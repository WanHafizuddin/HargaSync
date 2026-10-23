"""Test helpers: a TestClient on a throwaway data dir with the demo seed loaded."""

import re
import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from hargasync.app import create_app
from hargasync.config import Settings
from hargasync.db import connect
from hargasync.extraction import DisabledExtractor

PASSWORD = "test-pass-123"


def make_client(testcase, extractor=None):
    tmp = tempfile.mkdtemp(prefix="hargasync-test-")
    testcase.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
    settings = Settings(
        data_dir=Path(tmp), secret_key="test-secret", ai_mode="off", runpod_api_key="", runpod_endpoint_id="",
        demo_seed=True, demo_password=PASSWORD, https_only=False,
    )
    client = TestClient(create_app(settings, extractor=extractor or DisabledExtractor()))
    testcase.addCleanup(client.close)
    return client, settings


def open_db(testcase, settings):
    conn = connect(settings.data_dir / "hargasync.db")
    testcase.addCleanup(conn.close)
    return conn


def csrf(client, path="/login"):
    page = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match, f"no csrf token on {path}"
    return match.group(1)


def login(client, username):
    response = client.post(
        "/login",
        data={"username": username, "password": PASSWORD, "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response
