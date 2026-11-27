export function formatDuration(durationMs: number | null): string {
  if (durationMs === null || !Number.isFinite(durationMs) || durationMs < 0) {
    return "—";
  }

  const totalSeconds = Math.floor(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

export function formatReleaseDate(releaseDate: string | null): string {
  if (!releaseDate) {
    return "Release date unknown";
  }

  const date = new Date(`${releaseDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return "Release date unknown";
  }

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}
