from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


os.environ["APP_ENV"] = "test"
os.environ["INTOPIA_BACKEND"] = "memory"
os.environ["APP_REQUIRE_AUTH"] = "false"

import db  # noqa: E402
from cloud import InMemoryCloudStore, set_store_for_tests  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_cloud_store():
    store = InMemoryCloudStore()
    set_store_for_tests(store)
    db.init_db()
    yield store
    set_store_for_tests(None)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
