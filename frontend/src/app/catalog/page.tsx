"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { FormEvent } from "react";

import AudioPlayer, { type AudioPlayerHandle } from "@/components/audio-player";
import { getSongs } from "@/lib/api";
import { formatDuration, formatReleaseDate } from "@/lib/format";
import { artistsInOrder, isPlayableSong, playableQueue } from "@/lib/playback";
import type { Song } from "@/types/catalog";

const PAGE_SIZE = 12;

function Cover({ song }: { song: Song }) {
  if (song.cover_url) {
    return (
      <div
        aria-label={`Cover art for ${song.title}`}
        className="song-cover"
        role="img"
        style={{ backgroundImage: `url(${song.cover_url})` }}
      />
    );
  }

  return (
    <div aria-label="Cover art unavailable" className="song-cover cover-placeholder" role="img">
      <span aria-hidden="true">♪</span>
    </div>
  );
}

function SongCard({
  song,
  currentSongId,
  isPlaying,
  onPlay,
}: {
  song: Song;
  currentSongId: string | null;
  isPlaying: boolean;
  onPlay: (song: Song) => void;
}) {
  const artists = artistsInOrder(song.artists);
  const [featuredArtist, ...otherArtists] = artists;
  const playable = isPlayableSong(song);
  const isCurrent = currentSongId === song.id;

  return (
    <article className="song-card">
      <Cover song={song} />
      <div className="song-card-body">
        <div className="song-heading">
          {playable ? (
            <button
              aria-label={`${isCurrent && isPlaying ? "Pause" : "Play"} ${song.title}`}
              className="card-play-button"
              onClick={() => onPlay(song)}
              type="button"
            >
              {isCurrent && isPlaying ? "Pause" : "Play"}
            </button>
          ) : null}
          <div>
            <p className="song-kicker">{song.source_provider}</p>
            <h2>{song.title}</h2>
          </div>
          {song.explicit ? <span className="badge">Explicit</span> : null}
        </div>

        <div className="artist-line" aria-label="Artists">
          {featuredArtist ? <strong>{featuredArtist.name}</strong> : <span>Unknown artist</span>}
          {otherArtists.length > 0 ? (
            <span className="artist-features">
              {otherArtists.map((artist) => artist.name).join(", ")}
            </span>
          ) : null}
        </div>

        <div className="song-meta">
          <span>{song.album?.title ?? "Single"}</span>
          <span>{formatReleaseDate(song.release_date)}</span>
          <span>{formatDuration(song.duration_ms)}</span>
        </div>

        <p className={`availability ${playable ? "available" : "unavailable"}`}>
          {playable ? "Available to play" : "Playback unavailable"}
        </p>
      </div>
    </article>
  );
}

export default function CatalogPage() {
  const playerRef = useRef<AudioPlayerHandle>(null);
  const [songs, setSongs] = useState<Song[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentSong, setCurrentSong] = useState<Song | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playRequestId, setPlayRequestId] = useState(0);

  const loadSongs = useCallback(async (query: string, nextOffset: number, append: boolean) => {
    if (append) {
      setIsLoadingMore(true);
    } else {
      setIsLoading(true);
    }
    setError(null);

    try {
      const page = await getSongs({
        limit: PAGE_SIZE,
        offset: nextOffset,
        query: query || undefined,
      });
      setSongs((current) => (append ? [...current, ...page] : page));
      setOffset(nextOffset + page.length);
      setHasMore(page.length === PAGE_SIZE);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not load songs");
    } finally {
      setIsLoading(false);
      setIsLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    void loadSongs(activeQuery, 0, false);
  }, [activeQuery, loadSongs]);

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActiveQuery(searchInput.trim());
  }

  function retry() {
    void loadSongs(activeQuery, 0, false);
  }

  function handlePlay(song: Song) {
    if (!isPlayableSong(song)) {
      return;
    }
    if (currentSong?.id === song.id) {
      playerRef.current?.togglePlay();
      return;
    }
    setCurrentSong(song);
    setPlayRequestId((requestId) => requestId + 1);
  }

  const isEmpty = !isLoading && !error && songs.length === 0;
  const queue = playableQueue(songs);

  return (
    <main className="catalog-page">
      <header className="catalog-header">
        <div>
          <p className="eyebrow">Catalog</p>
          <h1>Find your next track.</h1>
          <p className="summary">Browse the songs currently available in the catalog.</p>
        </div>
        <Link className="back-link" href="/">
          Home
        </Link>
      </header>

      <form className="search-form" onSubmit={submitSearch} role="search">
        <label htmlFor="song-search">Search songs</label>
        <div className="search-controls">
          <input
            id="song-search"
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search by title"
            type="search"
            value={searchInput}
          />
          <button type="submit">Search</button>
        </div>
      </form>

      {isLoading ? <p className="state-panel">Loading songs…</p> : null}
      {error ? (
        <div className="state-panel error-panel" role="alert">
          <p>{error}</p>
          <button onClick={retry} type="button">
            Retry
          </button>
        </div>
      ) : null}
      {isEmpty ? (
        <div className="state-panel">
          <p>{activeQuery ? `No songs found for “${activeQuery}”.` : "No songs are available yet."}</p>
        </div>
      ) : null}

      {songs.length > 0 ? (
        <>
          <section aria-label="Song catalog" className="song-grid">
            {songs.map((song) => (
              <SongCard
                currentSongId={currentSong?.id ?? null}
                isPlaying={isPlaying}
                key={song.id}
                onPlay={handlePlay}
                song={song}
              />
            ))}
          </section>
          {hasMore ? (
            <div className="load-more-row">
              <button
                disabled={isLoadingMore}
                onClick={() => void loadSongs(activeQuery, offset, true)}
                type="button"
              >
                {isLoadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          ) : null}
        </>
      ) : null}
      <AudioPlayer
        currentSong={currentSong}
        onPlayingChange={setIsPlaying}
        onSongChange={(song) => {
          setCurrentSong(song);
          setPlayRequestId((requestId) => requestId + 1);
        }}
        playRequestId={playRequestId}
        queue={queue}
        ref={playerRef}
      />
    </main>
  );
}
