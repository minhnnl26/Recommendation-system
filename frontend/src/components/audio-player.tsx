"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

import {
  adjacentSong,
  artistsInOrder,
  formatPlaybackTime,
  isPlayableSong,
} from "@/lib/playback";
import type { Song } from "@/types/catalog";

export type AudioPlayerHandle = {
  togglePlay: () => void;
};

type AudioPlayerProps = {
  currentSong: Song | null;
  queue: Song[];
  playRequestId: number;
  onSongChange: (song: Song) => void;
  onPlayingChange: (playing: boolean) => void;
};

const AudioPlayer = forwardRef<AudioPlayerHandle, AudioPlayerProps>(
  function AudioPlayer(
    { currentSong, queue, playRequestId, onSongChange, onPlayingChange },
    ref,
  ) {
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const lastPlayRequestId = useRef(0);
    const [isPlaying, setIsPlaying] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [playbackError, setPlaybackError] = useState<string | null>(null);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);

    useImperativeHandle(
      ref,
      () => ({
        togglePlay() {
          const audio = audioRef.current;
          if (!audio || !currentSong) return;

          if (audio.paused) {
            void audio.play().catch(() => {
              setPlaybackError("This preview could not be played in your browser.");
              setIsPlaying(false);
              onPlayingChange(false);
            });
          } else {
            audio.pause();
          }
        },
      }),
      [currentSong, onPlayingChange],
    );

    useEffect(() => {
      const audio = audioRef.current ?? new Audio();
      audioRef.current = audio;

      const handleLoadStart = () => setIsLoading(true);
      const handleCanPlay = () => setIsLoading(false);
      const handleLoadedMetadata = () => setDuration(audio.duration || 0);
      const handleTimeUpdate = () => setCurrentTime(audio.currentTime);
      const handlePlay = () => {
        setIsPlaying(true);
        onPlayingChange(true);
      };
      const handlePause = () => {
        setIsPlaying(false);
        onPlayingChange(false);
      };
      const handleEnded = () => {
        setIsPlaying(false);
        onPlayingChange(false);
      };
      const handleError = () => {
        setIsLoading(false);
        setIsPlaying(false);
        onPlayingChange(false);
        setPlaybackError("This preview could not be loaded. Please choose another song.");
      };

      audio.addEventListener("loadstart", handleLoadStart);
      audio.addEventListener("canplay", handleCanPlay);
      audio.addEventListener("loadedmetadata", handleLoadedMetadata);
      audio.addEventListener("timeupdate", handleTimeUpdate);
      audio.addEventListener("play", handlePlay);
      audio.addEventListener("pause", handlePause);
      audio.addEventListener("ended", handleEnded);
      audio.addEventListener("error", handleError);

      if (!currentSong || !isPlayableSong(currentSong)) {
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
        setIsPlaying(false);
        setIsLoading(false);
        setCurrentTime(0);
        setDuration(0);
      } else {
        audio.pause();
        audio.currentTime = 0;
        setCurrentTime(0);
        setDuration(0);
        setPlaybackError(null);
        audio.src = currentSong.preview_url ?? "";
        audio.load();

        if (playRequestId > lastPlayRequestId.current) {
          lastPlayRequestId.current = playRequestId;
          void audio.play().catch(() => {
            setPlaybackError("This preview could not be played in your browser.");
            setIsPlaying(false);
            onPlayingChange(false);
          });
        }
      }

      return () => {
        audio.removeEventListener("loadstart", handleLoadStart);
        audio.removeEventListener("canplay", handleCanPlay);
        audio.removeEventListener("loadedmetadata", handleLoadedMetadata);
        audio.removeEventListener("timeupdate", handleTimeUpdate);
        audio.removeEventListener("play", handlePlay);
        audio.removeEventListener("pause", handlePause);
        audio.removeEventListener("ended", handleEnded);
        audio.removeEventListener("error", handleError);
        audio.pause();
      };
    }, [currentSong, onPlayingChange, playRequestId]);

    if (!currentSong) return null;

    const orderedArtists = artistsInOrder(currentSong.artists);
    const previousSong = adjacentSong(queue, currentSong.id, "previous");
    const nextSong = adjacentSong(queue, currentSong.id, "next");
    const maxDuration = duration || (currentSong.duration_ms ?? 0) / 1000;

    function seek(value: string) {
      const audio = audioRef.current;
      const nextTime = Number(value);
      if (!audio || !Number.isFinite(nextTime)) return;
      audio.currentTime = nextTime;
      setCurrentTime(nextTime);
    }

    function toggleAudio() {
      const audio = audioRef.current;
      if (!audio) return;
      if (audio.paused) {
        void audio.play().catch(() => {
          setPlaybackError("This preview could not be played in your browser.");
        });
      } else {
        audio.pause();
      }
    }

    return (
      <section aria-label="Audio player" className="audio-player">
        <div className="audio-player-info">
          <p className="song-kicker">Now selected</p>
          <strong>{currentSong.title}</strong>
          <span>
            {orderedArtists.map((artist) => artist.name).join(", ") || "Unknown artist"}
          </span>
        </div>
        <div className="audio-player-controls">
          <button
            aria-label="Play previous song"
            disabled={!previousSong}
            onClick={() => previousSong && onSongChange(previousSong)}
            type="button"
          >
            Previous
          </button>
          <button
            aria-label={isPlaying ? "Pause song" : "Play song"}
            className="primary-player-button"
            onClick={toggleAudio}
            type="button"
          >
            {isPlaying ? "Pause" : "Play"}
          </button>
          <button
            aria-label="Play next song"
            disabled={!nextSong}
            onClick={() => nextSong && onSongChange(nextSong)}
            type="button"
          >
            Next
          </button>
        </div>
        <div className="audio-player-progress">
          <span>{formatPlaybackTime(currentTime)}</span>
          <input
            aria-label="Seek audio"
            disabled={!maxDuration}
            max={maxDuration}
            min="0"
            onChange={(event) => seek(event.target.value)}
            type="range"
            value={Math.min(currentTime, maxDuration)}
          />
          <span>{formatPlaybackTime(maxDuration)}</span>
        </div>
        <div aria-live="polite" className="audio-player-status" role="status">
          {isLoading ? "Loading preview…" : playbackError ?? ""}
        </div>
      </section>
    );
  },
);

export default AudioPlayer;
