export type AlbumSummary = {
  id: string;
  source_provider: string;
  external_id: string;
  title: string;
  album_type: string | null;
  cover_url: string | null;
  release_date: string | null;
  external_url: string | null;
};

export type ArtistSummary = {
  id: string;
  source_provider: string;
  external_id: string;
  name: string;
  image_url: string | null;
  external_url: string | null;
  role: string | null;
  artist_order: number | null;
};

export type Song = {
  id: string;
  source_provider: string;
  external_id: string;
  title: string;
  duration_ms: number | null;
  track_number: number | null;
  release_date: string | null;
  explicit: boolean | null;
  cover_url: string | null;
  external_url: string | null;
  preview_url: string | null;
  audio_object_key: string | null;
  license_name: string | null;
  license_url: string | null;
  can_stream: boolean;
  can_download: boolean;
  status: string;
  provider_popularity: number | null;
  popularity_score: number | null;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
  album: AlbumSummary | null;
  artists: ArtistSummary[];
};

export type Artist = {
  id: string;
  source_provider: string;
  external_id: string;
  name: string;
  image_url: string | null;
  external_url: string | null;
  created_at: string;
  updated_at: string;
};
