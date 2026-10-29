from datetime import UTC, datetime

import pytest

from panynj_ridepath import InvalidFeed, parse_response


def test_source_fields(payload):
    feed = parse_response(payload, datetime.now(UTC))
    assert len(feed.results) == 13
    station = next(item for item in feed.results if item.consideredStation == "NEW")
    message = station.destinations[1].messages[0]
    assert message.arrivalTimeMessage == "Delayed"
    assert message.secondsToArrival == "199"
    assert not hasattr(message, "delayed")

@pytest.mark.parametrize("value", [None, {}, {"results": []}, {"results": [None]}])
def test_invalid_feed(value):
    with pytest.raises(InvalidFeed):
        parse_response(value, datetime.now(UTC))
