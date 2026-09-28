"""14.2.1–14.2.3, 14.3.1 — panelde belge paketleri: profilin "Belge paketleri" bölümü (kartlar,
kalem tikleri, durum rozeti, katlanmış iptaller), paket tanımlama / iptal / yeniden açma formları,
çalışan listesinin "Paket" sütunu ve "eksik paketi olanlar" süzgeci, grup sayfasının açık paket
sayısı ve `profil.md`'nin yeniden üretimi (PLAN.md §C89).

Veriler sentetiktir (çalışanlar, türler, gruplar ve çıktı satırları doğrudan yazılır); gerçek kimlik
belgesi ve yapay zekâ çağrısı yoktur. İstekler HTTP katmanından (`TestClient`) yapılır.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeePackage,
    Event,
    KnownDocumentType,
    PackageStatus,
)
from app.events import EventType
from app.groups import add_item, create_group, set_group_archived
from app.storage import DataLayout
from tests.web.conftest import SIGNED_IN

OWNER, OWNER_FOLDER = "E0001", "Ivan_Petrov_E0001"
OTHER, OTHER_FOLDER = "E0002", "Ana_Prueba_E0002"
CATALOG = (
    ("russian_passport", "Russian Passport", "Passport", "RU"),
    ("turkish_passport", "Turkish Passport", "Passport", "TR"),
    ("profile_picture", "Profile Picture", "Profile Picture", None),
    ("residence_card", "Serbian Residence Card", "Residence Card", "RS"),
)
BASE_TIME = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
COMPLETED = "Tamamlandı — başvuru başlatılabilir"


@pytest.fixture
def seeded(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, int]:
    """İki çalışan, dört tür, üç kalemli "Sırbistan iş başvurusu" grubu, tek kalemli "Almanya
    vizesi" grubu ve arşivdeki bir grup."""
    with session_factory() as session:
        for slug, name, label, country in CATALOG:
            session.add(
                KnownDocumentType(
                    slug=slug,
                    name=name,
                    file_label=label,
                    country=country,
                    sides="single",
                    direct=False,
                    analyze=True,
                    output_format="keep",
                )
            )
        for employee_id, folder, given, surname in (
            (OWNER, OWNER_FOLDER, "Ivan", "Petrov"),
            (OTHER, OTHER_FOLDER, "Ana", "Prueba"),
        ):
            session.add(
                Employee(id=employee_id, folder_name=folder, given_names=given, surname=surname)
            )
            layout.ensure_employee_tree(folder)
        session.flush()
        serbia = create_group(session, name="Sırbistan iş başvurusu", description=None, actor="ik")
        add_item(session, serbia.id, match_kind="label", file_label="Passport", actor="ik")
        add_item(session, serbia.id, match_kind="label", file_label="Profile Picture", actor="ik")
        add_item(session, serbia.id, match_kind="type", type_slug="residence_card", actor="ik")
        germany = create_group(session, name="Almanya vizesi", description=None, actor="ik")
        add_item(session, germany.id, match_kind="type", type_slug="russian_passport", actor="ik")
        old = create_group(session, name="Eski süreç", description=None, actor="ik")
        set_group_archived(session, old.id, True, actor="ik")
        session.commit()
        return {"serbia": serbia.id, "germany": germany.id, "archived": old.id}


def _document(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    slug: str,
    *,
    owner: str = OWNER,
    status: DocumentStatus = DocumentStatus.ACTIVE,
    minutes: int = 0,
    stored: bool = True,
) -> int:
    folder = OWNER_FOLDER if owner == OWNER else OTHER_FOLDER
    path = layout.employee_dir(folder) / "Hazir" / f"{slug}-{minutes}.pdf"
    if stored:
        path.write_bytes(b"%PDF-1.4 sentetik")
    with session_factory() as session:
        document = Document(
            employee_id=owner,
            type_slug=slug,
            path=layout.relative(path),
            format="pdf",
            source_refs_json=[],
            status=status.value,
            created_at=BASE_TIME + timedelta(minutes=minutes),
        )
        session.add(document)
        session.commit()
        return document.id


