"""Thin Nest REST client (X-API-Key). No SDK dependency."""

from __future__ import annotations

import os
from typing import Any, Dict, Iterator, List, Optional

import requests

from application.utils.owasp_agent.models import Chapter, Event, Project

DEFAULT_BASE_URL = "https://nest.owasp.org/api/v0"
DEFAULT_TIMEOUT = 30.0


class NestClientError(Exception):
    """Nest API failure."""


class NestAuthError(NestClientError):
    """Missing or invalid API key."""


class NestClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = (
            api_key if api_key is not None else os.environ.get("NEST_API_KEY", "")
        ).strip()
        self.base_url = (
            base_url or os.environ.get("NEST_API_BASE", DEFAULT_BASE_URL)
        ).rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise NestAuthError("NEST_API_KEY is required for Nest API access")
        return {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "OpenCRE-owasp-agent/1.0",
        }

    def _get(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        resp = self.session.get(
            url, headers=self._headers(), params=params or {}, timeout=self.timeout
        )
        if resp.status_code in (401, 403):
            raise NestAuthError(f"Nest auth failed: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise NestClientError(f"Nest HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if not isinstance(data, dict):
            raise NestClientError("Nest response was not a JSON object")
        return data

    def iter_pages(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Iterator[Dict[str, Any]]:
        page = 1
        while True:
            q = dict(params or {})
            q["page"] = page
            payload = self._get(path, q)
            items = payload.get("items") or payload.get("results") or []
            if not isinstance(items, list):
                break
            for item in items:
                if isinstance(item, dict):
                    yield item
            total_pages = payload.get("total_pages")
            has_next = payload.get("has_next")
            if has_next is False:
                break
            if total_pages is not None and page >= int(total_pages):
                break
            if not items:
                break
            page += 1
            if page > 500:
                break

    def list_chapters(self) -> List[Chapter]:
        out: List[Chapter] = []
        for item in self.iter_pages("chapters"):
            out.append(self._parse_chapter(item))
        return out

    def list_projects(self) -> List[Project]:
        out: List[Project] = []
        for item in self.iter_pages("projects"):
            out.append(self._parse_project(item))
        return out

    def list_events(self, upcoming_only: Optional[bool] = None) -> List[Event]:
        params: Dict[str, Any] = {}
        if upcoming_only is True:
            params["is_upcoming"] = "true"
        elif upcoming_only is False:
            params["is_upcoming"] = "false"
        out: List[Event] = []
        for item in self.iter_pages("events", params):
            out.append(self._parse_event(item))
        return out

    @staticmethod
    def _parse_chapter(item: Dict[str, Any]) -> Chapter:
        key = str(item.get("key") or item.get("slug") or item.get("name") or "").strip()
        tags = item.get("tags") or item.get("topics") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        return Chapter(
            key=key or "unknown",
            name=str(item.get("name") or key),
            country=str(item.get("country") or ""),
            region=str(item.get("region") or ""),
            city=str(item.get("city") or item.get("suggested_location") or ""),
            latitude=_opt_float(item.get("latitude")),
            longitude=_opt_float(item.get("longitude")),
            url=str(
                item.get("url") or item.get("owasp_url") or item.get("nest_url") or ""
            ),
            tags=list(tags) if isinstance(tags, list) else [],
            source="nest",
            raw=item,
        )

    @staticmethod
    def _parse_project(item: Dict[str, Any]) -> Project:
        key = str(item.get("key") or item.get("slug") or item.get("name") or "").strip()
        tags = item.get("tags") or item.get("topics") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        return Project(
            key=key or "unknown",
            name=str(item.get("name") or key),
            level=str(item.get("level") or ""),
            description=str(item.get("description") or item.get("summary") or ""),
            url=str(
                item.get("url") or item.get("owasp_url") or item.get("nest_url") or ""
            ),
            tags=list(tags) if isinstance(tags, list) else [],
            source="nest",
            raw=item,
        )

    @staticmethod
    def _parse_event(item: Dict[str, Any]) -> Event:
        key = str(item.get("key") or item.get("id") or item.get("name") or "").strip()
        topics = item.get("topics") or item.get("tags") or []
        if isinstance(topics, str):
            topics = [t.strip() for t in topics.split(",") if t.strip()]
        talks = item.get("talks") or item.get("sessions") or []
        if isinstance(talks, list):
            talk_names = [
                str(t.get("title") if isinstance(t, dict) else t) for t in talks
            ]
        else:
            talk_names = []
        return Event(
            key=key or "unknown",
            name=str(item.get("name") or item.get("title") or key),
            start_date=str(item.get("start_date") or item.get("start") or ""),
            end_date=str(item.get("end_date") or item.get("end") or ""),
            chapter_key=str(item.get("chapter_key") or item.get("chapter") or ""),
            city=str(item.get("city") or item.get("location") or ""),
            latitude=_opt_float(item.get("latitude")),
            longitude=_opt_float(item.get("longitude")),
            url=str(item.get("url") or item.get("owasp_url") or ""),
            description=str(item.get("description") or item.get("summary") or ""),
            topics=list(topics) if isinstance(topics, list) else [],
            talks=talk_names,
            source="nest",
            raw=item,
        )


def _opt_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
