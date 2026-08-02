"""Route-label cardinality guard: unmatched paths collapse to one sentinel series."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from llamatrade_telemetry import init_telemetry
from llamatrade_telemetry.instrumentation.http import UNMATCHED_ROUTE
from tests.conftest import scrape


class FakeConnectApp:
    """Root-mounted RPC app shaped like a generated Connect application."""

    RPC_PATH = "/llamatrade.UnmatchedTestService/Do"

    @property
    def path(self) -> str:
        return "/llamatrade.UnmatchedTestService"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        status = 200 if scope["path"] == self.RPC_PATH else 404
        await Response(status_code=status)(scope, receive, send)


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()

    @application.get("/unmatched-known")
    async def known() -> dict[str, bool]:
        return {"ok": True}

    @application.get("/unmatched-things/{thing_id}")
    async def thing(thing_id: str) -> dict[str, str]:
        raise HTTPException(status_code=404)

    application.mount("/", FakeConnectApp())
    init_telemetry(application, service="unmatched", version="0.0.0")
    return application


async def test_unknown_path_labeled_unmatched(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        r = await client.get("/wp-login.php")
        assert r.status_code == 404

    out = scrape()
    assert f'route="{UNMATCHED_ROUTE}"' in out
    assert 'route="/wp-login.php"' not in out


async def test_dotted_scanner_path_labeled_unmatched(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.get("/.git/config")).status_code == 404

    out = scrape()
    assert 'route="/.git/config"' not in out


async def test_registered_route_keeps_raw_path(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.get("/unmatched-known")).status_code == 200

    out = scrape()
    assert (
        'llamatrade_http_requests_total{method="GET",route="/unmatched-known",'
        'status_class="2xx",status_code="200",transport="http"} 1.0' in out
    )


async def test_registered_route_404_keeps_raw_path(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.get("/unmatched-things/42")).status_code == 404

    out = scrape()
    assert 'route="/unmatched-things/42"' in out


async def test_mounted_rpc_path_keeps_raw_path(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.post(FakeConnectApp.RPC_PATH)).status_code == 200

    out = scrape()
    assert f'route="{FakeConnectApp.RPC_PATH}"' in out


async def test_unknown_method_on_mounted_prefix_keeps_raw_path(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        r = await client.post("/llamatrade.UnmatchedTestService/Nope")
        assert r.status_code == 404

    out = scrape()
    assert 'route="/llamatrade.UnmatchedTestService/Nope"' in out