def _assign(client: TestClient, group_id: int, employee_id: str = OWNER, **data: str):
    return client.post(
        f"/employees/{employee_id}/packages",
        data={"group_id": str(group_id), **data},
        follow_redirects=False,
    )


def _packages(session_factory: sessionmaker[Session]) -> list[tuple[str, int, str]]:
    with session_factory() as session:
        return [
            (row.employee_id, row.group_id, row.status)
            for row in session.scalars(select(EmployeePackage).order_by(EmployeePackage.id))
        ]


def _package_events(session_factory: sessionmaker[Session]) -> list[tuple[str, str, dict]]:
    kinds = [kind.value for kind in EventType if kind.value.startswith("PACKAGE_")]
    with session_factory() as session:
        rows = session.scalars(select(Event).where(Event.type.in_(kinds)).order_by(Event.id))
        return [(row.type, row.actor, row.data_json or {}) for row in rows]


def _section(html: str) -> str:
    match = re.search(r'<section class="profile-packages".*?</section>', html, re.S)
    assert match is not None
    return match.group(0)


def _card(html: str, package_id: int) -> str:
    match = re.search(
        rf'<article class="package-card[^"]*" id="package-{package_id}">.*?</article>', html, re.S
    )
    assert match is not None, package_id
    return match.group(0)


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _package_id(session_factory: sessionmaker[Session], employee_id: str = OWNER) -> int:
    with session_factory() as session:
        found = session.scalar(
            select(func.max(EmployeePackage.id)).where(EmployeePackage.employee_id == employee_id)
        )
        assert found is not None
        return found


# --- 14.2.1: tanımlama ---------------------------------------------------------------------------


def test_profile_offers_unarchived_groups_and_a_note_input(
    client: TestClient, seeded: dict[str, int]
) -> None:
    page = client.get(f"/employees/{OWNER}")

    assert page.status_code == 200
    section = _section(page.text)
    assert "Belge paketleri" in section and "Açık ya da tamamlanmış paket yok." in section
    assert f'method="post" action="/employees/{OWNER}/packages"' in section
    options = re.findall(r'<option value="(\d+)"[^>]*>([^<]+)</option>', section)
    assert options == [
        (str(seeded["germany"]), "Almanya vizesi (1 kalem)"),
        (str(seeded["serbia"]), "Sırbistan iş başvurusu (3 kalem)"),
    ]
    assert '<input id="package-note" name="note" type="text" maxlength="120"' in section
    assert "<textarea" not in page.text
    assert "Paket tanımla" in section


def test_assigning_a_package_redirects_to_the_profile_and_logs_the_user(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, int],
) -> None:
    response = _assign(client, seeded["serbia"], note="Belgrad ofisi")

    assert response.status_code == 303
    assert response.headers["location"] == f"/employees/{OWNER}?notice=package_assigned#packages"
    assert _packages(session_factory) == [(OWNER, seeded["serbia"], "open")]
    package_id = _package_id(session_factory)
    assert _package_events(session_factory) == [
        (
            "PACKAGE_ASSIGNED",
            SIGNED_IN.username,
            {"package_id": package_id, "group_id": seeded["serbia"], "duplicate": False},
        )
    ]
    page = client.get(response.headers["location"])
    assert "Paket tanımlandı." in page.text
    card = _text(_card(page.text, package_id))
    assert "Sırbistan iş başvurusu" in card and "Açık — 0/3 zorunlu kalem" in card
    assert f"Tanımlayan: {SIGNED_IN.username}" in card and "Not: Belgrad ofisi" in card
    # 14.3.1: profil.md commit'ten sonra paket bölümüyle yeniden üretildi.
    profile_md = layout.profile_path(OWNER_FOLDER).read_text(encoding="utf-8")
    assert "## Belge paketleri" in profile_md
    assert "### Sırbistan iş başvurusu — Açık — 0/3 zorunlu kalem" in profile_md
    assert "Belgrad" not in profile_md


