# YouTube channels as a knowledge source

Approved `youtube_channel` targets (see `application/utils/comprehension/external.py`) are indexed as
`ext-<id>`: one catalogue chunk per video (`<video_id>`: title, speaker, date, duration, description)
and one chunk per ~90 s caption window (`<video_id>#t=<seconds>`, cited as a deep link). Only official
routes are used; there is no page scraping, yt-dlp or unofficial transcript library.

## Secrets

| Variable | Needed for |
|---|---|
| `YOUTUBE_API_KEY` | Catalogue (titles, real `publishedAt`, duration). Create it in Google Cloud, restrict it to *YouTube Data API v3*. |
| `YOUTUBE_OAUTH_CLIENT_ID`, `YOUTUBE_OAUTH_CLIENT_SECRET`, `YOUTUBE_OAUTH_REFRESH_TOKEN` | Optional `captions.download`. Works only for videos owned by the authorising account, so only for channels we run. Off unless all three are set. |
| none | Captions for other channels: the owner exports `<video_id>.<lang>.vtt` or `.srt` from YouTube Studio; point `--captions-dir` at them. |

The key is never logged; errors report only the HTTP status.

## Quota

The default allowance is 10,000 units/day. List calls (channels, playlistItems, videos) cost 1 unit
each: 1,600 videos need about 32 playlist pages plus 32 video batches, roughly 65 units. `captions.download`
costs about 200 units, so about 50 per day; the downloader stops at 45/day (state in
`<cache-dir>/caption-downloads.json`). API responses are cached in `<cache-dir>/api`, so a re-run or a
resumed run spends no quota for pages already read.

## Dry run

```bash
export YOUTUBE_API_KEY=...
python scripts/ingest_youtube.py \
  --spec-json spec.json --captions-dir ./captions --people-file leaders.txt --limit 50
```

`spec.json` is an `ExternalSpec` (`id`, `name`, `channel_id` or `playlist_id`). Without `--spec-json`
the approved `youtube_channel` rows of the targets table are used. The dry run prints videos found, how
many have captions, chunks, estimated tokens and cost (embedding cost, plus a pilot-rate figure of
about $0.01 per talk, i.e. about $16 for 1,600 talks) and writes nothing. Add `--apply` to embed and
write. `--people-file` (one name per line, e.g. Nest leaders) enables speaker linking: a speaker is
set only on an exact, unambiguous name match (case and diacritics ignored), otherwise it stays `unknown`.
