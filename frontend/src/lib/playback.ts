import type { ArtistSummary, Song } from "@/types/catalog";

export function isPlayableSong(song: Song): boolean {
  if (song.status !== "ready" || !song.can_stream || !song.preview_url?.trim()) {
    return false;
  }

  try {
    const url = new URL(song.preview_url);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function artistsInOrder(artists: ArtistSummary[]): ArtistSummary[] {
  return [...artists].sort(
    (left, right) =>
      (left.artist_order ?? Number.MAX_SAFE_INTEGER) -
      (right.artist_order ?? Number.MAX_SAFE_INTEGER),
  );
}

export function playableQueue(songs: Song[]): Song[] {
  return songs.filter(isPlayableSong);
}

export function adjacentSong(
  queue: Song[],
  currentSongId: string,
  direction: "previous" | "next",
): Song | null {
  const currentIndex = queue.findIndex((song) => song.id === currentSongId);
  if (currentIndex < 0) {
    return null;
  }

  const nextIndex = direction === "next" ? currentIndex + 1 : currentIndex - 1;
  return queue[nextIndex] ?? null;
}

export function formatPlaybackTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "0:00";
  }

  const totalSeconds = Math.floor(seconds);
  const minutes = Math.floor(totalSeconds / 60);
  return `${minutes}:${String(totalSeconds % 60).padStart(2, "0")}`;
}
