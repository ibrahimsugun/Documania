"""11.8.1 — Belge Türleri ekranında kabul edilen fotoğraflar örnek olarak işaretli görünür ve
"Örneklerden açıklama üret" onları örnek belgelerle birlikte yapay zekâya verir; üretilen metne
şirketin kabul ettiği fotoğrafın tanımı girer, hiçbir şey kaydedilmez.

Satırlar ve fotoğraflar sentetiktir (`tests/fixtures/accepted_photos.py`); yapay zekâ canlı
çağrılmaz (ağsız test sağlayıcısı). Yalnız `TestClient`: tarayıcıda çizim görülmedi."""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai import AnalysisProvider, PageAnalysisRequest, TypeDescriptionRequest
from app.catalog import import_catalog, load_record, load_seed_catalog
from app.config import Settings
from app.db.models import AccessLog, Document, DocumentStatus, Event, KnownDocumentType, Upload
from app.pipeline.render import image_copy
from app.storage import DataLayout, sha256_file
from app.web.routers.catalog import get_description_provider
from tests.ai.payloads import description_payload
from tests.fixtures.accepted_photos import PHOTO, PhotoRows, stored_check

PAGE = f"/document-types/{PHOTO}"
DESCRIBE_URL = f"{PAGE}/description"
RULES_URL = f"{PAGE}/photo-rules"
BUTTON = f'formaction="{DESCRIBE_URL}"'
DEFINITION = "Omuzdan yukarı, yüz ortada; düz açık arka plan, eşit ışık"
SEED_DESCRIPTION = load_seed_catalog().get(PHOTO).prompt_description  # type: ignore[union-attr]

type Build = Callable[[PhotoRows], list[int]]


class DescribingProvider(AnalysisProvider):
    """Ağsız test sağlayıcısı: tür açıklaması isteğini saklar, verilen yanıtı döner."""

    name = "aciklayan"

    def __init__(self, response: object) -> None:
        super().__init__(model="aciklayan-model")
        self.response = response
        self.descriptions: list[TypeDescriptionRequest] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        raise AssertionError("sayfa analizi istenmemeli")

    def _request_description(self, request: TypeDescriptionRequest) -> object:
        self.descriptions.append(request)
        return self.response


