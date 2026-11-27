# Music Provider Feasibility Spike

This spike evaluates metadata and playback feasibility for two providers without
writing to Supabase or integrating the frontend.

## Providers

- **Apple iTunes Search API**: useful for popular/catalog discovery and metadata.
  Track previews are treated as short promotional previews only; a missing
  `previewUrl` makes the result metadata-only.
- **Jamendo API v3**: useful for licensed music experiments. A valid `audio` URL
  is normalized as full playback, while `audiodownload` is deliberately never
  used.

Both adapters return the same internal `NormalizedTrack` contract. Provider
order is preserved, malformed records are skipped, and there is no cross-provider
deduplication or database import in this spike.

## Playback and licensing boundaries

The adapters never download, cache, or save audio. They do not upload audio to
R2, and provider audio is not used as training data. The application must still
review provider terms and the applicable license before any product use.

`full`, `preview`, and `external_only` describe feasibility only. `external_url`
is a metadata/store link, never an audio URL.

## Query normalization

`normalize_mood_query` is deterministic and rule-based. It recognizes a small
Vietnamese vocabulary such as `nhạc buồn`, `nhạc vui`, `thư giãn`, `tập trung`,
`ngủ`, and `tập thể dục`. It returns the original query, normalized text,
optional residual text, a mood label, and provider tags. It does not use an LLM
and does not interpret every free-text query as a mood.

## Evaluation limits and next step

Unit tests use mocked HTTP responses only. A live probe is available through
`app.scripts.probe_music_providers`, but is intentionally not part of the local
test gate. Results are not yet imported into the catalog, so this does not prove
long-term availability, licensing suitability, rate limits, or production
playback reliability.

The next step is to design a unified provider catalog migration and a controlled,
reviewable importer after licensing and schema decisions are approved.
