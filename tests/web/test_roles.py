"""10.1.8, 10.1.9 — yetki seviyeleri: Root (gizli, tek), İK, Kullanıcı (salt okunur); erişim logu
yalnız root (PLAN.md §D115).

Kapı sunucudadır: `app.main` her yönlendiriciye yazma kapısını (`panel_write_gate`,
`api_write_gate`) bağlar; yalnız yazmaya götüren `GET` sayfaları `WRITER_ONLY` taşır, erişim logu
`require_root`. Yapısal tarama (`effective_route_contexts`) yeni eklenen her yazan yolun kapıda
olduğunu, davranış taraması Kullanıcı'nın her yazan isteğinin 403 aldığını ve hiçbir şeyin
değişmediğini gösterir. Sayfa taraması `tests/web/test_translation_sweep.py`'nin sentetik dünyasını
Kullanıcı olarak gezer: yazma formu, düğmesi ve yazmaya götüren bağlantı yoktur. Veri sentetiktir;
gerçek kimlik belgesi ve canlı yapay zekâ çağrısı yoktur.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Event, TelegramUser, User, UserRole
from app.main import create_app
from app.storage import DataLayout
from app.web.auth import (
    LAST_ACTIVE_HR,
    READ_ONLY,
    SESSION_COOKIE,
    PanelUser,
    RootExistsError,
    RootTargetError,
    UserStatusError,
    api_write_gate,
    create_root,
    create_user,
    get_current_user,
    hash_password,
    panel_write_gate,
    require_root,
    require_writer,
    reset_password,
    set_user_active,
    set_user_role,
)
from app.web.routers.training import get_training_provider_problem
from tests.web import test_translation_sweep as sweep
from tests.web.conftest import SIGNED_IN

world = sweep.world

PASSWORD = "sentetik-rol-parolasi"
HR = SIGNED_IN
READER = PanelUser(SIGNED_IN.id, SIGNED_IN.username, UserRole.USER.value)
ROOT = PanelUser(SIGNED_IN.id, SIGNED_IN.username, UserRole.ROOT.value)

# Yazma kapısının dışındaki yazan yollar (§D115 c): giriş/çıkış, dil seçici, kişinin kendi hesabı.
OPEN_WRITES = frozenset(
    {
        ("POST", "/login"),
        ("POST", "/logout"),
        ("POST", "/language"),
        ("POST", "/account/password"),
        ("POST", "/account/telegram"),
        ("POST", "/account/telegram/{telegram_id}/status"),
        ("POST", "/account/telegram/{telegram_id}/delete"),
        ("POST", "/account/telegram/link"),
    }
)
# Yalnız yazmaya götüren `GET` sayfaları: form, arama ve iki aşamalı onayın ilk adımı.
WRITER_ONLY_PAGES = frozenset(
    {
        "/upload",
        "/employees/{employee_id}/fields",
        "/employees/{employee_id}/status/confirm",
        "/employees/{employee_id}/delete/confirm",
        "/employees/{employee_id}/records/{kind}/{record_id}/remove/confirm",
        "/employees/{employee_id}/merge/employees",
        "/employees/{employee_id}/merge/confirm",
        "/documents/{document_id}/move/employees",
        "/documents/{document_id}/move/confirm",
        "/documents/{document_id}/archive/confirm",
        "/documents/{document_id}/unarchive/confirm",
        "/documents/{document_id}/delete/confirm",
        "/document-types/new",
        "/document-types/{slug}/archive/confirm",
        "/document-groups/new",
        "/queues/{queue_item_id}/assign/employees",
        "/queues/{queue_item_id}/assign/confirm",
        "/queues/{queue_item_id}/close/confirm",
    }
)
ROOT_ONLY_PAGES = frozenset({"/access-log", "/access-log/employees/{employee_id}"})
# Davranış taramasında yol parametreleri: sentetik dünyadaki gerçek kayıtlar (403 "kayıt yok"tan
# değil kapıdan gelsin).
WORLD_PARAMS = {
    "upload_id": "{unknown_upload}",
    "queue_item_id": "{unresolved_item}",
    "document_id": "{document}",
    "employee_id": "E0001",
    "slug": "russian_passport",
    "candidate_id": "{candidate}",
    "group_id": "{group}",
    "item_id": "1",
    "package_id": "1",
    "kind": "alias",
    "record_id": "{alias}",
    "user_id": "1",
    "telegram_id": "1",
    "example_id": "1",
    "run_id": "1",
}

POST_TARGET = re.compile(r'method="post"\s+action="([^"]+)"')
HX_POST = re.compile(r'hx-post="([^"]+)"')
FORMACTION = re.compile(r'formaction="([^"]+)"')
LINK = re.compile(r'(?:href|hx-get)="(/[^"#]*)"')


def _pattern(path: str) -> re.Pattern[str]:
    return re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path)) + "$")


OPEN_TARGETS = [_pattern(path) for _, path in OPEN_WRITES]
WRITER_LINKS = [_pattern(path) for path in WRITER_ONLY_PAGES | ROOT_ONLY_PAGES]


def _contexts(application: FastAPI) -> Iterator[Any]:
    for route in application.routes:
        if hasattr(route, "effective_route_contexts"):
            yield from route.effective_route_contexts()
        elif isinstance(route, APIRoute):
            yield route


def _calls(dependant: Any) -> set[Any]:
    found: set[Any] = set()
    for dependency in dependant.dependencies:
        found.add(dependency.call)
        found |= _calls(dependency)
    return found


def _mutating(application: FastAPI) -> dict[tuple[str, str], set[Any]]:
    return {
        (method, context.path): _calls(context.dependant)
        for context in _contexts(application)
        for method in context.methods
        if method not in {"GET", "HEAD", "OPTIONS"}
    }


def _write_controls(html: str) -> set[str]:
    """Sayfadaki yazma denetimleri: kapı dışı olmayan form hedefi, `hx-post`, `formaction` ve
    yazmaya götüren (ya da root'a ayrılmış) sayfa bağlantısı."""
    found = {
        target
        for target in POST_TARGET.findall(html)
        if not any(pattern.match(target) for pattern in OPEN_TARGETS)
    }
    found |= {f"hx-post {target}" for target in HX_POST.findall(html)}
    found |= {f"formaction {target}" for target in FORMACTION.findall(html)}
    found |= {
        f"link {link}"
        for link in LINK.findall(html)
        if any(pattern.match(link.split("?", 1)[0]) for pattern in WRITER_LINKS)
    }
    return found


def _sign_in(app: FastAPI, user: PanelUser) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def _snapshot(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, Any]:
    """Veritabanının her tablosunun satır sayısı, son olay ve veri dizinindeki dosyalar."""
    with session_factory() as session:
        counts = {
            table.name: session.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.sorted_tables
        }
        last_event = session.scalar(select(func.max(Event.id)))
    files = sorted(
        (path.relative_to(layout.root).as_posix(), path.stat().st_size)
        for path in layout.root.rglob("*")
        if path.is_file()
    )
    return {"counts": counts, "last_event": last_event, "files": files}


def _users(session_factory: sessionmaker[Session]) -> list[tuple[str, str, bool]]:
    with session_factory() as session:
        rows = session.execute(select(User.username, User.role, User.active).order_by(User.id))
        return [(row.username, row.role, row.active) for row in rows]


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient, app: FastAPI) -> None:
    """Onay belirteci oturum çerezine bağlıdır; eğitim sekmesinin sağlayıcı notu kapalı."""
    client.cookies.set(SESSION_COOKIE, "oturum-bir")
    app.dependency_overrides[get_training_provider_problem] = lambda: None