@pytest.fixture(autouse=True)
def seeded(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()


@pytest.fixture
def described(app: FastAPI) -> DescribingProvider:
    provider = DescribingProvider(
        description_payload(
            layout="Tek kişinin vesikalık fotoğrafı; metin yok",
            headings=[],
            languages=[],
            scripts=[],
            field_locations=[],
            mrz=None,
            accepted_photo=DEFINITION,
        )
    )
    app.dependency_overrides[get_description_provider] = lambda: provider
    return provider


def _photos(
    session_factory: sessionmaker[Session], layout: DataLayout, build: Build
) -> list[Document]:
    """Çıktı belgelerini kurar ve commit eder; `build`'in döndürdüğü belgeleri sırayla verir."""
    with session_factory() as session:
        ids = build(PhotoRows(session, layout))
        session.commit()
        return [session.get_one(Document, document_id) for document_id in ids]


def _section(page: str) -> str:
    match = re.search(r'<section class="accepted-photos".*?</section>', page, re.S)
    assert match, "kabul edilen fotoğraflar bölümü yok"
    return match.group(0)


def _linked(fragment: str) -> list[int]:
    return [int(value) for value in re.findall(r'href="/documents/(\d+)/history"', fragment)]


def _photo_form(**overrides: Any) -> dict[str, Any]:
    """Profile Picture türünün kayıtlı değerleriyle tür formu (tohum katalog)."""
    data: dict[str, Any] = {
        "slug": PHOTO,
        "name": "Profile Picture",
        "file_label": "Profile Picture",
        "country": "",
        "description": "Çalışanın vesikalık veya portre fotoğrafı.",
        "expected_file_types": ["jpeg", "png", "pdf"],
        "pages_min": "1",
        "pages_max": "1",
        "sides": "single",
        "analyze": "on",
        "required_fields": "",
        "allowed_conversions": ["extract_image", "render_image"],
        "output_format": "jpeg",
        "prompt_description": SEED_DESCRIPTION,
    }
    data.update(overrides)
    return data


def _field_value(page: str, name: str) -> str:
    match = re.search(rf'name="{name}" value="([^"]*)"', page)
    assert match, f"{name} alanı yok"
    return html.unescape(match.group(1))


def _counts(session_factory: sessionmaker[Session]) -> dict[str, int]:
    with session_factory() as session:
        return {
            model.__name__: session.scalar(select(func.count()).select_from(model)) or 0
            for model in (Upload, Document, Event, AccessLog, KnownDocumentType)
        }


def _files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# --- işaret panelde görünür ----------------------------------------------------------------------


def test_the_photo_type_page_marks_only_accepted_photos_as_examples(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    older, failed, unsure, archived, newer = _photos(
        session_factory,
        layout,
        lambda rows: [
            rows.add().id,
            rows.add([stored_check({"single_person": "fail"})]).id,
            rows.add([stored_check({"plain_background": "unsure"})]).id,
            rows.add(status=DocumentStatus.ARCHIVED).id,
            rows.add().id,
        ],
    )

    page = client.get(PAGE)

    assert page.status_code == 200
    section = _section(page.text)
    assert "<h2>Kabul edilen fotoğraflar</h2>" in section
    assert "2 fotoğraf örnek olarak işaretli." in section
    assert _linked(section) == [newer.id, older.id]
    assert section.count('<span class="rule-tag">örnek</span>') == 2
    for excluded in (failed, unsure, archived):
        assert f"Belge {excluded.id}<" not in section
    assert f"({newer.created_at:%Y-%m-%d})" in section
    # Bölüm fotoğraf kurallarının altında, örnek belgelerin üstünde; fotoğraf açılmaz.
    assert (
        page.text.index('id="photo-rules"')
        < page.text.index('id="accepted-photos"')
        < page.text.index('id="examples"')
    )
    assert "<img" not in section
    # Yüklenmiş örnek yok: düğme kabul edilen fotoğraflar yüzünden çıkar.
    assert BUTTON in page.text
    assert _counts(session_factory)["AccessLog"] == 0


def test_without_accepted_photos_the_section_says_so_and_offers_no_generation(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    _photos(
        session_factory,
        layout,
        lambda rows: [rows.add([stored_check({"face_visible": "fail"})]).id],
    )

    page = client.get(PAGE)

    section = _section(page.text)
    assert "Henüz örnek olarak işaretlenen kabul edilmiş fotoğraf yok." in section
    assert _linked(section) == []
    assert BUTTON not in page.text


def test_only_the_newest_photos_are_listed(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    documents = _photos(session_factory, layout, lambda rows: [rows.add().id for _ in range(10)])

    section = _section(client.get(PAGE).text)

    assert "10 fotoğraf örnek olarak işaretli." in section
    assert _linked(section) == [document.id for document in reversed(documents)][:8]
    assert "Daha eski 2 fotoğraf da örnek olarak işaretli." in section


def test_types_without_photo_rules_have_no_accepted_photo_section(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    _photos(session_factory, layout, lambda rows: [rows.add(type_slug="russian_passport").id])

    page = client.get("/document-types/russian_passport")

    assert page.status_code == 200
    assert 'id="accepted-photos"' not in page.text


def test_changing_the_rule_set_changes_the_marks(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    # Kontrol analiz anındaki açık kurallarladır: sonradan açılan kural değerlendirilmemiştir,
    # kapatılan kuralın sonucu okunmaz.
    (clean, expressive) = _photos(
        session_factory,
        layout,
        lambda rows: [rows.add().id, rows.add([stored_check({"neutral_expression": "fail"})]).id],
    )
    defaults = [
        "face_visible",
        "single_person",
        "neutral_expression",
        "plain_background",
        "min_resolution",
        "no_sunglasses",
    ]

    def save(enabled: list[str]) -> None:
        data = {"enabled": enabled, "min_width_px": "400", "min_height_px": "400"}
        response = client.post(RULES_URL, data=data, follow_redirects=False)
        assert response.status_code == 303, response.text

    assert _linked(_section(client.get(PAGE).text)) == [clean.id]
    save([*defaults, "no_head_covering"])
    assert _linked(_section(client.get(PAGE).text)) == []
    save([rule for rule in defaults if rule != "neutral_expression"])
    assert _linked(_section(client.get(PAGE).text)) == [expressive.id, clean.id]


# --- işaretli fotoğraflar açıklamayı besler -----------------------------------------------------


def test_accepted_photos_feed_the_generated_description_which_is_not_saved(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    described: DescribingProvider,
) -> None:
    older, newer = _photos(session_factory, layout, lambda rows: [rows.add().id, rows.add().id])
    counts, files = _counts(session_factory), _files(layout.root)

    response = client.post(DESCRIBE_URL, data=_photo_form())

    assert response.status_code == 200, response.text
    (request,) = described.descriptions
    quality = Settings(database_url="sqlite://").page_render_jpeg_quality
    assert [image.data for image in request.images] == [
        image_copy(layout.resolve(document.path).read_bytes(), jpeg_quality=quality).content
        for document in (newer, older)
    ]
    assert "Fotoğraf türü: evet" in request.prompt
    text = _field_value(response.text, "prompt_description")
    assert text.endswith(f"Kabul edilen fotoğraf: {DEFINITION}.")
    assert "0 örnek sayfadan ve\n    2 kabul edilen fotoğraftan üretildi" in response.text
    assert f"<dt>Kabul edilen fotoğraf</dt>\n    <dd>{DEFINITION}</dd>" in response.text
    generated = re.search(
        r'<section class="generated-description".*?</section>', response.text, re.S
    )
    assert generated and _linked(generated.group(0)) == [newer.id, older.id]
    # Kaydedilmez, olay yazılmaz, fotoğraf açılmış sayılmaz, dosya değişmez.
    with session_factory() as session:
        assert load_record(session, PHOTO)["prompt_description"] == SEED_DESCRIPTION
    assert _counts(session_factory) == counts
    assert _files(layout.root) == files


def test_an_unreadable_photo_is_named_next_to_the_description(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    described: DescribingProvider,
) -> None:
    good, broken = _photos(
        session_factory, layout, lambda rows: [rows.add().id, rows.add(content=b"bozuk").id]
    )

    response = client.post(DESCRIBE_URL, data=_photo_form())

    assert response.status_code == 200, response.text
    assert "Açılamayan örnekler ve fotoğraflar atlandı:" in response.text
    assert f"Kabul edilen fotoğraf (belge {broken.id}) açılamadı." in response.text
    (request,) = described.descriptions
    assert len(request.images) == 1
    assert good.id != broken.id


def test_without_examples_or_accepted_photos_nothing_is_requested(
    client: TestClient, described: DescribingProvider
) -> None:
    response = client.post(DESCRIBE_URL, data=_photo_form())

    assert response.status_code == 422
    assert "bu türün açılabilen örneği yok" in response.text
    assert described.descriptions == []
