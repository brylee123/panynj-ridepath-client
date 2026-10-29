"""Source-shaped alert, content-fragment and website configuration responses."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .models import InvalidFeed


@dataclass(frozen=True)
class AnnouncementFeed:
    records: tuple[dict[str, Any], ...]
    fetched_at: datetime


@dataclass(frozen=True)
class SiteFeed:
    page_model: dict[str, Any]
    config: dict[str, Any]
    fetched_at: datetime


def parse_alerts(payload: Any, fetched_at: datetime) -> AnnouncementFeed:
    records = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise InvalidFeed("Expected an alerts array")
    for item in records:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("SentMessage"), str)
            or not isinstance(item.get("Subject"), str)
        ):
            raise InvalidFeed("Invalid alert record")
        if not isinstance(item.get("messageid"), (int, str)) or isinstance(
            item.get("messageid"), bool
        ):
            raise InvalidFeed("Missing alert message identity")
    return AnnouncementFeed(tuple(dict(item) for item in records), fetched_at)


def parse_planned(payload: Any, fetched_at: datetime) -> AnnouncementFeed:
    if not isinstance(payload, dict) or not isinstance(payload.get("entities"), list):
        raise InvalidFeed("Expected a planned-service entities array")
    if not isinstance(payload.get("properties", {}), dict):
        raise InvalidFeed("Invalid planned-service folder metadata")
    paging = payload.get("properties", {}).get("srn:paging", {})
    if not isinstance(paging, dict):
        raise InvalidFeed("Invalid planned-service pagination metadata")
    if "total" in paging and (type(paging["total"]) is not int or paging["total"] < 0):
        raise InvalidFeed("Invalid planned-service total")
    for item in payload["entities"]:
        if not isinstance(item, dict) or not isinstance(item.get("properties"), dict):
            raise InvalidFeed("Invalid planned-service record")
        if not isinstance(item["properties"].get("elements"), dict):
            raise InvalidFeed("Missing planned-service content elements")
    return AnnouncementFeed(tuple(dict(item) for item in payload["entities"]), fetched_at)
