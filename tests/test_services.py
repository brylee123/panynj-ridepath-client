"""Real HTTP transport and bounded planned-service pagination."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aiohttp import web

from panynj_ridepath import InvalidFeed, RateLimited, RidePathClient
from panynj_ridepath import client as library_client


@pytest.fixture
async def services_endpoint(aiohttp_server, monkeypatch, socket_enabled, service_fixtures, payload):
    records = []
    responses = {
        "/arrivals": payload,
        "/alerts": service_fixtures["alerts-live"],
        "/planned": service_fixtures["planned-live"],
        "/model": service_fixtures["index-model"],
        "/config": service_fixtures["trip-config"],
    }

    async def handler(request):
        records.append((request.method, request.path))
        value = responses[request.path]
        return value if isinstance(value, web.Response) else web.json_response(value)

    app = web.Application()
    app.router.add_get("/{resource}", handler)
    server = await aiohttp_server(app)
    for constant, resource in [
        ("FEED_URL", "arrivals"),
        ("ALERTS_URL", "alerts"),
        ("PLANNED_URL", "planned"),
        ("SITE_MODEL_URL", "model"),
        ("SITE_CONFIG_URL", "config"),
    ]:
        monkeypatch.setattr(library_client, constant, str(server.make_url("/" + resource)))
    return responses, records


async def test_all_new_resources_use_get_and_preserve_source(services_endpoint):
    _, requests = services_endpoint
    async with aiohttp.ClientSession() as session:
        client = RidePathClient(session)
        alerts = await client.async_fetch_alerts()
        planned = await client.async_fetch_planned()
        site = await client.async_fetch_site()
    assert len(alerts.records) == 8
    assert len(planned.records) == 1
    assert site.config["lines"]["red"]["origin"] == "Newark"
    assert requests == [
        ("GET", "/alerts"),
        ("GET", "/planned"),
        ("GET", "/model"),
        ("GET", "/config"),
    ]


async def test_alert_rate_limit_does_not_block_other_resources(services_endpoint):
    responses, requests = services_endpoint
    responses["/alerts"] = web.Response(status=429, headers={"Retry-After": "600"})
    async with aiohttp.ClientSession() as session:
        client = RidePathClient(session)
        for _ in range(2):
            with pytest.raises(RateLimited):
                await client.async_fetch_alerts()
        assert len((await client.async_fetch()).results) == 13
    assert requests == [("GET", "/alerts"), ("GET", "/arrivals")]


async def test_safe_planned_pagination(service_fixtures):
    page1 = deepcopy(service_fixtures["planned-live"])
    page2 = deepcopy(page1)
    page1["properties"]["srn:paging"]["total"] = 2
    page1["links"].append(
        {
            "rel": ["next"],
            "href": "https://www.panynj.gov/api/assets/path/planned-services.json?offset=1",
        }
    )
    page2["properties"]["name"] = "page2"
    page2["entities"][0]["properties"]["name"] = "second-notice"
    async with aiohttp.ClientSession() as session:
        client = RidePathClient(session)
        with patch.object(
            client, "_async_get_json", new=AsyncMock(side_effect=[page1, page2])
        ) as fetch:
            result = await client.async_fetch_planned()
    assert len(result.records) == 2
    assert fetch.await_count == 2


@pytest.mark.parametrize(
    "href",
    [
        "https://other.example/steal",
        "https://www.panynj.gov/api/assets/path/other.json",
        "javascript:alert(1)",
    ],
)
async def test_unsafe_next_link_rejected(service_fixtures, href):
    page = deepcopy(service_fixtures["planned-live"])
    page["links"] = [{"rel": ["next"], "href": href}]
    async with aiohttp.ClientSession() as session:
        client = RidePathClient(session)
        with patch.object(client, "_async_get_json", return_value=page) as fetch:
            with pytest.raises(InvalidFeed, match="Unexpected"):
                await client.async_fetch_planned()
            assert fetch.await_count == 1


async def test_incomplete_planned_listing_is_not_an_empty_all_clear(service_fixtures):
    page = deepcopy(service_fixtures["planned-live"])
    page["properties"]["srn:paging"]["total"] = 99
    async with aiohttp.ClientSession() as session:
        client = RidePathClient(session)
        with patch.object(client, "_async_get_json", return_value=page):
            with pytest.raises(InvalidFeed, match="Incomplete"):
                await client.async_fetch_planned()
