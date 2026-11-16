"""The ASGI bridge the browser's Web Worker uses to call the app."""

import asyncio
import json

from app import browser
from app.config import Settings


def test_handle_calls_the_app_without_a_server(tmp_path):
    browser.boot(str(tmp_path), str(Settings().risk_rules_path))

    status, headers, body = asyncio.run(browser.handle("GET", "/api/health", [], b""))
    assert status == 200
    assert json.loads(body) == {"status": "ok"}

    request = json.dumps({"text": "Utgångspris 2 950 000 kr\nBoarea 54 m²\nAvgift 3 200 kr/mån"}).encode()
    status, _, body = asyncio.run(browser.handle(
        "POST", "/api/properties/from-text", [["Content-Type", "application/json"]], request))
    assert status == 201
    assert json.loads(body)["fields"][3]["value"] == 2_950_000

    status, _, body = asyncio.run(browser.handle("GET", "/api/comparisons/cooperatives?ids=1", [], b""))
    assert status == 422  # The query string reaches the app.
    assert (tmp_path / "boster.db").exists()
