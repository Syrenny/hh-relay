from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from hh_relay.app import app


@pytest.fixture(scope="session")
def asgi_client() -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client
