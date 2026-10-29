"""Source-shaped RidePATH models. No display, freshness or delay policy."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


class InvalidFeed(ValueError):
    """The response cannot safely be interpreted as a RidePATH feed."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 255:
        raise InvalidFeed(f"Invalid {field}")
    return value


@dataclass(frozen=True)
class Arrival:
    target: str
    secondsToArrival: Any
    arrivalTimeMessage: str
    lineColor: Any
    headSign: Any
    lastUpdated: Any
    raw_data: dict[str, Any]


@dataclass(frozen=True)
class Destination:
    label: str
    messages: tuple[Arrival, ...]


@dataclass(frozen=True)
class Station:
    consideredStation: str
    destinations: tuple[Destination, ...]


@dataclass(frozen=True)
class Feed:
    results: tuple[Station, ...]
    fetched_at: datetime


def parse_response(payload: Any, fetched_at: datetime) -> Feed:
    """Validate the source hierarchy while preserving field names and values."""
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise InvalidFeed("Expected an object with a results array")
    if not payload["results"]:
        raise InvalidFeed("The results array is empty")
    stations = []
    codes = set()
    for station in payload["results"]:
        if not isinstance(station, dict):
            raise InvalidFeed("Invalid station record")
        code = _text(station.get("consideredStation"), "consideredStation")
        if code in codes:
            raise InvalidFeed("Duplicate station")
        codes.add(code)
        if not isinstance(station.get("destinations"), list):
            raise InvalidFeed("Expected destinations array")
        destinations = []
        labels = set()
        for destination in station["destinations"]:
            if not isinstance(destination, dict):
                raise InvalidFeed("Invalid destination record")
            label = _text(destination.get("label"), "label")
            if label in labels:
                raise InvalidFeed("Duplicate station/direction")
            labels.add(label)
            if not isinstance(destination.get("messages"), list):
                raise InvalidFeed("Expected messages array")
            messages = []
            for message in destination["messages"]:
                if not isinstance(message, dict):
                    raise InvalidFeed("Invalid arrival record")
                messages.append(
                    Arrival(
                        target=_text(message.get("target"), "target"),
                        secondsToArrival=message.get("secondsToArrival"),
                        arrivalTimeMessage=_text(
                            message.get("arrivalTimeMessage"), "arrivalTimeMessage"
                        ),
                        lineColor=message.get("lineColor"),
                        headSign=message.get("headSign"),
                        lastUpdated=message.get("lastUpdated"),
                        raw_data=dict(message),
                    )
                )
            destinations.append(Destination(label, tuple(messages)))
        stations.append(Station(code, tuple(destinations)))
    return Feed(tuple(stations), fetched_at)
