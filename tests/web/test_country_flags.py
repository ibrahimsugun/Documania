"""10.1.6 — bayrak simgeleri panelin statik dosyalarındadır ve oturumsuz açıktır (tm 142)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web.auth import get_current_user


@pytest.fixture
def anonymous(app: FastAPI) -> Iterator[TestClient]:
    """Gerçek oturum denetimiyle istemci: conftest'in hazır kullanıcısı kaldırılır."""
    del app.dependency_overrides[get_current_user]
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("name", ["ru", "tr", "de", "gb", "xk"])
def test_flag_is_served_without_a_session(anonymous: TestClient, name: str) -> None:
    response = anonymous.get(f"/static/flags/{name}.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.text.lstrip().startswith("<svg")


def test_unknown_flag_is_not_found(anonymous: TestClient) -> None:
    assert anonymous.get("/static/flags/zz.svg").status_code == 404