def test_an_archived_group_or_a_long_note_is_refused_and_nothing_is_written(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, int]
) -> None:
    archived = _assign(client, seeded["archived"])
    assert archived.status_code == 409
    assert "Arşivdeki gruba yeni paket tanımlanamaz." in archived.text

    long_note = _assign(client, seeded["serbia"], note="x" * 121)
    assert long_note.status_code == 422
    assert "Not en çok 120 karakter olabilir." in long_note.text
    assert f'value="{"x" * 121}"' in long_note.text

    assert _assign(client, 999).status_code == 404
    assert _assign(client, seeded["serbia"], employee_id="E9999").status_code == 404
    assert _packages(session_factory) == []
    assert _package_events(session_factory) == []


def test_a_second_package_of_the_same_group_is_confirmed_before_it_opens(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, int]
) -> None:
    assert _assign(client, seeded["serbia"]).status_code == 303

    warned = _assign(client, seeded["serbia"], note="ikinci")
    assert warned.status_code == 409
    section = _section(warned.text)
    assert "aynı gruptan iptal edilmemiş bir paket zaten var" in section
    assert '<input type="hidden" name="confirm_duplicate" value="1">' in section
    assert "Yine de paket tanımla" in section and 'value="ikinci"' in section
    assert len(_packages(session_factory)) == 1

    confirmed = _assign(client, seeded["serbia"], note="ikinci", confirm_duplicate="1")
    assert confirmed.status_code == 303
    assert [status for _, _, status in _packages(session_factory)] == ["open", "open"]
    assert _package_events(session_factory)[-1][2]["duplicate"] is True


# --- 14.2.2: kademeli tik ------------------------------------------------------------------------


def test_items_tick_as_documents_arrive_and_link_the_meeting_document(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, int],
) -> None:
    _assign(client, seeded["serbia"])
    package_id = _package_id(session_factory)
    passport = _document(session_factory, layout, "turkish_passport", minutes=1)
    photo = _document(session_factory, layout, "profile_picture", minutes=2, stored=False)
    _document(session_factory, layout, "residence_card", status=DocumentStatus.ARCHIVED)
    events_before = _package_events(session_factory)

    page = client.get(f"/employees/{OWNER}")

    card = _card(page.text, package_id)
    items = re.findall(r'<li class="(item-met|item-missing)">(.*?)</li>', card, re.S)
    assert [(kind, _text(body)) for kind, body in items] == [
        ("item-met", "✓ Karşılandı: Passport zorunlu turkish_passport-1.pdf"),
        ("item-met", "✓ Karşılandı: Profile Picture zorunlu profile_picture-2.pdf"),
        ("item-missing", "○ Eksik: Serbian Residence Card zorunlu"),
    ]
    # Dosyası yerinde olan belge yeni sekmede açılır, olmayanın geçmişine gidilir.
    assert f'href="/employees/{OWNER}/documents/{passport}/file" target="_blank"' in card
    assert f'href="/documents/{photo}/history"' in card
    assert "Açık — 2/3 zorunlu kalem" in _text(card)
    # GET olay ve durum yazmaz: tikler görüntülemede hesaplanır.
    assert _package_events(session_factory) == events_before
    assert _packages(session_factory)[0][2] == "open"


def test_a_completed_package_says_the_application_can_start(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, int],
) -> None:
    for slug in ("russian_passport", "profile_picture", "residence_card"):
        _document(session_factory, layout, slug)

    _assign(client, seeded["serbia"])

    page = client.get(f"/employees/{OWNER}")
    card = _card(page.text, _package_id(session_factory))
    assert 'class="package-card package-completed"' in card
    assert f'<span class="status-badge status-active">{COMPLETED}</span>' in card
    assert "Tamamlandı: " in _text(card)
    assert _packages(session_factory)[0][2] == PackageStatus.COMPLETED.value


