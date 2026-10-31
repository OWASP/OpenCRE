"""YouTube channel as a comprehension source: video catalogue plus caption chunks, official routes only.

* Metadata comes from the YouTube Data API v3 (``YOUTUBE_API_KEY``); every list call costs 1 quota unit.
* Captions come from exported ``<video_id>.<lang>.vtt|srt`` files (channel owners export them in
  YouTube Studio) or, optionally, ``captions.download`` through OAuth for videos the authorising
  account owns (200 units each, hence the daily drip limit). No scraping, no unofficial transcript tools.

Chunk paths follow the external contract: ``<video_id>`` (catalogue entry) and
``<video_id>#t=<seconds>`` (a caption window), see ``external.page_url``.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

API_BASE = "https://www.googleapis.com/youtube/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
# Cached API answers older than this are fetched again: YouTube terms require stored API data to be
# refreshed within 30 days, and a refresh must notice videos that were removed.
CACHE_MAX_AGE_SECONDS = 24 * 3600
LIST_COST = 1  # quota units per channels/playlistItems/videos list call
CAPTION_DOWNLOAD_COST = 200
DEFAULT_DAILY_DOWNLOADS = 45  # 45 * 200 = 9,000 of the 10,000 default daily units
WINDOW_SECONDS = (
    90  # a window closes after this long or at the char cap, whichever is first
)
WINDOW_MAX_CHARS = 1500

# (url, params, headers) -> parsed JSON; injectable so tests never touch the network.
HttpGet = Callable[[str, Dict[str, Any], Dict[str, str]], Dict[str, Any]]


def _requests_get(url: str, params: Dict[str, Any], headers: Dict[str, str]) -> Any:
    import requests

    r = requests.get(url, params=params, headers=headers, timeout=60)
    if r.status_code >= 400:
        # Never include the request URL: it carries the API key.
        raise RuntimeError(f"YouTube API HTTP {r.status_code}")
    return r.json()


@dataclass
class Video:
    id: str
    title: str
    description: str = ""
    published: str = ""  # ISO date YYYY-MM-DD
    duration_seconds: int = 0
    speaker: str = ""
    extracted: Optional[Dict[str, Any]] = (
        None  # youtube_extract record, when --extract ran
    )


class YouTubeApi:
    """Quota-counting Data API client; list responses are cached on disk so a run can resume."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        http_get: Optional[HttpGet] = None,
        cache_dir: Optional[str] = None,
    ):
        self._key = (
            api_key if api_key is not None else os.environ.get("YOUTUBE_API_KEY", "")
        )
        self._get = http_get or _requests_get
        self.cache = Path(cache_dir) if cache_dir else None
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
        self.quota_used = 0

    def _call(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        cache_file = None
        if self.cache:
            tag = re.sub(
                r"[^A-Za-z0-9,._-]+",
                "_",
                f"{endpoint}-{json.dumps(params, sort_keys=True)}",
            )
            cache_file = self.cache / (tag[:180] + ".json")
            if (
                cache_file.exists()
                and time.time() - cache_file.stat().st_mtime < CACHE_MAX_AGE_SECONDS
            ):
                return json.loads(cache_file.read_text(encoding="utf-8"))
        if not self._key:
            raise RuntimeError("YOUTUBE_API_KEY is not set")
        out = self._get(f"{API_BASE}/{endpoint}", {**params, "key": self._key}, {})
        self.quota_used += LIST_COST
        if cache_file:
            cache_file.write_text(json.dumps(out), encoding="utf-8")
        return out

    def resolve_channel_id(self, value: str) -> str:
        """A ``UC...`` channel id for an id, ``@handle`` or youtube.com URL (``channels.list?forHandle``, 1 unit)."""
        return resolve_channel_id(value, self)

    def uploads_playlist(self, channel_id: str) -> str:
        channel_id = self.resolve_channel_id(channel_id)
        data = self._call("channels", {"part": "contentDetails", "id": channel_id})
        items = data.get("items") or []
        if not items:
            raise ValueError(f"channel {channel_id} not found")
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    def playlist_video_ids(self, playlist_id: str, limit: int = 0) -> List[str]:
        ids: List[str] = []
        token = ""
        while True:
            params: Dict[str, Any] = {
                "part": "contentDetails",
                "playlistId": playlist_id,
                "maxResults": 50,
            }
            if token:
                params["pageToken"] = token
            data = self._call("playlistItems", params)
            ids += [i["contentDetails"]["videoId"] for i in data.get("items") or []]
            token = data.get("nextPageToken") or ""
            if not token or (limit and len(ids) >= limit):
                return ids[:limit] if limit else ids

    def videos(self, ids: List[str]) -> List[Video]:
        out: List[Video] = []
        for i in range(0, len(ids), 50):
            data = self._call(
                "videos",
                {"part": "snippet,contentDetails", "id": ",".join(ids[i : i + 50])},
            )
            for it in data.get("items") or []:
                sn = it.get("snippet") or {}
                out.append(
                    Video(
                        id=it["id"],
                        title=str(sn.get("title") or "").strip(),
                        description=str(sn.get("description") or "").strip(),
                        published=str(sn.get("publishedAt") or "")[:10],
                        duration_seconds=parse_iso_duration(
                            (it.get("contentDetails") or {}).get("duration", "")
                        ),
                    )
                )
        return out

    def channel_videos(self, spec: Any, limit: int = 0) -> List[Video]:
        playlist = spec.playlist_id or self.uploads_playlist(spec.channel_id)
        return self.videos(self.playlist_video_ids(playlist, limit=limit))


_HANDLE_URL = re.compile(r"youtube\.com/(@[^/?#\s]+)", re.I)
_CHANNEL_URL = re.compile(r"youtube\.com/channel/(UC[^/?#\s]+)", re.I)


def handle_of(value: str) -> str:
    """``@handle`` for '@handle' or a youtube.com/@handle URL; '' for anything else (e.g. a UC... id)."""
    v = (value or "").strip()
    if v.startswith("@"):
        return v
    m = _HANDLE_URL.search(v)
    return m.group(1) if m else ""


def resolve_channel_id(spec_or_value: Any, api_or_http: Any = None) -> str:
    """Channel id for a spec (its ``channel_id``) or a plain value; ids pass through at no cost.

    Handles (``@FooSec``) and youtube.com URLs are looked up with ``channels.list?part=id&forHandle=``.
    ``api_or_http`` is a ``YouTubeApi`` or a bare ``HttpGet`` callable (tests, no network).
    Raises ``ValueError`` when the handle is unknown or matches more than one channel.
    """
    value = str(getattr(spec_or_value, "channel_id", spec_or_value) or "").strip()
    handle = handle_of(value)
    if not handle:
        m = _CHANNEL_URL.search(value)
        return m.group(1) if m else value
    api = api_or_http
    if not isinstance(api, YouTubeApi):
        api = YouTubeApi(http_get=api_or_http)
    items = (
        api._call("channels", {"part": "id", "forHandle": handle}).get("items") or []
    )
    ids = sorted({str(i.get("id") or "") for i in items if i.get("id")})
    if not ids:
        raise ValueError(f"YouTube handle {handle} not found")
    if len(ids) > 1:
        raise ValueError(f"YouTube handle {handle} is ambiguous: {', '.join(ids)}")
    return ids[0]


_ISO_DUR = re.compile(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def parse_iso_duration(text: str) -> int:
    m = _ISO_DUR.match(text or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


# ---- captions -------------------------------------------------------------------------------

Cue = Tuple[float, str]  # (start seconds, text)
_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
_TAG = re.compile(r"<[^>]+>")


def _seconds(ts: str) -> float:
    m = _TS.search(ts)
    if not m:
        return 0.0
    h, mi, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse_captions(text: str) -> List[Cue]:
    """Cues from WebVTT or SRT text (both use ``start --> end`` lines)."""
    cues: List[Cue] = []
    for block in re.split(r"\n\s*\n", (text or "").replace("\r\n", "\n")):
        lines = [l for l in block.split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if "-->" in line:
                body = " ".join(_TAG.sub("", l).strip() for l in lines[i + 1 :])
                body = re.sub(r"\s+", " ", body).strip()
                if body:
                    cues.append((_seconds(line.split("-->")[0]), body))
                break
    return cues


def caption_file_for(
    captions_dir: str, video_id: str, lang: str = "en"
) -> Optional[Path]:
    """``<video_id>.<lang>.vtt|srt``; prefers ``lang``, then any language."""
    d = Path(captions_dir)
    names = [f"{video_id}.{lang}.vtt", f"{video_id}.{lang}.srt"]
    for n in names:
        if (d / n).is_file():
            return d / n
    found = sorted(
        list(d.glob(f"{video_id}.*.vtt")) + list(d.glob(f"{video_id}.*.srt"))
    )
    return found[0] if found else None


def read_captions(captions_dir: Optional[str], video_id: str) -> List[Cue]:
    if not captions_dir:
        return []
    f = caption_file_for(captions_dir, video_id)
    return parse_captions(f.read_text(encoding="utf-8", errors="replace")) if f else []


# ---- OAuth captions.download (channels we own only), with a daily drip limit ----------------


class DripLimiter:
    """Counts caption downloads per UTC day in a small JSON state file."""

    def __init__(
        self,
        state_path: str,
        per_day: int = DEFAULT_DAILY_DOWNLOADS,
        today: Optional[Callable[[], str]] = None,
    ):
        self.path = Path(state_path)
        self.per_day = per_day
        self._today = today or (lambda: time.strftime("%Y-%m-%d", time.gmtime()))

    def _load(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return (
            data
            if data.get("day") == self._today()
            else {"day": self._today(), "count": 0}
        )

    def remaining(self) -> int:
        return max(0, self.per_day - int(self._load()["count"]))

    def allow(self) -> bool:
        return self.remaining() > 0

    def record(self) -> None:
        st = self._load()
        st["count"] = int(st["count"]) + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(st), encoding="utf-8")


def oauth_configured(env: Optional[Dict[str, str]] = None) -> bool:
    e = os.environ if env is None else env
    return all(
        e.get(k)
        for k in (
            "YOUTUBE_OAUTH_REFRESH_TOKEN",
            "YOUTUBE_OAUTH_CLIENT_ID",
            "YOUTUBE_OAUTH_CLIENT_SECRET",
        )
    )


class CaptionDownloader:
    """Optional ``captions.download`` path; only works for videos the authorising account owns."""

    def __init__(
        self,
        limiter: DripLimiter,
        http_post: Optional[Callable[[str, Dict[str, str]], Dict[str, Any]]] = None,
        http_get_text: Optional[
            Callable[[str, Dict[str, Any], Dict[str, str]], str]
        ] = None,
        env: Optional[Dict[str, str]] = None,
        out_dir: Optional[str] = None,
    ):
        self.env = os.environ if env is None else env
        self.limiter = limiter
        self._post = http_post or self._default_post
        self._get_text = http_get_text or self._default_get_text
        self.out_dir = Path(out_dir) if out_dir else None
        self._token = ""

    @staticmethod
    def _default_post(url: str, data: Dict[str, str]) -> Dict[str, Any]:
        import requests

        r = requests.post(url, data=data, timeout=60)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _default_get_text(
        url: str, params: Dict[str, Any], headers: Dict[str, str]
    ) -> str:
        import requests

        r = requests.get(url, params=params, headers=headers, timeout=60)
        if r.status_code >= 400:
            raise RuntimeError(f"YouTube API HTTP {r.status_code}")
        return r.text

    def enabled(self) -> bool:
        return oauth_configured(self.env)

    def _access_token(self) -> str:
        if not self._token:
            self._token = self._post(
                TOKEN_URL,
                {
                    "grant_type": "refresh_token",
                    "refresh_token": self.env["YOUTUBE_OAUTH_REFRESH_TOKEN"],
                    "client_id": self.env["YOUTUBE_OAUTH_CLIENT_ID"],
                    "client_secret": self.env["YOUTUBE_OAUTH_CLIENT_SECRET"],
                },
            )["access_token"]
        return self._token

    def fetch(self, video_id: str) -> List[Cue]:
        """Cues for one video, or [] when disabled, over the daily limit, or not downloadable."""
        if not self.enabled() or not self.limiter.allow():
            return []
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        try:
            tracks = self._get_text(
                f"{API_BASE}/captions",
                {"part": "snippet", "videoId": video_id},
                headers,
            )
            items = json.loads(tracks).get("items") or []
            if not items:
                return []
            self.limiter.record()  # one drip unit per download attempt (200 quota units)
            raw = self._get_text(
                f"{API_BASE}/captions/{items[0]['id']}", {"tfmt": "vtt"}, headers
            )
        except (
            Exception
        ):  # noqa: BLE001 - not our video (403) or transient: fall back to no captions
            return []
        if self.out_dir:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            (self.out_dir / f"{video_id}.en.vtt").write_text(raw, encoding="utf-8")
        return parse_captions(raw)


# ---- speaker guessing and linking -----------------------------------------------------------

_SPEAKER_PATTERNS = (
    re.compile(r"^(?P<speaker>[^|\-–—:]{3,60}?)\s+[-–—]\s+(?P<title>.+)$"),
    re.compile(r"^(?P<title>.+?)\s*\|\s*(?P<speaker>[^|]{3,60})$"),
    re.compile(r"^(?P<title>.+?)\s+by\s+(?P<speaker>[A-Z][^|\-–—]{2,60})$"),
)


def fold(text: str) -> str:
    """Lowercase, diacritics and punctuation removed, whitespace collapsed."""
    nfd = unicodedata.normalize("NFKD", text or "")
    plain = "".join(c for c in nfd if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def _looks_like_name(s: str) -> bool:
    words = s.split()
    return (
        2 <= len(words) <= 4
        and all(w[:1].isupper() for w in words)
        and not any(c.isdigit() for c in s)
    )


def guess_speaker(title: str) -> str:
    """Candidate speaker name from a title, or '' (patterns: 'Name - Title', 'Title | Name', 'Title by Name')."""
    t = (title or "").strip()
    for pat in _SPEAKER_PATTERNS:
        m = pat.match(t)
        if m and _looks_like_name(m.group("speaker").strip()):
            return m.group("speaker").strip()
    return ""


def match_speaker(guess: str, people: Iterable[str]) -> str:
    """The known person's canonical name when ``guess`` matches exactly after folding, else ''.

    Conservative: only full-name equality counts, and an ambiguous match (two different people
    folding to the same string) is rejected.
    """
    g = fold(guess)
    if not g:
        return ""
    hits = {p for p in people if fold(p) == g}
    return next(iter(hits)) if len(hits) == 1 else ""


def link_speakers(videos: List[Video], people: Iterable[str]) -> None:
    known = list(people)
    for v in videos:
        v.speaker = match_speaker(guess_speaker(v.title), known)


# ---- chunking ---------------------------------------------------------------------------------


def _duration_text(sec: int) -> str:
    return (
        f"{sec // 3600}h {sec % 3600 // 60}min" if sec >= 3600 else f"{sec // 60} min"
    )


def header_line(v: Video, channel_name: str) -> str:
    x = v.extracted
    if x is None:
        return (
            f"Talk: {v.title} | Speaker: {v.speaker or 'unknown'} | "
            f"Published: {v.published or 'unknown'} | Channel: {channel_name}"
        )
    return (
        f"Talk: {x.get('talk_title') or v.title} | "
        f"Speaker: {', '.join(x.get('speakers') or []) or v.speaker or 'unknown'} | "
        f"Event: {x.get('event') or 'unknown'} | Event date: {x.get('event_date') or 'unknown'} | "
        f"Published (upload): {v.published or 'unknown'} | Channel: {channel_name}"
    )


MAX_CHAPTERS = 15
_CHAPTER = re.compile(
    r"^\s*[(\[]?((?:\d{1,2}:)?\d{1,2}:\d{2})[)\]]?\s*[-–—:.]?\s*(\S.*?)\s*$"
)


def parse_chapters(description: str) -> List[Tuple[int, str, str]]:
    """(seconds, clock text, label) from timestamped description lines; needs 2+ lines, capped at 15."""
    found: List[Tuple[int, str, str]] = []
    for line in (description or "").splitlines():
        m = _CHAPTER.match(line)
        if not m:
            continue
        parts = [int(p) for p in m.group(1).split(":")]
        sec = 0
        for p in parts:
            sec = sec * 60 + p
        found.append((sec, m.group(1), m.group(2)[:120]))
    return found[:MAX_CHAPTERS] if len(found) >= 2 else []


def watch_url(video_id: str, seconds: int = 0) -> str:
    base = f"https://www.youtube.com/watch?v={video_id}"
    return f"{base}&t={seconds}s" if seconds else base


def catalogue_chunk(
    v: Video, channel_name: str, has_captions: bool = False
) -> Tuple[str, int, str]:
    x = v.extracted
    speaker = (", ".join(x.get("speakers") or []) if x else "") or v.speaker
    lines = [
        header_line(v, channel_name),
        f"Title: {v.title}",
        f"Speaker: {speaker or 'unknown'}",
    ]
    if x:
        lines += [
            f"Event: {x.get('event') or 'unknown'}",
            f"Event date: {x.get('event_date') or 'unknown'}",
            f"Published (upload): {v.published or 'unknown'}",
        ]
    else:
        lines.append(f"Published: {v.published or 'unknown'}")
    lines.append(
        f"Duration: {_duration_text(v.duration_seconds)}"
        if v.duration_seconds
        else "Duration: unknown"
    )
    lines.append(f"Video: {watch_url(v.id)}")
    if not has_captions:
        lines.append("Transcript: not indexed (metadata only)")
    for sec, clock, label in parse_chapters(v.description):
        lines.append(f"Chapters: {clock} {label} -> {watch_url(v.id, sec)}")
    if v.description:
        lines.append("Description: " + v.description[:2000])
    return (v.id, 0, "\n".join(lines))


def caption_windows(cues: List[Cue]) -> List[Tuple[int, str]]:
    """Group cues into ~60-90 s windows capped at ~1,500 chars; returns (start_seconds, text)."""
    out: List[Tuple[int, str]] = []
    start, buf = 0.0, []
    size = 0
    for t, text in cues:
        if buf and (t - start >= WINDOW_SECONDS or size + len(text) > WINDOW_MAX_CHARS):
            out.append((int(start), " ".join(buf)))
            buf, size = [], 0
        if not buf:
            start = t
        buf.append(text)
        size += len(text) + 1
    if buf:
        out.append((int(start), " ".join(buf)))
    return out


def video_chunks(
    v: Video, cues: List[Cue], channel_name: str
) -> List[Tuple[str, int, str]]:
    """Catalogue chunk first, then one chunk per caption window (``<id>#t=<seconds>``)."""
    chunks = [catalogue_chunk(v, channel_name, has_captions=bool(cues))]
    head = header_line(v, channel_name)
    for i, (start, text) in enumerate(caption_windows(cues), start=1):
        chunks.append((f"{v.id}#t={start}", i, f"{head}\n{text}"))
    return chunks
