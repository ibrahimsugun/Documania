"""14.1.1, 14.1.2 — Belge Grupları sekmesi: liste, yeni grup, grup sayfası, kalem ekleme/kaldırma,
arşivleme ve geri alma (PLAN.md §C89). Hepsi tek adımdır ve `GROUP_CHANGED` olayını kullanıcı adıyla
yazar; grup ve kalem silinmez."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import DocumentGroup, DocumentGroupItem, Event, KnownDocumentType
from app.events import EventType
from tests.web.conftest import SIGNED_IN

CATALOG = (
    ("russian_passport", "Russian Passport", "Passport", "RU", True),
    ("turkish_passport", "Turkish Passport", "Passport", "TR", True),
    ("serbian_passport", "Serbian Passport", "passport", "RS", False),
    ("residence_card", "Serbian Residence Card", "Residence Card", "RS", True),
    ("turkish_id_card", "Turkish Identity Card", "Identity Card", "TR", True),
    ("kosovo_id_document", "Kosovo Identity Document", "Identity Document", "XK", True),
)


@pytest.fixture(autouse=True)
def catalog(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        for slug, name, label, country, active in CATALOG:
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
                    active=active,
                )
            )
        session.commit()


def _create(client: TestClient, name: str = "Sırbistan iş başvurusu", **extra: str) -> int:
    response = client.post(
        "/document-groups",
        data={"name": name, "description": "Çalışma izni", **extra},
        follow_redirects=False,
    )
    assert response.status_code == 303
    match = re.fullmatch(r"/document-groups/(\d+)\?notice=created", response.headers["location"])
    assert match, response.headers["location"]
    return int(match.group(1))


def _add(client: TestClient, group_id: int, **data: str) -> int:
    response = client.post(f"/document-groups/{group_id}/items", data=data, follow_redirects=False)
    return response.status_code


def _events(session_factory: sessionmaker[Session]) -> list[tuple[str, dict]]:
    with session_factory() as session:
        rows = session.scalars(
            select(Event).where(Event.type == EventType.GROUP_CHANGED).order_by(Event.id)
        )
        return [(row.actor, row.data_json or {}) for row in rows]


def _items_table(html: str) -> str:
    match = re.search(r'<table class="catalog group-items-table">.*?</table>', html, re.S)
    return match.group(0) if match else ""


# --- liste ve yeni grup --------------------------------------------------------------------------


def test_empty_list_page_opens_under_the_menu(client: TestClient) -> None:
    page = client.get("/document-groups")

    assert page.status_code == 200
    assert "<h1>Belge Grupları</h1>" in page.text
    assert '<a href="/document-groups" class="active" aria-current="page">' in page.text
    assert 'href="/document-groups/new"' in page.text
    assert "Henüz belge grubu yok" in page.text


def test_new_group_form_posts_to_the_list_path(client: TestClient) -> None:
    page = client.get("/document-groups/new")

    assert page.status_code == 200
    assert "<h1>Yeni belge grubu</h1>" in page.text
    assert 'method="post" action="/document-groups"' in page.text
    assert 'name="description"' in page.text and 'maxlength="200"' in page.text
    assert "<textarea" not in page.text


def test_creating_a_group_opens_its_page(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    group_id = _create(client)

    page = client.get(f"/document-groups/{group_id}?notice=created")
    assert page.status_code == 200
    assert "<h1>Sırbistan iş başvurusu</h1>" in page.text
    assert "Grup oluşturuldu" in page.text
    assert re.search(r"<strong>0</strong>\s*açık pakette hemen geçerli olacak", page.text)
    assert "Bu grupta henüz kalem yok" in page.text
    assert _events(session_factory) == [
        (SIGNED_IN.username, {"group_id": group_id, "action": "create", "item_count": 0})
    ]

    listing = client.get("/document-groups")
    assert f'<a href="/document-groups/{group_id}">Sırbistan iş başvurusu</a>' in listing.text
    assert "Çalışma izni" in listing.text
    assert '<span class="status-badge status-active">Etkin</span>' in listing.text


def test_duplicate_name_is_a_conflict_and_keeps_the_form(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client)

    response = client.post("/document-groups", data={"name": "SIRBISTAN İŞ BAŞVURUSU"})

    assert response.status_code == 409
    assert "Bu adla bir grup zaten var" in response.text
    assert 'value="SIRBISTAN İŞ BAŞVURUSU"' in response.text
    with session_factory() as session:
        assert len(session.scalars(select(DocumentGroup)).all()) == 1


def test_invalid_name_is_rejected_with_a_field_message(client: TestClient) -> None:
    response = client.post("/document-groups", data={"name": "  !!  ", "description": ""})

    assert response.status_code == 422
    assert "Grup adı en az bir harf ya da rakam içermeli." in response.text
    assert "Grup kaydedilmedi" in response.text


# --- grup sayfası --------------------------------------------------------------------------------


def test_group_page_offers_catalog_labels_with_counts_and_types(client: TestClient) -> None:
    group_id = _create(client)

    page = client.get(f"/document-groups/{group_id}")

    assert '<option value="Passport">Passport (3 tür)</option>' in page.text
    assert '<option value="Identity Card">Identity Card (1 tür)</option>' in page.text
    assert '<option value="Identity Document">Identity Document (1 tür)</option>' in page.text
    assert (
        '<option value="serbian_passport">Serbian Passport · RS — passport (pasif)</option>'
        in page.text
    )
    assert f'method="post" action="/document-groups/{group_id}/items"' in page.text


def test_label_and_type_items_are_added_and_listed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    group_id = _create(client)

    assert (
        _add(
            client,
            group_id,
            match_kind="label",
            file_label="Passport",
            required="1",
            note="6 aydan uzun geçerli",
        )
        == 303
    )
    assert _add(client, group_id, match_kind="type", type_slug="residence_card") == 303

    page = client.get(f"/document-groups/{group_id}?notice=item_added")
    table = _items_table(page.text)
    assert "Kalem eklendi." in page.text
    assert "Passport" in table and "Serbian Residence Card" in table
    assert "Ülkeden bağımsız: bu etiketli 3 türden herhangi biri karşılar" in table
    assert "Yalnız bu tür karşılar · RS · residence_card" in table
    assert table.count("<td>Zorunlu</td>") == 1
    assert table.count("<td>İsteğe bağlı</td>") == 1
    assert "6 aydan uzun geçerli" in table
    with session_factory() as session:
        items = session.scalars(select(DocumentGroupItem).order_by(DocumentGroupItem.id)).all()
        assert [(item.match_kind, item.required) for item in items] == [
            ("label", True),
            ("type", False),
        ]
    actions = [data["action"] for _, data in _events(session_factory)]
    assert actions == ["create", "item_added", "item_added"]

    listing = client.get("/document-groups")
    assert re.search(r"<td>2</td>\s*<td>0</td>", listing.text)


def test_unknown_label_is_rejected_and_the_form_keeps_its_values(client: TestClient) -> None:
    group_id = _create(client)

    response = client.post(
        f"/document-groups/{group_id}/items",
        data={"match_kind": "label", "file_label": "Driving Licence", "note": "not"},
    )

    assert response.status_code == 422
    assert "Bu dosya etiketi katalogdaki hiçbir türde yok." in response.text
    assert 'id="item-label-note" name="note" value="not"' in response.text


def test_duplicate_item_is_a_conflict(client: TestClient) -> None:
    group_id = _create(client)
    assert _add(client, group_id, match_kind="type", type_slug="russian_passport") == 303

    response = client.post(
        f"/document-groups/{group_id}/items",
        data={"match_kind": "type", "type_slug": "russian_passport"},
    )

    assert response.status_code == 409
    assert "Bu kalem grupta zaten var" in response.text
    assert '<option value="russian_passport" selected>' in response.text


def test_bad_match_kind_is_rejected(client: TestClient) -> None:
    group_id = _create(client)

    response = client.post(
        f"/document-groups/{group_id}/items",
        data={"match_kind": "country", "file_label": "Passport"},
    )

    assert response.status_code == 422
    assert "Kalem ya bir dosya etiketiyle ya da bir türle tanımlanır." in response.text


def test_removing_an_item_keeps_it_in_the_history(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    group_id = _create(client)
    _add(client, group_id, match_kind="label", file_label="Passport", required="1")
    with session_factory() as session:
        item_id = session.scalars(select(DocumentGroupItem.id)).one()

    response = client.post(
        f"/document-groups/{group_id}/items/{item_id}/remove", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/document-groups/{group_id}?notice=item_removed"
    page = client.get(response.headers["location"])
    assert "Kalem kaldırıldı." in page.text
    assert _items_table(page.text) == ""
    assert "Kaldırılan kalemler (1)" in page.text
    assert SIGNED_IN.username in page.text
    with session_factory() as session:
        item = session.get(DocumentGroupItem, item_id)
        assert item is not None and item.removed_by == SIGNED_IN.username
    assert _events(session_factory)[-1][1]["action"] == "item_removed"

    again = client.post(f"/document-groups/{group_id}/items/{item_id}/remove")
    assert again.status_code == 404


def test_group_name_and_description_are_changed_on_the_group_page(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    group_id = _create(client)
    _create(client, "Almanya vize")

    updated = client.post(
        f"/document-groups/{group_id}",
        data={"name": "Sırbistan başvurusu", "description": "Yeni açıklama"},
        follow_redirects=False,
    )
    assert updated.status_code == 303
    assert updated.headers["location"] == f"/document-groups/{group_id}?notice=updated"
    assert "<h1>Sırbistan başvurusu</h1>" in client.get(updated.headers["location"]).text

    same = client.post(
        f"/document-groups/{group_id}",
        data={"name": "Sırbistan başvurusu", "description": "Yeni açıklama"},
        follow_redirects=False,
    )
    assert same.headers["location"] == f"/document-groups/{group_id}?notice=unchanged"

    taken = client.post(f"/document-groups/{group_id}", data={"name": "almanya VIZE"})
    assert taken.status_code == 409
    assert "Bu adla bir grup zaten var" in taken.text
    assert "<h1>Sırbistan başvurusu</h1>" in taken.text

    invalid = client.post(f"/document-groups/{group_id}", data={"name": "   "})
    assert invalid.status_code == 422
    assert "Grup adı boş olamaz." in invalid.text

    updates = [data for _, data in _events(session_factory) if data["action"] == "update"]
    assert updates == [
        {
            "group_id": group_id,
            "action": "update",
            "item_count": 0,
            "fields": ["name", "description"],
        }
    ]


# --- arşiv ---------------------------------------------------------------------------------------


def test_archive_hides_the_group_until_asked_and_restore_brings_it_back(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    group_id = _create(client)
    _add(client, group_id, match_kind="label", file_label="Passport", required="1")

    archived = client.post(f"/document-groups/{group_id}/archive", follow_redirects=False)
    assert archived.status_code == 303
    page = client.get(archived.headers["location"])
    assert "Grup arşivlendi" in page.text
    assert 'id="group-archived"' in page.text
    assert f'action="/document-groups/{group_id}/restore"' in page.text
    assert f'action="/document-groups/{group_id}/archive"' not in page.text

    listing = client.get("/document-groups")
    assert f'href="/document-groups/{group_id}"' not in listing.text
    assert 'href="/document-groups?archived=1">Arşivdekileri de göster (1)' in listing.text
    with_archived = client.get("/document-groups?archived=1")
    assert f'href="/document-groups/{group_id}"' in with_archived.text
    assert '<span class="status-badge status-archived">Arşivde</span>' in with_archived.text

    restored = client.post(f"/document-groups/{group_id}/restore", follow_redirects=False)
    assert restored.headers["location"] == f"/document-groups/{group_id}?notice=restored"
    assert f'href="/document-groups/{group_id}"' in client.get("/document-groups").text

    with session_factory() as session:
        group = session.get(DocumentGroup, group_id)
        assert group is not None and group.archived_at is None
    assert [data["action"] for _, data in _events(session_factory)] == [
        "create",
        "item_added",
        "archive",
        "restore",
    ]
    assert {actor for actor, _ in _events(session_factory)} == {SIGNED_IN.username}


def test_missing_group_or_item_is_404(client: TestClient) -> None:
    group_id = _create(client)

    assert client.get("/document-groups/999").status_code == 404
    assert client.post("/document-groups/999", data={"name": "x"}).status_code == 404
    assert (
        client.post("/document-groups/999/items", data={"match_kind": "label"}).status_code == 404
    )
    assert client.post("/document-groups/999/archive").status_code == 404
    assert client.post("/document-groups/999/restore").status_code == 404
    assert client.post("/document-groups/999/items/1/remove").status_code == 404
    assert client.post(f"/document-groups/{group_id}/items/999/remove").status_code == 404