def test_pages_show_the_computed_state_but_only_refresh_points_write_it(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, int],
) -> None:
    # Belgeler yenileme noktası dışından (doğrudan satır) gelir: sayfa tamamlanmış hâli gösterir ama
    # GET ne durumu ne `PACKAGE_COMPLETED`'ı yazar.
    _assign(client, seeded["serbia"])
    for slug in ("russian_passport", "profile_picture", "residence_card"):
        _document(session_factory, layout, slug)
    events_before = _package_events(session_factory)

    profile = client.get(f"/employees/{OWNER}")
    listing = client.get("/employees", params={"packages": "missing"})

    assert COMPLETED in _text(_card(profile.text, _package_id(session_factory)))
    assert "Eksik paketi olan çalışan yok." in listing.text
    assert _package_events(session_factory) == events_before
    assert _packages(session_factory) == [(OWNER, seeded["serbia"], "open")]


# --- 14.2.3: iptal ve yeniden açma ---------------------------------------------------------------


def test_cancelling_needs_a_reason_and_folds_the_package_under_details(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, int]
) -> None:
    _assign(client, seeded["serbia"])
    package_id = _package_id(session_factory)
    url = f"/employees/{OWNER}/packages/{package_id}/cancel"

    blank = client.post(url, data={"note": "  "}, follow_redirects=False)
    assert blank.status_code == 422
    assert "İptal nedeni boş olamaz." in _card(blank.text, package_id)

    done = client.post(url, data={"note": "Başvuru ertelendi"}, follow_redirects=False)
    assert done.status_code == 303
    assert done.headers["location"] == f"/employees/{OWNER}?notice=package_cancelled#packages"
    assert _packages(session_factory) == [(OWNER, seeded["serbia"], "cancelled")]
    page = client.get(done.headers["location"])
    section = _section(page.text)
    assert "Paket iptal edildi." in section and "Açık ya da tamamlanmış paket yok." in section
    folded = re.search(r'<details class="cancelled-packages">.*?</details>', section, re.S)
    assert folded is not None
    assert "İptal edilen paketler (1)" in folded.group(0)
    assert "Neden: Başvuru ertelendi" in _text(folded.group(0))
    assert f'action="/employees/{OWNER}/packages/{package_id}/reopen"' in folded.group(0)
    assert client.post(url, data={"note": "yine"}, follow_redirects=False).status_code == 409


def test_reopening_brings_the_package_back_in_one_step(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, int]
) -> None:
    _assign(client, seeded["serbia"])
    package_id = _package_id(session_factory)
    reopen = f"/employees/{OWNER}/packages/{package_id}/reopen"
    assert client.post(reopen, follow_redirects=False).status_code == 409

    client.post(f"/employees/{OWNER}/packages/{package_id}/cancel", data={"note": "Vazgeçildi"})
    response = client.post(reopen, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/employees/{OWNER}?notice=package_reopened#packages"
    assert _packages(session_factory) == [(OWNER, seeded["serbia"], "open")]
    assert [(kind, actor) for kind, actor, _ in _package_events(session_factory)] == [
        ("PACKAGE_ASSIGNED", SIGNED_IN.username),
        ("PACKAGE_CANCELLED", SIGNED_IN.username),
        ("PACKAGE_REOPENED", SIGNED_IN.username),
    ]


def test_a_package_of_another_employee_cannot_be_cancelled_through_this_profile(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, int]
) -> None:
    _assign(client, seeded["serbia"], employee_id=OTHER)
    package_id = _package_id(session_factory, OTHER)

    response = client.post(
        f"/employees/{OWNER}/packages/{package_id}/cancel", data={"note": "yanlış"}
    )
    assert response.status_code == 404
    assert client.post(f"/employees/{OWNER}/packages/{package_id}/reopen").status_code == 404
    assert _packages(session_factory) == [(OTHER, seeded["serbia"], "open")]


# --- 14.3.1: çalışan listesi ---------------------------------------------------------------------


def _list_rows(html: str) -> dict[str, list[str]]:
    body = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    rows = [
        [_text(cell) for cell in re.findall(r"<td>(.*?)</td>", row, re.S)]
        for row in re.findall(r"<tr>(.*?)</tr>", body, re.S)
    ]
    return {row[0]: row for row in rows}


