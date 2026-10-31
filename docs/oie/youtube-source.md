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

**Status (2026-10-31):** a `YOUTUBE_API_KEY` is in the staging `.env` and the OWASP channel catalogue (1,737 videos, metadata only, no captions) was ingested on 2026-10-29. Code paths are also covered by mocked-HTTP tests.

## Storage terms (YouTube API Services Developer Policies, III.E.4; page last updated 2026-10-15)

Stored API data may be kept at most 30 calendar days, then it must be refreshed or deleted. So `youtube_channel` targets
cannot have `refresh_days` above 30 (enforced in `validate_spec`), and the catalogue ingested on 2026-10-29 must be
re-ingested (or deleted) by 2026-11-28. The same policy says clients must not use API data "to create new or derived
data or metrics"; whether LLM speaker/event extraction (EXT-1.14) and embeddings count is a legal call for the owner,
not settled here. Scraping YouTube or obtaining scraped YouTube data is prohibited, hence no unofficial transcript tools.

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


## Channel handles

`channel_id` may be a handle (`@FooSec`) or a `youtube.com/@handle` URL. It is resolved with
`channels.list?part=id&forHandle=@handle` (1 quota unit, cached in `<cache-dir>/api` like every other
call) automatically before the uploads playlist is read, and the dry run prints `resolved @FooSec -> UC...`.
An unknown or ambiguous handle is reported as an error for that channel (exit code 1); other channels
still run. A full `youtube.com/channel/UC...` URL is reduced to its id without a call.

## Speaker names file

`scripts/nest_people_file.py` writes the `--people-file` (one full name per line, deduplicated, sorted)
from OWASP Nest project leaders:

```bash
# live: reads every project once, needs NEST_API_KEY (and optionally NEST_API_BASE), same as nest_loader.py
python scripts/nest_people_file.py --out leaders.txt --save-json nest-projects.json
# offline, from a saved dump (a list of project records, or {"projects": [...]}, each with leaders[].name)
python scripts/nest_people_file.py --from-json nest-projects.json --out leaders.txt
```