@pytest.fixture
def zvz(session_factory: sessionmaker[Session]) -> tuple[int, int]:
    """Root `Zvz` ve onun Telegram kimliği: (kullanıcı kimliği, Telegram kimliği)."""
    with session_factory() as session:
        root = create_root(session, "Zvz", PASSWORD)
        session.add(TelegramUser(telegram_id=777_000_001, user_id=root.id, allowed=True))
        session.commit()
        return root.id, 777_000_001


# --- yapısal kapı (§D115 c) ---------------------------------------------------------------------


def test_every_writing_route_passes_the_write_gate_except_the_own_account_ones() -> None:
    routes = _mutating(create_app())

    assert set(OPEN_WRITES) <= set(routes)
    for (method, path), calls in routes.items():
        gated = panel_write_gate in calls or api_write_gate in calls
        assert gated is ((method, path) not in OPEN_WRITES), (method, path)


def test_a_new_writing_route_without_the_gate_turns_the_scan_red() -> None:
    application = create_app()
    application.add_api_route("/yeni-yazan-yol", lambda: None, methods=["POST"])

    routes = _mutating(application)
    assert not (routes[("POST", "/yeni-yazan-yol")] & {panel_write_gate, api_write_gate})


def test_write_only_pages_need_a_writer_and_the_access_log_needs_root() -> None:
    pages = {
        context.path: _calls(context.dependant)
        for context in _contexts(create_app())
        if "GET" in context.methods
    }

    assert set(sweep.PAGES) >= WRITER_ONLY_PAGES | ROOT_ONLY_PAGES
    for path, calls in pages.items():
        assert (require_writer in calls) is (path in WRITER_ONLY_PAGES), path
        assert (require_root in calls) is (path in ROOT_ONLY_PAGES), path