def test_list_shows_open_packages_and_missing_items_and_filters_them(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, int],
) -> None:
    _assign(client, seeded["serbia"])
    _assign(client, seeded["germany"])
    _assign(client, seeded["germany"], employee_id=OTHER)
    _document(session_factory, layout, "profile_picture")
    _document(session_factory, layout, "russian_passport", owner=OTHER)
    # Tamamlanma yenileme noktasında yazılır; liste hesaplanan hâli gösterir.

    page = client.get("/employees")
    header = re.findall(r"<th>(.*?)</th>", page.text)
    assert header[5] == "Paket"
    rows = _list_rows(page.text)
    assert rows[OWNER][5] == "2 açık · 3 eksik"
    assert rows[OTHER][5] == "—"

    filtered = client.get("/employees", params={"packages": "missing"})
    assert list(_list_rows(filtered.text)) == [OWNER]
    assert "yalnız eksik paketi olanlar" in filtered.text
    assert 'name="packages" value="missing" checked' in filtered.text
    # Süzgeç aramayla birleşir; tanınmayan değer süzmez.
    combined = client.get("/employees", params={"packages": "missing", "q": "Prueba"})
    assert "“Prueba” ile eşleşen ve eksik paketi olan çalışan yok." in combined.text
    assert list(
        _list_rows(client.get("/employees", params={"packages": "missing", "q": "Petrov"}).text)
    ) == [OWNER]
    assert set(_list_rows(client.get("/employees", params={"packages": "hepsi"}).text)) == {
        OWNER,
        OTHER,
    }
    fragment = client.get(
        "/employees", params={"packages": "missing"}, headers={"HX-Request": "true"}
    )
    assert "<html" not in fragment.text and list(_list_rows(fragment.text)) == [OWNER]


def test_paging_keeps_the_package_filter(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, int]
) -> None:
    with session_factory() as session:
        for number in range(3, 30):
            employee_id = f"E{number:04d}"
            session.add(
                Employee(
                    id=employee_id,
                    folder_name=f"Kisi_Kalabalik_{employee_id}",
                    given_names="Kisi",
                    surname=f"Kalabalik{number:02d}",
                )
            )
            session.add(
                EmployeePackage(
                    employee_id=employee_id, group_id=seeded["germany"], requested_by="ik"
                )
            )
        session.commit()

    page = client.get("/employees", params={"packages": "missing"})

    assert "27 çalışan bulundu" in page.text
    assert 'href="/employees?packages=missing&amp;page=2"' in page.text


# --- grup sayfası ve profil.md -------------------------------------------------------------------


def test_group_page_counts_open_packages_and_group_changes_rewrite_profiles(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, int],
) -> None:
    _assign(client, seeded["germany"])
    _assign(client, seeded["germany"], employee_id=OTHER)
    _document(session_factory, layout, "russian_passport", owner=OTHER)
    client.post(
        f"/employees/{OTHER}/packages/{_package_id(session_factory, OTHER)}/cancel",
        data={"note": "Vazgeçildi"},
    )

    page = client.get(f"/document-groups/{seeded['germany']}")
    assert re.search(r"<strong>1</strong>\s*açık pakette hemen geçerli olacak", page.text)
    listing = client.get("/document-groups")
    row = re.search(
        rf"<tr>\s*<td><a href=\"/document-groups/{seeded['germany']}\">.*?</tr>",
        listing.text,
        re.S,
    )
    assert row is not None and "<td>1</td>" in row.group(0)

    renamed = client.post(
        f"/document-groups/{seeded['germany']}",
        data={"name": "Almanya çalışma vizesi", "description": ""},
        follow_redirects=False,
    )
    assert renamed.status_code == 303
    for folder in (OWNER_FOLDER, OTHER_FOLDER):
        assert "Almanya çalışma vizesi" in layout.profile_path(folder).read_text(encoding="utf-8")

    added = client.post(
        f"/document-groups/{seeded['germany']}/items",
        data={"match_kind": "label", "file_label": "Profile Picture", "required": "true"},
        follow_redirects=False,
    )
    assert added.status_code == 303
    assert "| Profile Picture | evet | ○ | — |" in layout.profile_path(OWNER_FOLDER).read_text(
        encoding="utf-8"
    )
