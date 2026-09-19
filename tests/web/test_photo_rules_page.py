"""11.6.1 — Profil fotoğrafı kural seti: kurallar katalogda tutulur ve Belge Türleri ekranından
açılıp kapatılabilir.

Kurallar yalnız saklanır (değerlendirme 11.7'nindir); ekran belge içeriğine, yüklemelere ve olay
loguna dokunmaz. Yalnız `TestClient`: tarayıcıda çizim görülmedi."""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import (
    PHOTO_RULE_SPECS,
    PhotoRulesForm,
    build_photo_rules,
    enabled_photo_rules,
    export_catalog,
    import_catalog,
    load_seed_catalog,
)
from app.db.models import Document, Event, KnownDocumentType, Upload
from tests.fixtures.gen import make_docx_bytes

SLUG = "profile_picture"
PAGE = f"/document-types/{SLUG}"
RULES_URL = f"{PAGE}/photo-rules"
ALL_IDS = tuple(spec.id for spec in PHOTO_RULE_SPECS)
DEFAULT_ON = tuple(spec.id for spec in PHOTO_RULE_SPECS if spec.default_enabled)


@pytest.fixture(autouse=True)
def seeded(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()


def _stored(session_factory: sessionmaker[Session], slug: str = SLUG) -> dict[str, Any] | None:
    with session_factory() as session:
        return session.get_one(KnownDocumentType, slug).photo_rules


def _checked(html: str) -> tuple[str, ...]:
    """Kural işaret kutularından işaretli olanlar (kimlik sırasıyla)."""
    boxes = re.findall(r'<input type="checkbox" name="enabled" value="([a-z_]+)"( checked)?>', html)
    return tuple(rule for rule, checked in boxes if checked)


def _offered(html: str) -> tuple[str, ...]:
    return tuple(re.findall(r'<input type="checkbox" name="enabled" value="([a-z_]+)"', html))


def _size(html: str) -> tuple[str, str]:
    width = re.search(r'name="min_width_px" value="([^"]*)"', html)
    height = re.search(r'name="min_height_px" value="([^"]*)"', html)
    assert width and height, "çözünürlük alanları yok"
    return width.group(1), height.group(1)


def _save(client: TestClient, enabled: list[str] | None, **fields: str) -> Any:
    data: dict[str, Any] = {"min_width_px": "400", "min_height_px": "400", **fields}
    if enabled is not None:
        data["enabled"] = enabled
    return client.post(RULES_URL, data=data, follow_redirects=False)


# --- kurallar panelde görünür ---------------------------------------------------------------------


def test_the_profile_picture_page_lists_every_rule_with_its_default_state(
    client: TestClient,
) -> None:
    page = client.get(PAGE)

    assert page.status_code == 200
    assert '<section class="photo-rules" id="photo-rules">' in page.text
    assert _offered(page.text) == ALL_IDS
    assert _checked(page.text) == DEFAULT_ON
    assert _size(page.text) == ("400", "400")
    for spec in PHOTO_RULE_SPECS:
        assert f"<strong>{spec.label}</strong>" in page.text, spec.id
        assert spec.description in page.text, spec.id
    # Şirket kararı olarak işaretli tek kural ve formun kendi adresi.
    assert page.text.count('class="rule-tag"') == 1
    assert f'<form class="photo-rules-form" method="post" action="{RULES_URL}">' in page.text


def test_rules_are_a_separate_form_from_the_type_form(client: TestClient) -> None:
    page = client.get(PAGE)

    type_form = page.text.split('<form class="type-form"', 1)[1].split("</form>", 1)[0]
    assert 'name="enabled"' not in type_form
    assert 'name="min_width_px"' not in type_form
    assert 'name="photo_rules"' not in page.text


def test_a_type_without_photo_rules_shows_no_rule_section(client: TestClient) -> None:
    for slug in ("russian_passport", "attachment"):
        page = client.get(f"/document-types/{slug}")

        assert page.status_code == 200
        assert 'id="photo-rules"' not in page.text, slug
        assert 'name="enabled"' not in page.text, slug
    assert 'id="photo-rules"' not in client.get("/document-types/new").text


def test_the_list_page_is_unchanged_and_links_to_the_rule_page(client: TestClient) -> None:
    page = client.get("/document-types")

    assert page.status_code == 200
    assert f'href="{PAGE}"' in page.text
    assert 'id="photo-rules"' not in page.text


# --- açıp kapatma ---------------------------------------------------------------------------------


def test_saving_stores_the_set_in_the_catalog_and_the_page_shows_it_back(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    chosen = ["face_visible", "min_resolution", "no_head_covering"]

    response = _save(client, chosen, min_width_px="640", min_height_px="480")

    assert response.status_code == 303
    assert response.headers["location"] == f"{PAGE}?notice=photo_rules#photo-rules"
    stored = _stored(session_factory)
    assert stored == build_photo_rules(
        PhotoRulesForm(enabled=tuple(chosen), min_width_px="640", min_height_px="480")
    )
    assert tuple(stored) == ALL_IDS  # her kural açıkça yazılır
    page = client.get(f"{PAGE}?notice=photo_rules")
    assert "Fotoğraf kuralları kaydedildi." in page.text
    assert _checked(page.text) == ("face_visible", "min_resolution", "no_head_covering")
    assert _size(page.text) == ("640", "480")
    # Katalog (analiz ve dışa aktarım) kural setiyle okunur; kapalı kurallar sorulmaz.
    with session_factory() as session:
        exported = export_catalog(session).get(SLUG)
        assert exported is not None
        assert tuple(s.id for s in enabled_photo_rules(exported.photo_rules)) == tuple(chosen)


def test_a_rule_is_turned_off_and_on_again(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _save(client, list(ALL_IDS))
    assert _checked(client.get(PAGE).text) == ALL_IDS

    _save(client, [i for i in ALL_IDS if i != "no_sunglasses"])
    page = client.get(PAGE)
    assert "no_sunglasses" not in _checked(page.text)
    assert _stored(session_factory)["no_sunglasses"] == {"enabled": False}  # type: ignore[index]

    _save(client, list(ALL_IDS))
    assert "no_sunglasses" in _checked(client.get(PAGE).text)
    assert _stored(session_factory)["no_sunglasses"] == {"enabled": True}  # type: ignore[index]


def test_every_rule_can_be_turned_off_at_once(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = _save(client, None)  # hiç işaret kutusu gönderilmez

    assert response.status_code == 303
    stored = _stored(session_factory)
    assert stored is not None and all(entry["enabled"] is False for entry in stored.values())
    assert _checked(client.get(PAGE).text) == ()


def test_saving_twice_with_the_same_values_is_harmless(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _save(client, ["single_person"])
    first = _stored(session_factory)

    assert _save(client, ["single_person"]).status_code == 303
    assert _stored(session_factory) == first


def test_saved_rules_survive_a_type_edit(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _save(client, ["single_person"], min_width_px="800")
    before = _stored(session_factory)
    # Tür formu kuralları taşımaz: gövdedeki `photo_rules` ve `enabled` yok sayılır.
    form = client.get(PAGE).text
    assert 'name="expected_file_types"' in form
    response = client.post(
        PAGE,
        data={
            "name": "Profile Picture",
            "file_label": "Profile-Picture",
            "expected_file_types": ["jpeg", "png"],
            "pages_min": "1",
            "pages_max": "1",
            "sides": "single",
            "analyze": "on",
            "allowed_conversions": ["extract_image", "render_image"],
            "output_format": "jpeg",
            "description": "Vesikalık",
            "photo_rules": '{"face_visible": true}',
            "enabled": "face_visible",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303, response.text
    with session_factory() as session:
        row = session.get_one(KnownDocumentType, SLUG)
        assert (row.description, row.photo_rules) == ("Vesikalık", before)


# --- reddedilen değerler --------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "abc", "0", "-3", "12.5", "20001", "  "])
def test_a_bad_pixel_count_is_refused_per_field_and_nothing_is_written(
    client: TestClient, session_factory: sessionmaker[Session], bad: str
) -> None:
    before = _stored(session_factory)

    response = _save(
        client, ["face_visible", "single_person"], min_width_px=bad, min_height_px="480"
    )

    assert response.status_code == 422
    assert "Kurallar kaydedilmedi" in response.text
    assert "En az genişlik: 1 ile 20000 arasında" in response.text
    assert "En az yükseklik:" not in response.text
    # Girilen değerler ve işaretler yerinde durur; kayıt değişmez.
    assert _checked(response.text) == ("face_visible", "single_person")
    assert _size(response.text) == (bad, "480")
    assert _stored(session_factory) == before


def test_the_pixel_counts_are_checked_even_when_the_resolution_rule_is_off(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = _save(client, ["face_visible"], min_height_px="yok")

    assert response.status_code == 422
    assert "En az yükseklik: 1 ile 20000 arasında" in response.text
    assert _stored(session_factory) is None


def test_an_unknown_rule_is_refused_and_nothing_is_written(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = _save(client, ["face_visible", "yuz_tanima"])

    assert response.status_code == 422
    assert "Tanımsız kural: yuz_tanima" in response.text
    assert _stored(session_factory) is None


def test_missing_size_fields_are_refused_rather_than_defaulted(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = client.post(RULES_URL, data={"enabled": ["face_visible"]}, follow_redirects=False)

    assert response.status_code == 422
    assert _stored(session_factory) is None


def test_a_refused_page_is_still_the_whole_edit_page(client: TestClient) -> None:
    response = _save(client, ["face_visible"], min_width_px="x")

    assert 'class="type-form"' in response.text
    assert 'id="examples"' in response.text
    assert "<code>profile_picture</code>" in response.text


# --- olmayan ya da fotoğraf kuralı olmayan tür ----------------------------------------------------


def test_an_unknown_type_is_a_404(client: TestClient) -> None:
    response = client.post(
        "/document-types/yok_boyle_tur/photo-rules",
        data={"min_width_px": "400", "min_height_px": "400"},
    )

    assert response.status_code == 404


def test_a_type_without_photo_rules_refuses_them_even_with_a_bad_form(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    for data in ({"min_width_px": "400", "min_height_px": "400"}, {"min_width_px": "x"}):
        response = client.post("/document-types/russian_passport/photo-rules", data=data)

        assert response.status_code == 404
        assert "fotoğraf kuralı yok" in response.text
    assert _stored(session_factory, "russian_passport") is None


# --- sayfanın öteki çizimleri ---------------------------------------------------------------------


def test_the_rule_section_stays_on_every_render_of_the_edit_page(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _save(client, ["face_visible"])
    stored = _stored(session_factory)

    # Reddedilen tür formu.
    invalid = client.post(PAGE, data={"name": "", "file_label": ""})
    assert invalid.status_code == 422
    assert _checked(invalid.text) == ("face_visible",)

    # Reddedilen ve kabul edilen örnek yüklemesi.
    refused = client.post(
        f"{PAGE}/examples", files=[("files", ("kitap.docx", make_docx_bytes(), "x"))]
    )
    assert refused.status_code == 422
    assert _checked(refused.text) == ("face_visible",)

    assert _stored(session_factory) == stored


def test_the_notice_is_shown_only_for_known_names_and_is_escaped(client: TestClient) -> None:
    assert "Fotoğraf kuralları kaydedildi." in client.get(f"{PAGE}?notice=photo_rules").text
    other = client.get(f"{PAGE}?notice=%3Cscript%3E")
    assert 'role="status"' not in other.text
    assert "<script>" not in other.text
    assert client.get(f"{PAGE}?notice=" + "x" * 33).status_code == 422


# --- kapsam: içerik ve kayıtlar değişmez ----------------------------------------------------------


def test_saving_rules_opens_no_upload_document_or_event(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    def counts() -> tuple[int, int, int]:
        with session_factory() as session:
            return tuple(  # type: ignore[return-value]
                session.scalar(select(func.count()).select_from(model)) or 0
                for model in (Upload, Document, Event)
            )

    before = counts()

    _save(client, ["face_visible"])
    _save(client, None)

    assert counts() == before


def test_the_only_catalog_column_the_rules_change_is_photo_rules(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    def columns() -> dict[str, Any]:
        with session_factory() as session:
            row = session.get_one(KnownDocumentType, SLUG)
            return {
                key: value
                for key, value in vars(row).items()
                if not key.startswith("_") and key != "photo_rules"
            }

    before = columns()

    _save(client, ["single_person"], min_width_px="700")

    assert columns() == before
