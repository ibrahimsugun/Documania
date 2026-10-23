"""İşlem sonrası geçici bildirim (PRD 10.11.1, 10.11.3; PLAN.md §D120; tm 175).

Taşıyıcı tek kullanımlık `documania_flash` çerezidir (tam sayfa yönlendirmesi) ya da `HX-Trigger`
başlığı (HTMX); metin merkezi kayıttan (`app.web.feedback.REGISTRY`) gösterildiği isteğin dilinde
biçimlenir. Testler: çerezin içeriği ve ömrü, bir kez gösterim, kişisel değer yasağı, dil, taşınan
eski bildirim sözlükleri, iki aşamalı onay, salt okunur Kullanıcı'nın 403'ü ve panelin her yazma
yolunun bildirim verdiği.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

from app.db.models import UserRole
from app.i18n import use_language
from app.web.auth import SESSION_COOKIE, PanelUser, get_current_user, require_api_user
from app.web.feedback import (
    FLASH_COOKIE,
    FLASH_MAX_AGE,
    PARAMETERS,
    REGISTRY,
    TOAST_EVENT,
    FeedbackKind,
    _encode,
    _register,
    flash,
    hx_flash,
    pop_flash,
    render,
)
from tests.web.conftest import SIGNED_IN
from tests.web.flash import flashed, hx_toasts, toast_items, toasts

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "app" / "web" / "templates"
READER = PanelUser(SIGNED_IN.id, SIGNED_IN.username, UserRole.USER.value)


def _request(cookie: str | None = None, *, htmx: bool = False) -> Request:
    headers = []
    if cookie is not None:
        headers.append((b"cookie", f"{FLASH_COOKIE}={cookie}".encode()))
    if htmx:
        headers.append((b"hx-request", b"true"))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def _cookie_value(response: Response) -> str:
    header = response.headers["set-cookie"]
    return header.split(";", 1)[0].split("=", 1)[1]


def _type_form(slug: str = "sample_card") -> dict[str, object]:
    return {
        "slug": slug,
        "name": "Sample Card",
        "file_label": "Sample Card",
        "country": "RS",
        "description": "",
        "expected_file_types": ["pdf"],
        "pages_min": "1",
        "pages_max": "1",
        "sides": "single",
        "analyze": "on",
        "required_fields": "surname",
        "allowed_conversions": ["merge"],
        "output_format": "pdf",
        "acceptance_criteria": ["Kenarlar görünür"],
        "prompt_description": "",
    }


# --- 1) çekirdek: çerez yalnız anahtar ve izinli parametre taşır ---------------------------------


def test_flash_writes_only_the_key_and_the_allowed_parameters_in_a_short_lived_cookie() -> None:
    response = Response()
    flash(response, "catalog.bulk_archived_skipped", count=2, skipped=1)

    header = response.headers["set-cookie"]
    assert header.startswith(f"{FLASH_COOKIE}=")
    attributes = {part.strip().lower() for part in header.split(";")[1:]}
    assert {"httponly", "path=/", "samesite=lax", f"max-age={FLASH_MAX_AGE}"} <= attributes
    value = _cookie_value(response)
    raw = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
    assert raw == [{"k": "catalog.bulk_archived_skipped", "p": {"count": 2, "skipped": 1}}]
    # Metin çerezde değil: gösterildiği isteğin dilinde biçimlenir (10.11.3).
    assert "Arşiv" not in base64.urlsafe_b64decode(value + "==").decode()


def test_pop_flash_reads_once_and_deletes_the_cookie() -> None:
    sent = Response()
    flash(sent, "groups.created")
    response = Response()

    with use_language("tr"):
        shown = pop_flash(_request(_cookie_value(sent)), response)

    assert [(toast.kind, toast.text) for toast in shown] == [
        (FeedbackKind.SUCCESS, "Grup oluşturuldu. Şimdi kalemlerini ekleyin.")
    ]
    deleted = response.headers["set-cookie"]
    assert deleted.startswith(f'{FLASH_COOKIE}=""') and "Max-Age=0" in deleted
    assert pop_flash(_request(), Response()) == []


@pytest.mark.parametrize(
    "items",
    [
        [{"k": "yok.boyle", "p": {}}],  # bilinmeyen anahtar
        [{"k": "catalog.created", "p": {"slug": "Ana Petrović"}}],  # slug değil
        [{"k": "catalog.created", "p": {"slug": "x", "name": "Ana"}}],  # izinsiz parametre
        [{"k": "catalog.created", "p": {}}],  # eksik parametre
        [{"k": "uploads.received", "p": {"upload_id": "<script>"}}],
        [{"k": "catalog.bulk_archived", "p": {"count": True}}],
        [{"k": "catalog.bulk_archived", "p": {"count": "2"}}],
        "dizi değil",
    ],
    ids=lambda items: json.dumps(items, ensure_ascii=True)[:40],
)
def test_an_unknown_key_or_a_parameter_of_a_disallowed_type_is_ignored(items: object) -> None:
    value = _encode(items) if isinstance(items, list) else "%%%bozuk"
    assert pop_flash(_request(value), Response()) == []


def test_flash_refuses_an_unknown_key_and_a_personal_value() -> None:
    with pytest.raises(ValueError, match="kayıtlı olmayan"):
        flash(Response(), "yok.boyle")
    with pytest.raises(ValueError, match="geçersiz"):
        flash(Response(), "catalog.created", slug="Ana Petrović")
    with pytest.raises(ValueError, match="geçersiz"):
        flash(Response(), "employees.document_moved", employee_id="Ana Petrović")
    with pytest.raises(ValueError, match="geçersiz"):
        flash(Response(), "groups.created", name="Ana")


def test_the_registry_allows_only_non_personal_placeholders() -> None:
    # Kişisel değer (ad-soyad, belge numarası, doğum tarihi) parametre olamaz; izinli tipler:
    # tam sayı, E numarası, parti kimliği, tür slug'ı (§D120 b); profil alanı adları (15.2.1).
    assert set(PARAMETERS) == {
        "count",
        "skipped",
        "version",
        "previous",
        "employee_id",
        "upload_id",
        "slug",
        "fields",
        "overflow",
    }
    for key, feedback in REGISTRY.items():
        assert feedback.key == key
        assert feedback.params <= set(PARAMETERS), key
        assert isinstance(feedback.kind, FeedbackKind)
    for personal in ("name", "surname", "full_name", "document_number", "birth_date"):
        with pytest.raises(ValueError, match="izinsiz"):
            _register(f"deneme.{personal}", FeedbackKind.INFO, "{" + personal + "}")


def test_the_kind_decides_the_screen_reader_role_and_the_persistence() -> None:
    assert [(kind.role, kind.persistent) for kind in FeedbackKind] == [
        ("status", False),
        ("status", False),
        ("alert", True),
        ("alert", True),
    ]


# --- 4) dil: metin gösterildiği isteğin dilinde --------------------------------------------------


def test_the_same_key_speaks_each_language() -> None:
    texts = {}
    for language in ("en", "tr", "sr"):
        with use_language(language):
            texts[language] = render("employees.status_inactive").text
    assert texts == {
        "en": "The employee was deactivated; their new documents will not be placed automatically.",
        "tr": "Çalışan pasife alındı; yeni belgeleri otomatik yerleşmeyecek.",
        "sr": texts["sr"],
    }
    assert texts["sr"] not in (texts["en"], texts["tr"])
    with use_language("sr"):
        assert render("uploads.received", upload_id="u_20990101_0001").text == (
            "Otpremanje je primljeno: u_20990101_0001. Napredak pratite ispod."
        )


def test_hx_flash_renders_in_the_request_language_into_the_trigger_header() -> None:
    response = Response()
    with use_language("en"):
        hx_flash(response, "queue.reopened")
        hx_flash(response, "write.conflict")

    triggers = json.loads(response.headers["HX-Trigger"])
    assert triggers[TOAST_EVENT]["toasts"] == [
        {"kind": "success", "text": "The item was reopened."},
        {"kind": "warning", "text": triggers[TOAST_EVENT]["toasts"][1]["text"]},
    ]
    assert "set-cookie" not in response.headers


# --- 2) tam sayfa: POST → 303 → GET'te bir kez ---------------------------------------------------


def test_a_redirected_write_shows_its_notice_once_and_never_in_the_address(
    client: TestClient,
) -> None:
    response = client.post("/document-groups", data={"name": "İzin"}, follow_redirects=False)

    assert response.status_code == 303
    assert "notice" not in response.headers["location"]
    assert flashed(response) == ("groups.created", {})
    first = client.get(response.headers["location"])
    assert toast_items(first.text) == [
        ("success", "status", "Grup oluşturuldu. Şimdi kalemlerini ekleyin.")
    ]
    assert f'{FLASH_COOKIE}=""' in first.headers["set-cookie"]
    # Yenileme, geri gelme ya da adresi paylaşma bildirimi yeniden göstermez.
    assert toasts(client.get(response.headers["location"]).text) == []
    assert toasts(TestClient(client.app).get(response.headers["location"]).text) == []


def test_the_notice_region_carries_the_script_the_close_label_and_the_noscript_note(
    client: TestClient,
) -> None:
    page = client.get("/employees").text

    region = re.search(r'<div class="toasts" aria-live="polite" data-close-label="([^"]+)">', page)
    assert region is not None and region.group(1) == "Bildirimi kapat"
    assert page.index('class="toasts"') < page.index('<main class="content">')
    assert re.search(r'<script src="/static/toast\.js\?v=[0-9a-f]{12}" defer></script>', page)
    assert "<noscript><style>.toasts { position: static;" in page


def test_the_notice_is_shown_in_the_language_of_the_showing_request(
    app: FastAPI, client: TestClient
) -> None:
    response = client.post("/document-groups", data={"name": "İzin"}, follow_redirects=False)
    serbian = PanelUser(SIGNED_IN.id, SIGNED_IN.username, SIGNED_IN.role, language="sr")
    app.dependency_overrides[get_current_user] = lambda: serbian

    page = client.get(response.headers["location"])

    assert toasts(page.text) == ["Grupa je napravljena. Sada dodajte njene stavke."]
    region = re.search(r'data-close-label="([^"]+)"', page.text)
    assert region is not None and region.group(1) == "Zatvori obaveštenje"


def test_a_file_response_and_a_redirect_do_not_consume_the_notice(client: TestClient) -> None:
    client.post("/document-groups", data={"name": "İzin"}, follow_redirects=False)

    style = client.get("/static/theme.css")
    root = client.get("/", follow_redirects=False)

    assert FLASH_COOKIE not in style.headers.get("set-cookie", "")
    assert FLASH_COOKIE not in root.headers.get("set-cookie", "")
    assert toasts(client.get("/document-groups").text) == [
        "Grup oluşturuldu. Şimdi kalemlerini ekleyin."
    ]


# --- 3) HTMX: başlık, çerez yok ----------------------------------------------------------------


def test_an_htmx_request_gets_the_notice_in_the_trigger_header_and_no_cookie(
    client: TestClient,
) -> None:
    response = client.post(
        "/uploads/u_20990101_0001/rerun", headers={"HX-Request": "true"}, follow_redirects=False
    )

    assert response.status_code == 404
    assert hx_toasts(response) == [{"kind": "error", "text": "İşlem yapılamadı: kayıt bulunamadı."}]
    assert FLASH_COOKIE not in response.headers.get("set-cookie", "")
    assert 'class="toasts"' not in response.text


def test_an_htmx_request_after_a_redirect_moves_the_cookie_into_the_header(
    client: TestClient,
) -> None:
    # `hx-select` ile seçilen parça bildirim alanını içermez: çerez başlığa taşınır, çift
    # gösterim olmaz.
    client.post("/document-groups", data={"name": "İzin"}, follow_redirects=False)

    page = client.get("/document-groups", headers={"HX-Request": "true"})

    assert hx_toasts(page) == [
        {"kind": "success", "text": "Grup oluşturuldu. Şimdi kalemlerini ekleyin."}
    ]
    assert toasts(page.text) == []
    assert f'{FLASH_COOKIE}=""' in page.headers["set-cookie"]


# --- 5) taşıma: eski sözlüklerin her anahtarı kayıtta; sayfa içi kutu kalmadı -------------------

# Taşınan sözlüklerin (`catalog.py` NOTICES/BULK_NOTICES/TYPE_PAGE_NOTICES/CANDIDATE_NOTICES,
# `employees.py` PACKAGE_/PROFILE_/RECORD_/DOCUMENT_/EMPLOYEE_DELETED_NOTICES, `groups.py`,
# `users.py`, `queue.py`, `training.py` NOTICES) anahtarları → kayıttaki anahtar.
MIGRATED = {
    **{
        f"catalog:{key}": f"catalog.{key}"
        for key in (
            "created",
            "updated",
            "deactivated",
            "activated",
            "archived",
            "restored",
            "none_selected",
            "bulk_deactivated",
            "bulk_activated",
            "bulk_archived",
            "photo_rules",
        )
    },
    "catalog:bulk_archived+skipped": "catalog.bulk_archived_skipped",
    **{
        f"candidate:{key}": f"catalog.candidate_{key}"
        for key in ("approved", "rejected", "restored")
    },
    "candidate:examined": "catalog.candidate_examined",
    **{
        f"employees:{key}": f"employees.{key}"
        for key in (
            "package_assigned",
            "package_cancelled",
            "package_reopened",
            "fields_changed",
            "fields_renamed",
            "status_inactive",
            "status_active",
            "merged",
            "record_removed",
            "record_restored",
            "contact_added",
            "document_archived",
            "document_unarchived",
            "document_deleted",
            "document_deleted_partial",
        )
    },
    "employees:employee_deleted": "employees.deleted",
    "employees:employee_deleted_partial": "employees.deleted_partial",
    **{
        f"groups:{key}": f"groups.{key}"
        for key in (
            "created",
            "updated",
            "unchanged",
            "item_added",
            "item_removed",
            "archived",
            "restored",
        )
    },
    **{
        f"users:{key}": f"users.{key}"
        for key in (
            "created",
            "password_reset",
            "deactivated",
            "reactivated",
            "role_changed",
            "own_password",
            "telegram_allowed",
            "telegram_blocked",
            "telegram_removed",
            "telegram_added",
        )
    },
    "queue:closed": "queue.closed",
    "queue:reopened": "queue.reopened",
    **{
        f"training:{key}": f"training.{key}"
        for key in (
            "uploaded",
            "placed",
            "skipped",
            "conflict",
            "verified",
            "verify_none",
            "moved",
            "removed",
            "map_started",
            "dismissed",
            "restored",
            "run_archived",
            "run_restored",
        )
    },
}


def test_every_key_of_the_old_notice_dictionaries_is_in_the_registry() -> None:
    assert sorted(key for key in MIGRATED.values() if key not in REGISTRY) == []


def test_no_router_reads_or_writes_a_notice_address_any_more() -> None:
    routers = ROOT / "app" / "web" / "routers"
    offenders = [
        f"{path.name}:{number}"
        for path in sorted(routers.glob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"[?&]notice=|\bnotice\b\s*[:=]|NOTICES\b", line)
    ]
    assert offenders == []


# Kalan `.notice` kutuları işlem sonucu değil, kaydın durumunu anlatan kalıcı notlardır (arşivli
# grup, pasif çalışan, sağlayıcı yok, bütçe, taslak durumu …) ve PLAN.md §D120'de listelidir;
# `notice-success` (işlem sonucu kutusu) yalnız kaydedilmemiş açıklama bandında kalır.
def test_no_success_box_is_left_in_the_templates() -> None:
    boxes = {
        path.name
        for path in TEMPLATES.glob("*.html")
        if "notice-success" in path.read_text(encoding="utf-8")
    }
    assert boxes == {"catalog_description.html"}


# --- 7) iki aşamalı onay: bildirim yalnız son adımda ----------------------------------------------


def test_the_two_step_confirmation_notifies_only_when_the_action_is_done(
    client: TestClient,
) -> None:
    client.cookies.set(SESSION_COOKIE, "oturum-bir")
    created = client.post("/document-types", data=_type_form(), follow_redirects=False)
    assert created.status_code == 303
    client.get("/document-types")  # oluşturma bildirimi tüketildi

    confirm = client.get("/document-types/sample_card/archive/confirm")
    prepared = client.post("/document-types/sample_card/archive/prepare")

    assert (confirm.status_code, prepared.status_code) == (200, 200)
    assert toasts(confirm.text) == [] and toasts(prepared.text) == []
    assert hx_toasts(prepared) == [] and flashed(prepared) is None
    token = re.search(r'name="confirmation" value="([^"]+)"', prepared.text)
    assert token is not None
    done = client.post(
        "/document-types/sample_card/archive",
        data={"confirmation": token.group(1)},
        follow_redirects=False,
    )
    assert flashed(done) == ("catalog.archived", {"slug": "sample_card"})


# --- 8) salt okunur Kullanıcı'nın 403'ü hata bildirimi -------------------------------------------


def test_a_read_only_users_refused_write_is_an_error_notice(
    app: FastAPI, client: TestClient
) -> None:
    app.dependency_overrides[get_current_user] = lambda: READER

    refused = client.post("/document-groups", data={"name": "İzin"}, follow_redirects=False)
    htmx = client.post(
        "/uploads/u_20990101_0001/rerun", headers={"HX-Request": "true"}, follow_redirects=False
    )

    assert refused.status_code == 403
    assert flashed(refused) == ("access.read_only", {})
    assert toast_items(client.get("/employees").text) == [
        ("error", "alert", "Hesabınız salt okunur: bu işlemi yapamazsınız.")
    ]
    assert htmx.status_code == 403
    assert hx_toasts(htmx) == [
        {"kind": "error", "text": "Hesabınız salt okunur: bu işlemi yapamazsınız."}
    ]


# --- 6) envanter: panelin her yazma yolu bildirim verir -------------------------------------------

# Bildirim almayan yazma yolları (PLAN.md §D120): giriş/çıkış ve dil seçici (oturum ve dil akışı),
# tür formunun ölçüt satırı ekle/kaldır ve örneklerden açıklama üretme (hiçbir şey kaydetmez;
# sonuç formun kendisidir). Yapay zekâ ayarları İK'ya (bu taramanın kullanıcısı) bilinmeyen yolla
# aynı 404'tür, bildirim taşımaz (10.1.10); root'un başarısız kaydı bildirim alır
# (`tests/web/test_ai_settings_page.py`).
WITHOUT_FEEDBACK = frozenset(
    {
        "/ai-settings",
        "/ai-settings/{rest:path}",
        "/login",
        "/logout",
        "/language",
        "/document-types/criteria/add",
        "/document-types/criteria/remove",
        "/document-types/{slug}/description",
    }
)


def _write_routes(application: FastAPI) -> set[str]:
    paths = set()
    for route in application.routes:
        contexts = (
            route.effective_route_contexts() if hasattr(route, "effective_route_contexts") else []
        )
        for context in contexts:
            calls = [dependency.call for dependency in context.dependant.dependencies]
            if require_api_user in calls:
                continue
            if set(context.methods) - {"GET", "HEAD", "OPTIONS"}:
                paths.add(context.path)
    return paths


def test_the_inventory_covers_every_panel_write_route(app: FastAPI) -> None:
    routes = _write_routes(app)
    assert WITHOUT_FEEDBACK <= routes
    assert len(routes - WITHOUT_FEEDBACK) > 90


def test_every_panel_write_route_answers_with_a_notice_even_when_it_fails(app: FastAPI) -> None:
    # Olmayan kayıtla (404/409/422) ya da eksik formla: her yazma yolu sonucu bildirimle söyler —
    # yönlendirmenin çerezi, sayfanın bildirim alanı ya da `HX-Trigger` başlığı.
    def ghost(match: re.Match[str]) -> str:
        return "E9999" if match.group(1) == "employee_id" else "999999"

    writer = TestClient(app, raise_server_exceptions=False)
    silent = []
    for path in sorted(_write_routes(app) - WITHOUT_FEEDBACK):
        writer.cookies.clear()
        response = writer.post(re.sub(r"\{(\w+)\}", ghost, path), follow_redirects=False)
        if not (flashed(response) or toasts(response.text) or hx_toasts(response)):
            silent.append(f"{path}: {response.status_code}")
    assert silent == []
