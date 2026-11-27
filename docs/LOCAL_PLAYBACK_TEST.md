# Local Playback Test

Frontend playback is intentionally limited to songs that satisfy all three conditions:

- `status = 'ready'`
- `can_stream = true`
- `preview_url` is a valid, non-empty HTTP(S) audio URL

The frontend uses `preview_url` only. It does not treat `external_url` or `audio_object_key` as playable audio.

For local testing, use audio that you own, public-domain audio, or audio covered by an appropriate license. Do not download or commit unknown or copyrighted audio into this repository, and do not put credentials in source code.

The following SQL is a non-executed placeholder template only. Replace the values locally after reviewing the license and the target environment:

```sql
update public.songs
set
  preview_url = 'https://example.com/licensed-preview.mp3',
  can_stream = true
where id = '<song-uuid>';
```