# --- Kullanıcı: her yazan istek 403, veri değişmez (10.1.8) -------------------------------------


def _world_path(path: str, data: dict[str, object]) -> str:
    return re.sub(r"\{(\w+)\}", lambda match: WORLD_PARAMS[match.group(1)], path).format(**data)


def test_a_read_only_user_gets_403_on_every_writing_route_and_nothing_changes(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    world: dict[str, object],
) -> None:
    _sign_in(app, READER)
    before = _snapshot(session_factory, layout)
    refused = []

    for method, path in sorted(_mutating(app)):
        if (method, path) in OPEN_WRITES:
            continue
        response = client.request(method, _world_path(path, world), data={"x": "1"})
        assert response.status_code == 403, (method, path, response.status_code)
        assert response.json() == {"detail": READ_ONLY}
        refused.append(path)

    assert len(refused) > 90
    assert _snapshot(session_factory, layout) == before


def test_hr_and_root_pass_the_write_gate(app: FastAPI) -> None:
    # Kayıt yok: istekler 404/409/422/303 döner ama hiçbiri yetki yüzünden 403 değildir.
    def ghost(match: re.Match[str]) -> str:
        return "E9999" if match.group(1) == "employee_id" else "999999"

    for user in (HR, ROOT):
        _sign_in(app, user)
        writer = TestClient(app, raise_server_exceptions=False)
        for method, path in sorted(_mutating(app)):
            response = writer.request(method, re.sub(r"\{(\w+)\}", ghost, path))
            assert response.status_code != 403, (user.role, method, path)


