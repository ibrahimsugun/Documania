"""10.1.11 — giriş kaydı (`login_log`) ve erişim logunun "Girişler" sekmesi (PLAN.md §D125).

Girişler gerçek yoldan (`POST /login`, `POST /logout`) yazılır; IP kuralı `client_ip` üzerinde,
görünüm root olarak `TestClient` ile sınanır (İK/Kullanıcı'nın 404'ü `tests/web/test_roles.py`'de).
Kullanıcılar ve parolalar sentetiktir; ağ ya da yapay zekâ çağrısı yoktur.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.config import Settings, get_settings
from app.db.models import LoginLog, User, UserRole, UserSession, utcnow
from app.web.auth import (
    SESSION_COOKIE,
    PanelUser,
    client_ip,
    create_user,
    get_current_user,
    set_user_active,
)
from app.web.routers.access_log import PAGE_SIZE
from app.web.routers.auth import LOGIN_FAILED
from tests.web.conftest import SIGNED_IN

PASSWORD = "gizli-parola-190"
SETTINGS = Settings(_env_file=None, database_url="sqlite://")
LOOPBACK = SETTINGS.trusted_proxy_networks
ROOT = PanelUser(id=SIGNED_IN.id, username=SIGNED_IN.username, role="root")


@pytest.fixture
def real_login(app: FastAPI, session_factory: sessionmaker[Session]) -> dict[str, int]:
    """Gerçek oturumla giriş: `ayse` etkin İK, `pasif` pasife alınmış Kullanıcı."""
    del app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    with session_factory() as session:
        ayse = create_user(session, "ayse", PASSWORD)
        pasif = create_user(session, "pasif", PASSWORD, role=UserRole.USER)
        session.flush()
        actor = PanelUser(id=SIGNED_IN.id, username=SIGNED_IN.username, role="hr")
        set_user_active(session, pasif, False, actor=actor)
        session.commit()
        return {"ayse": ayse.id, "pasif": pasif.id}


def _login(client: TestClient, username: str, password: str, **headers: str):  # noqa: ANN202
    return client.post(
        "/login",
        data={"username": username, "password": password},
        headers=headers,
        follow_redirects=False,
    )


def _log(session_factory: sessionmaker[Session]) -> list[LoginLog]:
    with session_factory() as session:
        return list(session.scalars(select(LoginLog).order_by(LoginLog.id)))


def test_every_attempt_and_logout_is_recorded_with_its_reason_but_the_page_says_nothing(
    client: TestClient, session_factory: sessionmaker[Session], real_login: dict[str, int]
) -> None:
    long_name = "x" * 80
    agent = "Mozilla/5.0 " + "A" * 300
    failures = [
        _login(client, "ayse", "yanlis-parola-1"),
        _login(client, f"  {long_name} ", PASSWORD),
        _login(client, "pasif", PASSWORD),
        _login(client, "pasif", "yanlis-parola-1"),
    ]
    signed_in = _login(client, " ayse ", PASSWORD, **{"User-Agent": agent})
    token = signed_in.cookies[SESSION_COOKIE]
    out = client.post("/logout", follow_redirects=False)

    assert signed_in.status_code == out.status_code == 303
    # 10.1.4: dört başarısızlığın yanıtı aynı — tek metin, 401, neden sayfada yok.
    pages = {re.sub(r'value="[^"]*"', "", page.text) for page in failures}
    assert [page.status_code for page in failures] == [401] * 4
    assert len(pages) == 1
    page = pages.pop()
    assert LOGIN_FAILED in page
    for word in ("unknown_user", "wrong_password", "inactive", "Yanlış parola", "Pasif"):
        assert word not in page

    rows = _log(session_factory)
    ayse, pasif = real_login["ayse"], real_login["pasif"]
    assert [(r.username, r.user_id, r.outcome, r.reason) for r in rows] == [
        ("ayse", ayse, "failed", "wrong_password"),
        ("x" * 64, None, "failed", "unknown_user"),
        ("pasif", pasif, "failed", "inactive"),
        ("pasif", pasif, "failed", "wrong_password"),
        ("ayse", ayse, "success", None),
        ("ayse", ayse, "logout", None),
    ]
    assert len(rows[4].user_agent) == 255 and rows[4].user_agent.startswith("Mozilla/5.0")
    # TestClient'ın bağlantı adresi geri döngü değil: başlık yok, bağlantının kendisi yazılır.
    assert {row.ip for row in rows} == {"testclient"}
    # Parola ve oturum belirteci hiçbir sütunda yok.
    values = " ".join(str(value) for row in rows for value in vars(row).values())
    for secret in (PASSWORD, "yanlis-parola-1", token):
        assert secret not in values


def test_logout_without_an_open_session_and_a_previous_session_are_not_logouts(
    client: TestClient, session_factory: sessionmaker[Session], real_login: dict[str, int]
) -> None:
    client.post("/logout", follow_redirects=False)
    _login(client, "ayse", PASSWORD)
    _login(client, "ayse", PASSWORD)  # tarayıcıdaki önceki oturum kapanır — çıkış sayılmaz

    assert [row.outcome for row in _log(session_factory)] == ["success", "success"]


def _request(peer: str | None, **headers: str) -> Request:
    return Request(
        {
            "type": "http",
            "client": (peer, 1234) if peer else None,
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        }
    )


@pytest.mark.parametrize(
    ("peer", "headers", "expected"),
    [
        (
            "127.0.0.1",
            {"CF-Connecting-IP": "203.0.113.9", "X-Forwarded-For": "1.1.1.1"},
            "203.0.113.9",
        ),
        ("::1", {"X-Forwarded-For": " 2001:db8::5 , 10.0.0.1"}, "2001:db8::5"),
        ("::ffff:127.0.0.1", {"X-Forwarded-For": "198.51.100.4"}, "198.51.100.4"),
        ("127.0.0.1", {"CF-Connecting-IP": "bozuk", "X-Forwarded-For": "yok"}, "127.0.0.1"),
        (
            "127.0.0.1",
            {"CF-Connecting-IP": "bozuk", "X-Forwarded-For": "198.51.100.4"},
            "198.51.100.4",
        ),
        (
            "203.0.113.50",
            {"CF-Connecting-IP": "1.2.3.4", "X-Forwarded-For": "5.6.7.8"},
            "203.0.113.50",
        ),
        (None, {"X-Forwarded-For": "5.6.7.8"}, None),
    ],
    ids=["cf", "xff-v6", "mapped", "garbage", "cf-garbage", "outside", "no-peer"],
)
def test_proxy_headers_count_only_when_the_connection_comes_from_loopback(
    peer: str | None, headers: dict[str, str], expected: str | None
) -> None:
    assert client_ip(_request(peer, **headers), LOOPBACK) == expected


def test_trusted_proxies_can_widen_or_empty_the_list() -> None:
    compose = Settings(_env_file=None, database_url="sqlite://", trusted_proxies="172.16.0.0/12")
    request = _request("172.18.0.1", **{"CF-Connecting-IP": "203.0.113.9"})

    assert client_ip(request, compose.trusted_proxy_networks) == "203.0.113.9"
    assert (
        Settings(
            _env_file=None, database_url="sqlite://", trusted_proxies=""
        ).trusted_proxy_networks
        == ()
    )
    with pytest.raises(ValueError, match="TRUSTED_PROXIES"):
        Settings(_env_file=None, database_url="sqlite://", trusted_proxies="127.0.0.1,yerel")


def test_a_log_that_cannot_be_written_never_blocks_login_or_logout(
    client: TestClient,
    engine: Engine,
    session_factory: sessionmaker[Session],
    real_login: dict[str, int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE login_log"))

    with caplog.at_level(logging.WARNING):
        failed = _login(client, "ayse", "yanlis-parola-1")
        signed_in = _login(client, "ayse", PASSWORD)
        out = client.post("/logout", follow_redirects=False)

    assert (failed.status_code, signed_in.status_code, out.status_code) == (401, 303, 303)
    with session_factory() as session:
        opened = session.scalars(select(UserSession)).one()
        assert opened.revoked_at is not None
    warnings = [
        record.getMessage() for record in caplog.records if "giriş kaydı" in record.getMessage()
    ]
    assert len(warnings) == 3
    assert not any("ayse" in message or PASSWORD in message for message in warnings)


# --- Girişler sekmesi (yalnız root) ------------------------------------------------------------


@pytest.fixture
def as_root(app: FastAPI, session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.get_one(User, ROOT.id).role = "root"
        session.add(User(id=2, username="zeynep", password_hash="yok", role="hr"))
        session.commit()
    app.dependency_overrides[get_current_user] = lambda: ROOT


def _rows(html: str, name: str) -> list[list[str]]:
    table = re.search(rf'<table class="{name}">(.*?)</table>', html, re.S)
    assert table is not None, name
    body = re.search(r"<tbody>(.*?)</tbody>", table.group(1), re.S).group(1)
    return [
        [
            re.sub(r"<[^>]+>", "", cell).strip()
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        ]
        for row in re.findall(r"<tr>(.*?)</tr>", body, re.S)
    ]


def test_the_logins_tab_lists_newest_first_with_summary_and_filters(
    client: TestClient, session_factory: sessionmaker[Session], as_root: None
) -> None:
    now = utcnow()
    me = {"username": ROOT.username, "user_id": ROOT.id}
    with session_factory() as session:
        session.add_all(
            [
                LoginLog(
                    ts=now - timedelta(days=3), **me, outcome="failed", reason="wrong_password"
                ),
                LoginLog(
                    ts=now - timedelta(hours=2), **me, outcome="failed", reason="wrong_password"
                ),
                LoginLog(ts=now - timedelta(hours=1), **me, outcome="success", ip="203.0.113.7"),
                LoginLog(
                    ts=now - timedelta(minutes=30), username="zeynep", user_id=2, outcome="logout"
                ),
                LoginLog(
                    ts=now - timedelta(minutes=5),
                    username="<b>ghost</b>",
                    outcome="failed",
                    reason="unknown_user",
                ),
            ]
        )
        session.commit()

    html = client.get("/access-log/logins").text

    assert '<a href="/access-log/logins" class="active" aria-current="page">Girişler</a>' in html
    entries = _rows(html, "login-log")
    assert [row[1:4] for row in entries] == [
        ["&lt;b&gt;ghost&lt;/b&gt; bilinmeyen", "Başarısız", "Bilinmeyen kullanıcı adı"],
        ["zeynep", "Çıkış", "—"],
        [ROOT.username, "Başarılı", "—"],
        [ROOT.username, "Başarısız", "Yanlış parola"],
        [ROOT.username, "Başarısız", "Yanlış parola"],
    ]
    assert entries[2][4] == "203.0.113.7"
    summary = _rows(html, "login-summary")
    assert [row[0] for row in summary] == [ROOT.username, "zeynep", "Bilinmeyen adlar"]
    assert summary[0][1].endswith("UTC") and summary[0][2] == "1"  # 3 gün önceki sayılmaz
    assert summary[1][1:] == ["—", "0"] and summary[2][1:] == ["—", "1"]

    failed = _rows(client.get("/access-log/logins?outcome=failed").text, "login-log")
    assert len(failed) == 3
    mine = client.get(f"/access-log/logins?outcome=failed&user={ROOT.id}").text
    assert len(_rows(mine, "login-log")) == 2
    assert '<input type="hidden" name="outcome" value="failed">' in mine
    assert f'href="/access-log/logins?outcome=success&amp;user={ROOT.id}"' in mine
    unknown = _rows(client.get("/access-log/logins?user=unknown").text, "login-log")
    assert [row[1] for row in unknown] == ["&lt;b&gt;ghost&lt;/b&gt; bilinmeyen"]
    # Tanınmayan süzgeç "tümü" sayılır.
    assert len(_rows(client.get("/access-log/logins?outcome=x&user=99").text, "login-log")) == 5


def test_the_logins_tab_pages_by_fifty_and_both_tabs_show_the_switch(
    client: TestClient, session_factory: sessionmaker[Session], as_root: None
) -> None:
    now = utcnow()
    with session_factory() as session:
        session.add_all(
            LoginLog(ts=now - timedelta(seconds=i), username="zeynep", user_id=2, outcome="success")
            for i in range(PAGE_SIZE + 1)
        )
        session.commit()

    first = client.get("/access-log/logins").text
    second = client.get("/access-log/logins?page=2").text
    documents = client.get("/access-log").text

    assert len(_rows(first, "login-log")) == PAGE_SIZE
    assert len(_rows(second, "login-log")) == 1
    assert 'href="/access-log/logins?page=2"' in first
    assert (
        '<a href="/access-log" class="active" aria-current="page">Belge erişimleri</a>' in documents
    )
    assert '<a href="/access-log/logins">Girişler</a>' in documents


def test_an_empty_log_shows_the_empty_state(client: TestClient, as_root: None) -> None:
    html = client.get("/access-log/logins").text

    assert "Henüz giriş kaydı yok." in html
    assert 'class="login-summary"' not in html
