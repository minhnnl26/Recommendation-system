import type { Artist, Song } from "@/types/catalog";

type SongListOptions = {
  limit?: number;
  offset?: number;
  query?: string;
};

type ArtistListOptions = {
  limit?: number;
  offset?: number;
  query?: string;
};

function getApiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!baseUrl) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured");
  }
  return baseUrl.replace(/\/$/, "");
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error(`Catalog request failed (${response.status})`);
  }

  return (await response.json()) as T;
}

function addPaginationParams(
  params: URLSearchParams,
  limit = 12,
  offset = 0,
  query?: string,
): void {
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  const normalizedQuery = query?.trim();
  if (normalizedQuery) {
    params.set("query", normalizedQuery);
  }
}

export function getSongs(options: SongListOptions = {}): Promise<Song[]> {
  const params = new URLSearchParams();
  addPaginationParams(params, options.limit, options.offset, options.query);
  return getJson<Song[]>(`/api/v1/songs?${params.toString()}`);
}

export function getArtists(options: ArtistListOptions = {}): Promise<Artist[]> {
  const params = new URLSearchParams();
  addPaginationParams(params, options.limit, options.offset, options.query);
  return getJson<Artist[]>(`/api/v1/artists?${params.toString()}`);
}