def test_a_read_only_user_keeps_the_own_account_and_the_language_selector(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.get_one(User, SIGNED_IN.id).password_hash = hash_password(PASSWORD)
        session.commit()
    _sign_in(app, READER)

    changed = client.post(
        "/account/password",
        data={
            "current_password": PASSWORD,
            "new_password": "yeni-sentetik-parola",
            "new_password_repeat": "yeni-sentetik-parola",
        },
        follow_redirects=False,
    )
    language = client.post(
        "/language", data={"language": "sr", "next": "/employees"}, follow_redirects=False
    )

    assert changed.status_code == 303
    assert language.status_code == 303
    with session_factory() as session:
        assert session.get_one(User, SIGNED_IN.id).language == "sr"
    assert client.get("/account/telegram").status_code == 200


# --- Kullanıcı: sayfalar salt okunur, yazma düğmesi yok (10.1.8) ---------------------------------


def test_a_read_only_user_opens_every_page_without_a_single_write_control(
    app: FastAPI, client: TestClient, world: dict[str, object]
) -> None:
    failures: list[str] = []
    hr_controls: set[str] = set()
    for route, addresses in sweep.PAGES.items():
        if route == "/login" or route in ROOT_ONLY_PAGES:
            continue
        for template, expected in addresses:
            path = template.format(**world)
            _sign_in(app, READER)
            response = client.get(path, follow_redirects=False)
            if route in WRITER_ONLY_PAGES:
                if response.status_code != 403:
                    failures.append(f"{path}: {response.status_code} (beklenen 403)")
                continue
            if response.status_code != expected:
                failures.append(f"{path}: {response.status_code} (beklenen {expected})")
                continue
            controls = _write_controls(response.text)
            if controls:
                failures.append(f"{path}: {sorted(controls)}")
            if "Yükle</a>" in response.text.split("</nav>", 1)[0]:
                failures.append(f"{path}: Yükle menüsü")
            _sign_in(app, HR)
            hr_controls |= _write_controls(client.get(path, follow_redirects=False).text)

    assert not failures, "\n".join(failures)
    # Tarama boş değil: aynı sayfalar İK'ya yazma denetimleri gösterir.
    assert len(hr_controls) > 40
    assert {"/employees/E0001/contacts", "link /upload", "link /employees/E0001/fields"} & (
        hr_controls
    )


def test_hr_sees_the_upload_menu_and_a_read_only_user_does_not(
    app: FastAPI, client: TestClient
) -> None:
    menu = re.compile(r'<nav class="menu"[^>]*>(.*?)</nav>', re.S)

    hr_menu = menu.search(client.get("/employees").text)
    _sign_in(app, READER)
    reader_menu = menu.search(client.get("/employees").text)

    assert hr_menu is not None and reader_menu is not None
    assert 'href="/upload"' in hr_menu.group(1)
    assert 'href="/upload"' not in reader_menu.group(1)


# --- erişim logu yalnız root (10.1.9) -----------------------------------------------------------


@pytest.mark.parametrize("user", [HR, READER], ids=["hr", "user"])
def test_the_access_log_is_a_404_without_a_link_for_hr_and_user(
    app: FastAPI, client: TestClient, world: dict[str, object], user: PanelUser
) -> None:
    unknown = client.get("/olmayan-bir-yol").json()
    _sign_in(app, user)

    for path in ("/access-log", "/access-log?page=0", "/access-log/employees/E0001"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.json() == unknown
    for page in ("/employees", "/employees/E0001", "/users"):
        assert "/access-log" not in client.get(page).text, page


def test_root_sees_the_access_log_its_links_and_its_own_root_label(
    app: FastAPI, client: TestClient, world: dict[str, object]
) -> None:
    opened = client.get("/employees/E0001/documents/{document}/file".format(**world))
    assert opened.status_code == 200
    _sign_in(app, ROOT)

    assert client.get("/access-log").status_code == 200
    assert client.get("/access-log/employees/E0001").status_code == 200
    profile = client.get("/employees/E0001").text
    assert 'href="/access-log/employees/E0001"' in profile
    assert 'class="tool-link" href="/access-log"' in profile
    assert '<span class="badge role-badge" translate="no">Root</span>' in profile
    for path in ("/account/password", "/account/telegram"):
        assert '<span class="badge role-badge" translate="no">Root</span>' in client.get(path).text


def test_the_root_label_is_shown_to_root_only(app: FastAPI, client: TestClient) -> None:
    for user in (HR, READER):
        _sign_in(app, user)
        for path in ("/employees", "/users", "/account/password", "/account/telegram"):
            assert "role-badge" not in client.get(path).text, (user.role, path)


# --- root gizli ve tek (10.1.8, §D115 b, d) ----------------------------------------------------


@pytest.mark.parametrize("user", [HR, ROOT, READER], ids=["hr", "root", "user"])
def test_root_is_listed_in_no_users_table_not_even_on_its_own_screen(
    app: FastAPI, client: TestClient, zvz: tuple[int, int], user: PanelUser
) -> None:
    root_id, root_telegram = zvz
    _sign_in(app, user)

    page = client.get("/users")

    assert page.status_code == 200
    assert "Zvz" not in page.text and str(root_telegram) not in page.text
    assert f'id="user-{root_id}"' not in page.text
    assert 'value="root"' not in page.text and ">Root<" not in page.text.split("</header>", 1)[1]


def test_role_choices_are_hr_and_user_only(client: TestClient) -> None:
    page = client.get("/users").text
    new_user = page.split('<select id="new-role" name="role">', 1)[1].split("</select>", 1)[0]

    assert re.findall(r'<option value="([^"]+)"', new_user) == ["hr", "user"]


@pytest.mark.parametrize("user", [HR, ROOT], ids=["hr", "root"])
def test_every_request_aimed_at_root_is_a_404_like_an_unknown_user(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    zvz: tuple[int, int],
    user: PanelUser,
) -> None:
    root_id, root_telegram = zvz
    _sign_in(app, user)
    requests = [
        ("password", {"password": "baska-sentetik-parola"}),
        ("status", {"status": "inactive"}),
        ("role", {"role": "user"}),
        (f"telegram/{root_telegram}/status", {"allowed": "false"}),
        (f"telegram/{root_telegram}/delete", {}),
    ]
    before = _users(session_factory)

    for suffix, data in requests:
        aimed = client.post(f"/users/{root_id}/{suffix}", data=data)
        unknown = client.post(f"/users/999999/{suffix}", data=data)
        assert aimed.status_code == 404, suffix
        assert aimed.json() == unknown.json(), suffix

    assert _users(session_factory) == before
    with session_factory() as session:
        assert session.get_one(TelegramUser, root_telegram).allowed is True
        assert session.scalar(select(func.count()).select_from(Event)) == 0


def test_the_panel_cannot_create_a_root(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = client.post(
        "/users", data={"username": "ikinci", "password": PASSWORD, "role": "root"}
    )
    unknown = client.post(
        "/users", data={"username": "ikinci", "password": PASSWORD, "role": "patron"}
    )

    assert response.status_code == unknown.status_code == 422
    assert "Bilinmeyen rol." in response.text and "root" not in response.text.split("<main", 1)[1]
    assert [name for name, _, _ in _users(session_factory)] == [SIGNED_IN.username]


def test_there_is_at_most_one_root(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        create_root(session, "Zvz", PASSWORD)
        session.commit()
        with pytest.raises(RootExistsError):
            create_root(session, "ikinci-root", PASSWORD)
        with pytest.raises(ValueError):
            create_user(session, "ikinci-root", PASSWORD, role=UserRole.ROOT)
    assert [role for _, role, _ in _users(session_factory)].count("root") == 1


# --- rol değiştirme (10.1.8) -------------------------------------------------------------------


def _hr(session_factory: sessionmaker[Session], name: str, *, active: bool = True) -> int:
    with session_factory() as session:
        user = create_user(session, name, PASSWORD, role=UserRole.HR)
        user.active = active
        session.commit()
        return user.id


def test_hr_changes_a_role_with_an_event_under_its_name(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _hr(session_factory, "ayse")

    response = client.post(f"/users/{ayse}/role", data={"role": "user"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/users?notice=role_changed"
    with session_factory() as session:
        assert session.get_one(User, ayse).role == "user"
        (event,) = session.scalars(select(Event)).all()
    assert (event.type, event.actor) == ("USER_ROLE_CHANGED", SIGNED_IN.username)
    assert event.data_json == {"target_user_id": ayse, "from": "hr", "to": "user"}
    page = client.get(response.headers["location"]).text
    assert "Kullanıcının rolü değişti" in page
    row = re.search(rf'<tr id="user-{ayse}"[^>]*>(.*?)</tr>', page, re.S)
    assert row is not None and "<td>Kullanıcı</td>" in row.group(1)


def test_role_change_refuses_own_role_same_role_unknown_role_and_unknown_user(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _hr(session_factory, "ayse")

    own = client.post(f"/users/{SIGNED_IN.id}/role", data={"role": "user"})
    same = client.post(f"/users/{ayse}/role", data={"role": "hr"})
    root = client.post(f"/users/{ayse}/role", data={"role": "root"})
    unknown = client.post("/users/999999/role", data={"role": "user"})

    assert own.status_code == 409 and "Kendi rolünüzü değiştiremezsiniz." in own.text
    assert same.status_code == 409 and "zaten bu rolde" in same.text
    assert root.status_code == 422 and "Bilinmeyen rol." in root.text
    assert unknown.status_code == 404
    assert [role for _, role, _ in _users(session_factory)] == ["hr", "hr"]
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Event)) == 0


def test_the_last_active_hr_is_kept_and_root_does_not_count(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session], zvz: tuple[int, int]
) -> None:
    # Oturumdaki root; ayşe tek etkin İK (oturum kullanıcısının satırı pasif, mehmet pasif).
    with session_factory() as session:
        session.get_one(User, SIGNED_IN.id).active = False
        session.commit()
    ayse = _hr(session_factory, "ayse")
    mehmet = _hr(session_factory, "mehmet", active=False)
    root = PanelUser(zvz[0], "Zvz", UserRole.ROOT.value)
    _sign_in(app, root)

    for suffix, data in (("status", {"status": "inactive"}), ("role", {"role": "user"})):
        response = client.post(f"/users/{ayse}/{suffix}", data=data)
        assert response.status_code == 409, suffix
        assert LAST_ACTIVE_HR in response.text
        assert "root" not in response.text.split("<main", 1)[1].lower()
    # Pasif İK düşürülebilir; ikinci etkin İK gelince ayşe de düşürülebilir.
    assert client.post(f"/users/{mehmet}/role", data={"role": "user"}).status_code == 200
    _hr(session_factory, "zeynep")
    assert client.post(f"/users/{ayse}/role", data={"role": "user"}).status_code == 200
    with session_factory() as session:
        events = session.execute(select(Event.actor, Event.data_json).order_by(Event.id)).all()
    assert events == [
        ("Zvz", {"target_user_id": mehmet, "from": "hr", "to": "user"}),
        ("Zvz", {"target_user_id": ayse, "from": "hr", "to": "user"}),
    ]


def test_service_rules_refuse_root_targets_and_root_as_a_choice(
    session_factory: sessionmaker[Session], zvz: tuple[int, int]
) -> None:
    with session_factory() as session:
        root = session.get_one(User, zvz[0])
        actor = PanelUser(SIGNED_IN.id, SIGNED_IN.username, UserRole.HR.value)
        ayse = create_user(session, "ayse", PASSWORD)
        session.commit()
        with pytest.raises(RootTargetError):
            set_user_role(session, root, UserRole.USER, actor=actor)
        with pytest.raises(RootTargetError):
            set_user_active(session, root, False, actor=actor)
        with pytest.raises(RootTargetError):
            reset_password(session, root, "baska-sentetik-parola", actor=actor)
        with pytest.raises(ValueError):
            set_user_role(session, ayse, UserRole.ROOT, actor=actor)
        with pytest.raises(UserStatusError):
            set_user_role(session, ayse, UserRole.HR, actor=actor)


def test_a_role_change_applies_to_an_open_session_on_its_next_request(
    app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    ayse = _hr(session_factory, "ayse")
    del app.dependency_overrides[get_current_user]
    session_client = TestClient(app)
    login = session_client.post(
        "/login", data={"username": "ayse", "password": PASSWORD}, follow_redirects=False
    )
    assert login.status_code == 303
    assert session_client.get("/upload").status_code == 200

    with session_factory() as session:
        set_user_role(session, session.get_one(User, ayse), UserRole.USER, actor=HR)
        session.commit()

    assert session_client.get("/employees").status_code == 200
    assert session_client.get("/upload").status_code == 403
    refused = session_client.post("/document-groups", data={"name": "Vize"})
    assert refused.status_code == 403

    with session_factory() as session:
        set_user_role(session, session.get_one(User, ayse), UserRole.HR, actor=HR)
        session.commit()
    assert session_client.get("/upload").status_code == 200


def test_a_read_only_user_is_refused_on_the_json_api_too(
    app: FastAPI, client: TestClient, tmp_path: Path
) -> None:
    _sign_in(app, READER)

    response = client.post(
        "/api/uploads", files=[("files", ("a.pdf", b"%PDF-1.4", "application/pdf"))]
    )

    assert response.status_code == 403
    assert response.json() == {"detail": READ_ONLY}
