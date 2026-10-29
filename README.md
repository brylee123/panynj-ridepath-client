# panynj-ridepath-client

Independent asynchronous Python client for the public Port Authority PATH feeds.
Unofficial: not affiliated with or endorsed by PANYNJ. Python 3.14.2 or newer.

## Installation

```sh
pip install panynj-ridepath-client
```

## Usage

```python
import asyncio
import aiohttp
from panynj_ridepath import RidePathClient, CannotConnect, InvalidFeed, RateLimited

async def main():
    async with aiohttp.ClientSession() as session:
        client = RidePathClient(session)
        arrivals = await client.async_fetch()
        for station in arrivals.results:
            for direction in station.destinations:
                for train in direction.messages:
                    print(station.consideredStation, direction.label,
                          train.target, train.arrivalTimeMessage)
        alerts = await client.async_fetch_alerts()
        planned = await client.async_fetch_planned()
        site = await client.async_fetch_site()
        print(len(alerts.records), len(planned.records), site.fetched_at)

asyncio.run(main())
```

The caller owns and closes the aiohttp session. Reuse the client across polls so
its per-resource Retry-After deadlines remain effective. No background polling,
Home Assistant dependency, authentication, or telemetry is included.

## Responses and semantics

* `async_fetch()`: `Feed.results` contains `Station.consideredStation`,
  `destinations`, direction `label`, and ordered `messages`. Arrival fields retain
  the upstream names and values: `target`, `secondsToArrival`,
  `arrivalTimeMessage`, `lineColor`, `headSign`, `lastUpdated`, and `raw_data`.
* `async_fetch_alerts()`: `AnnouncementFeed.records` retains validated source
  dictionaries. The endpoint's default window is eight hours. Records can include
  old revisions, resolutions, accessibility notices, and duplicate incidents.
* `async_fetch_planned()`: retrieves the content-fragment listing, following at
  most ten same-resource pagination pages. Records are raw CMS dictionaries;
  callers must apply publication dates and flags before displaying notices.
* `async_fetch_site()`: `SiteFeed.page_model` and `.config` retain the website's
  page model and trip configuration. This method makes two GET requests.

Every response includes an aware UTC `fetched_at`. This is receipt time, not an
upstream train observation time. Numeric seconds can disagree with arrival text;
the client does not turn that value into a trustworthy countdown or infer delay.
No endpoint supplies a structured real-time status enum for each train line.
The library does not infer Good Service, Suspended, Delayed, or Not Scheduled.

## Endpoints

* https://www.panynj.gov/bin/portauthority/ridepath.json
* https://www.panynj.gov/bin/portauthority/alerts?agency=PATH&hours=8
* https://www.panynj.gov/api/assets/path/planned-services.json
* https://www.panynj.gov/content/path/en/index.model.json
* https://www.panynj.gov/content/dam/path/trip-planner/trip-planner-config.json

These public website endpoints have no published stability guarantee. Schema
changes raise `InvalidFeed` (a `ValueError`); network/HTTP/decoding failures raise
`CannotConnect`. `RateLimited`, a `CannotConnect` subclass, exposes `.seconds`.
Requests have a ten-second total timeout and a 1 MiB decoded response limit.
There are no immediate retries. After Retry-After, the caller decides when to
poll again. A failed request must not be interpreted as an empty all-clear feed.

Raw record dictionaries are copied shallowly and should be treated as read-only.
Missing optional arrival fields are retained as `None`. No timezone conversion,
HTML rendering, incident deduplication, calendar inference, or freshness policy
is performed. Those decisions belong to the consuming application.

## Development and releases

```sh
python -m pip install -e '.[test]' build twine
ruff check .
pytest
python -m build
python -m twine check dist/*
```

Tests use captured fixtures and local HTTP servers; they never require the live
service. GitHub Actions builds and checks every pull request and main push.
A published GitHub release named `vX.Y.Z` must match `pyproject.toml`; that workflow
publishes the tested wheel and source distribution to PyPI through OIDC Trusted
Publishing in the `pypi` environment. No long-lived upload token is used.

Code is MIT licensed. Captured feed excerpts are test data, not a claim of
ownership of Port Authority content. Live content remains the provider's.
