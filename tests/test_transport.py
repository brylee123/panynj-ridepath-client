"""Real aiohttp requests to a local test server, without the public endpoint."""

import asyncio
import json
from unittest.mock import patch

import aiohttp
import pytest
from aiohttp import web

from panynj_ridepath import CannotConnect, InvalidFeed, RateLimited
from panynj_ridepath import RidePathClient as PathApi
from panynj_ridepath.const import MAX_RESPONSE_BYTES


@pytest.fixture
async def endpoint(aiohttp_server, monkeypatch, socket_enabled):
    """Redirect only this test module's API endpoint to localhost."""
    responses = []
    calls = []

    async def handler(request):
        calls.append(request)
        return responses.pop(0)

    app = web.Application()
    app.router.add_get("/feed", handler)
    server = await aiohttp_server(app)
    monkeypatch.setattr(
        "panynj_ridepath.client.FEED_URL",
        str(server.make_url("/feed")),
    )
    return responses, calls


async def test_fetch_ignores_wrong_content_type(payload, endpoint):
    responses, calls = endpoint
    responses.append(web.Response(text=json.dumps(payload), content_type="text/plain"))
    async with aiohttp.ClientSession() as session:
        assert len((await PathApi(session).async_fetch()).results) == 13
    assert len(calls) == 1


@pytest.mark.parametrize("status", [403, 404, 500])
async def test_http_errors(status, endpoint):
    responses, _ = endpoint
    responses.append(web.Response(status=status))
    async with aiohttp.ClientSession() as session:
        with pytest.raises(CannotConnect):
            await PathApi(session).async_fetch()


async def test_timeout():
    async with aiohttp.ClientSession() as session:
        with patch.object(session, "get", side_effect=TimeoutError()):
            with pytest.raises(CannotConnect):
                await PathApi(session).async_fetch()


@pytest.mark.parametrize("oversize", [False, True], ids=["invalid_json", "oversize"])
async def test_invalid_and_oversize_response(oversize, endpoint):
    responses, _ = endpoint
    body = "x" * (MAX_RESPONSE_BYTES + 1) if oversize else "<html>error</html>"
    responses.append(web.Response(text=body))
    async with aiohttp.ClientSession() as session:
        with pytest.raises(InvalidFeed):
            await PathApi(session).async_fetch()


async def test_rate_limit_prevents_early_network_retry(endpoint):
    responses, calls = endpoint
    responses.append(web.Response(status=429, headers={"Retry-After": "120"}))
    async with aiohttp.ClientSession() as session:
        api = PathApi(session)
        for _ in range(2):
            with pytest.raises(RateLimited) as raised:
                await api.async_fetch()
            assert 110 < raised.value.seconds <= 120
    assert len(calls) == 1


async def test_cancel_is_not_swallowed():
    async with aiohttp.ClientSession() as session:
        with patch.object(session, "get", side_effect=asyncio.CancelledError()):
            with pytest.raises(asyncio.CancelledError):
                await PathApi(session).async_fetch()
