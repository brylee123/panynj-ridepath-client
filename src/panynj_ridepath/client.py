"""Bounded asynchronous HTTP access to the public RidePATH endpoint."""

import asyncio
import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic
from urllib.parse import urljoin, urlsplit

import aiohttp

from .announcements import AnnouncementFeed, SiteFeed, parse_alerts, parse_planned
from .const import (
    ALERTS_URL,
    FEED_URL,
    MAX_RESPONSE_BYTES,
    PLANNED_URL,
    SITE_CONFIG_URL,
    SITE_MODEL_URL,
)
from .models import Feed, InvalidFeed, parse_response


class CannotConnect(Exception):
    """A network or HTTP failure."""


class RateLimited(CannotConnect):
    """An upstream Retry-After deadline is active."""

    def __init__(self, seconds: float) -> None:
        super().__init__("Upstream requested a retry delay")
        self.seconds = seconds


class RidePathClient:
    """Use the caller's session; never close it or disable TLS."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session
        self.retry_at: dict[str, float] = {}

    async def async_fetch(self) -> Feed:
        """Fetch at most 1 MiB with a total timeout and no immediate retries."""
        return parse_response(await self._async_get_json(FEED_URL), datetime.now(UTC))

    async def async_fetch_alerts(self) -> AnnouncementFeed:
        return parse_alerts(await self._async_get_json(ALERTS_URL), datetime.now(UTC))

    async def async_fetch_planned(self) -> AnnouncementFeed:
        """Follow only bounded same-folder next links, never CMS mutation actions."""
        url = PLANNED_URL
        entities = []
        visited = set()
        for _ in range(10):
            if url in visited:
                raise InvalidFeed("Repeated planned-service page")
            visited.add(url)
            payload = await self._async_get_json(url)
            page = parse_planned(payload, datetime.now(UTC))
            entities.extend(page.records)
            links = payload.get("links", [])
            if not isinstance(links, list):
                raise InvalidFeed("Invalid planned-service pagination")
            if any(
                not isinstance(link, dict) or not isinstance(link.get("rel", []), list)
                for link in links
            ):
                raise InvalidFeed("Invalid planned-service pagination relation")
            next_links = [
                link.get("href")
                for link in links
                if isinstance(link, dict) and "next" in link.get("rel", [])
            ]
            if not next_links:
                paging = payload.get("properties", {}).get("srn:paging", {})
                total = paging.get("total")
                if isinstance(total, int) and total > len(entities):
                    raise InvalidFeed("Incomplete planned-service listing")
                return AnnouncementFeed(tuple(entities), datetime.now(UTC))
            if len(next_links) != 1 or not isinstance(next_links[0], str):
                raise InvalidFeed("Invalid planned-service next link")
            candidate = urljoin(PLANNED_URL, next_links[0])
            parts = urlsplit(candidate)
            if (
                parts.scheme != "https"
                or parts.netloc != "www.panynj.gov"
                or parts.path != "/api/assets/path/planned-services.json"
            ):
                raise InvalidFeed("Unexpected planned-service next link")
            url = candidate
        raise InvalidFeed("Too many planned-service pages")

    async def async_fetch_site(self) -> SiteFeed:
        model = await self._async_get_json(SITE_MODEL_URL)
        config = await self._async_get_json(SITE_CONFIG_URL)
        if not isinstance(model, dict) or not isinstance(config, dict):
            raise InvalidFeed("Invalid PATH site configuration")
        return SiteFeed(model, config, datetime.now(UTC))

    async def _async_get_json(self, url: str):
        """One bounded GET, with independent Retry-After deadlines per resource."""
        if (remaining := self.retry_at.get(url, 0.0) - monotonic()) > 0:
            raise RateLimited(remaining)
        try:
            async with asyncio.timeout(10):
                async with self.session.get(
                    url,
                    headers={"Accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status in (429, 503):
                        delay = self._retry_after(response.headers.get("Retry-After"))
                        self.retry_at[url] = monotonic() + delay
                        raise RateLimited(delay)
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.content.iter_chunked(16384):
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise InvalidFeed("Response exceeds 1 MiB")
                    try:
                        payload = json.loads(body)
                    except (ValueError, UnicodeError, RecursionError) as err:
                        raise InvalidFeed("Response is not valid JSON") from err
                    return payload
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(f"Feed request failed ({type(err).__name__})") from err

    @staticmethod
    def _retry_after(value: str | None) -> float:
        if value:
            try:
                seconds = float(value)
                if seconds >= 0 and seconds < float("inf"):
                    return max(30, seconds)
            except ValueError:
                try:
                    target = parsedate_to_datetime(value)
                    if target.tzinfo is not None:
                        return max(30, (target - datetime.now(UTC)).total_seconds())
                except ValueError, TypeError, OverflowError:
                    pass
        return 60
