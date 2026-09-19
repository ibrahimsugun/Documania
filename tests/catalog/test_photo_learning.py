"""11.8.1 — fotoğraf örneklerinden öğrenme: kabul edilen fotoğraflar örnek işaretlenir ve tür
açıklamasını besler (`app.catalog.describe`).

Kabul edilen fotoğraf: fotoğraf türünün `active` çıktısı, kaynak sayfalarının saklı kontrolünde
(11.7.1) şu an açık her kural `pass`. Satırlar ve dosyalar sentetiktir
(`tests/fixtures/accepted_photos.py`, `tests/fixtures/gen.py`); yapay zekâ canlı çağrılmaz (ağsız
test sağlayıcısı). Uçtan uca akış `tests/test_scenarios_s01_s05.py`, panel
`tests/web/test_accepted_photos_page.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfWriter
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai import (
    AnalysisProvider,
    PageAnalysisRequest,
    PhotoCheck,
    TypeDescriptionError,
    TypeDescriptionRequest,
    validate_type_description,
)
from app.ai.prompts import load_type_description_instructions
from app.catalog import (
    CatalogEntry,
    enabled_photo_rules,
    import_catalog,
    load_seed_catalog,
    read_photo_rules,
    validate_catalog,
)
from app.catalog.describe import (
    MAX_DESCRIPTION_PAGES,
    AcceptedPhoto,
    ExamplePage,
    NoExamplePagesError,
    accepted_photos,
    build_description_prompt,
    describe_type,
    format_description,
    is_accepted_photo,
)
from app.config import Settings
from app.db.models import Document, DocumentStatus, Event, Page
from app.pipeline.render import image_copy, render_pdf_images
from app.storage import DataLayout, prepare_data_dir, sha256_file
from tests.ai.payloads import description_payload
from tests.catalog.conftest import RecordFactory
from tests.fixtures.accepted_photos import (
    FOLDER,
    OPEN_RULES,
    PHOTO,
    PhotoRows,
    stored_check,
)
from tests.fixtures.gen import (
    make_docx_bytes,
    make_half_filled_image_bytes,
    make_pdf_bytes,
    make_portrait_image_bytes,
)

CATALOG = load_seed_catalog()
PHOTO_ENTRY = CATALOG.get(PHOTO)
PASSPORT = "russian_passport"
DEFINITION = "Omuzdan yukarı, yüz ortada ve karşıya bakıyor; düz açık arka plan"


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


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, database_url="sqlite://")


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        import_catalog(db_session, CATALOG)
        db_session.flush()
        yield db_session


@pytest.fixture
def rows(session: Session, layout: DataLayout) -> PhotoRows:
    return PhotoRows(session, layout)


def _photo_provider() -> DescribingProvider:
    return DescribingProvider(
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


def _ids(photos: tuple[AcceptedPhoto, ...]) -> list[int]:
    return [photo.document_id for photo in photos]


def _checks(*payloads: dict[str, Any] | None) -> list[PhotoCheck | None]:
    return [None if payload is None else PhotoCheck.model_validate(payload) for payload in payloads]


def _files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _place_example(layout: DataLayout, name: str, content: bytes, slug: str = PHOTO) -> None:
    directory = layout.type_examples_dir(slug)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(content)


def _copy(content: bytes, settings: Settings) -> bytes:
    return image_copy(content, jpeg_quality=settings.page_render_jpeg_quality).content


def _pageless_pdf() -> bytes:
    """Geçerli ama sayfasız PDF (render edilecek ilk sayfası yok)."""
    buffer = BytesIO()
    PdfWriter().write(buffer)
    return buffer.getvalue()


# --- hangi fotoğraf örnektir (saf kural) --------------------------------------------------------

RULES = enabled_photo_rules(None)


@pytest.mark.parametrize("pages", [1, 2], ids=["tek-sayfa", "iki-sayfa"])
def test_every_open_rule_passing_on_every_page_marks_the_photo(pages: int) -> None:
    assert is_accepted_photo(RULES, _checks(*[stored_check()] * pages))


@pytest.mark.parametrize(
    "checks",
    [
        pytest.param([stored_check({"single_person": "fail"})], id="fail"),
        pytest.param([stored_check({"plain_background": "unsure"})], id="unsure"),
        pytest.param(
            [stored_check(rules=[rule for rule in OPEN_RULES if rule != "no_sunglasses"])],
            id="kural-degerlendirilmemis",
        ),
        pytest.param([None], id="kontrol-yok"),
        pytest.param([stored_check(), stored_check({"face_visible": "fail"})], id="ikinci-sayfa"),
        pytest.param([stored_check(), None], id="ikinci-sayfanin-kontrolu-yok"),
    ],
)
def test_a_photo_not_passing_every_open_rule_is_not_an_example(
    checks: list[dict[str, Any] | None],
) -> None:
    assert not is_accepted_photo(RULES, _checks(*checks))


def test_without_open_rules_or_pages_nothing_is_an_example() -> None:
    assert not is_accepted_photo((), _checks(stored_check()))
    assert not is_accepted_photo(RULES, [])


def test_a_closed_rule_is_not_read() -> None:
    rules = [rule for rule in RULES if rule.id != "no_sunglasses"]

    assert is_accepted_photo(rules, _checks(stored_check({"no_sunglasses": "fail"})))


# --- kabul edilen fotoğraflar kayıtlardan okunur -----------------------------------------------


def test_accepted_photos_are_listed_newest_first(session: Session, rows: PhotoRows) -> None:
    older = rows.add()
    rows.add([stored_check({"neutral_expression": "fail"})])
    newer = rows.add()

    photos = accepted_photos(session, PHOTO, None)

    assert _ids(photos) == [newer.id, older.id]
    assert [(photo.path, photo.created_at) for photo in photos] == [
        (newer.path, newer.created_at),
        (older.path, older.created_at),
    ]


@pytest.mark.parametrize(
    "variant",
    [
        pytest.param({"checks": [stored_check({"single_person": "fail"})]}, id="fail"),
        pytest.param({"checks": [stored_check({"plain_background": "unsure"})]}, id="unsure"),
        pytest.param({"checks": [None]}, id="kontrol-yok"),
        pytest.param({"checks": [{"rules": "bozuk"}]}, id="okunamayan-kayit"),
        pytest.param({"status": DocumentStatus.SUPERSEDED}, id="eski-surum"),
        pytest.param({"status": DocumentStatus.ARCHIVED}, id="arsiv"),
        pytest.param({"pages": [5]}, id="sayfa-yok"),
        pytest.param({"refs": []}, id="kaynak-yok"),
        pytest.param({"refs": {"file_id": 1}}, id="kaynak-liste-degil"),
        pytest.param({"refs": ["x"]}, id="kaynak-sozluk-degil"),
        pytest.param({"refs": [{"file_id": "1", "pages": [0]}]}, id="dosya-kimligi-metin"),
        pytest.param({"refs": [{"file_id": 1, "pages": ["0"]}]}, id="sayfa-metin"),
        pytest.param({"refs": [{"file_id": 1}]}, id="sayfa-listesi-yok"),
        pytest.param({"refs": [{"file_id": 999, "pages": []}]}, id="dosyanin-sayfasi-yok"),
    ],
)
def test_only_active_photos_passing_every_open_rule_are_examples(
    session: Session, rows: PhotoRows, variant: dict[str, Any]
) -> None:
    rows.add(**variant)

    assert accepted_photos(session, PHOTO, None) == ()


def test_the_marks_follow_the_current_rule_set(session: Session, rows: PhotoRows) -> None:
    # Kontrol analiz anındaki açık kurallarladır; kural sonradan açılırsa değerlendirilmemiştir,
    # kapatılırsa sonucu okunmaz.
    clean = rows.add()
    no_sunglasses_fail = rows.add([stored_check({"no_sunglasses": "fail"})])
    head_covering_open = {"no_head_covering": {"enabled": True}}
    sunglasses_closed = {"no_sunglasses": {"enabled": False}}

    assert _ids(accepted_photos(session, PHOTO, None)) == [clean.id]
    assert accepted_photos(session, PHOTO, head_covering_open) == ()
    assert _ids(accepted_photos(session, PHOTO, sunglasses_closed)) == [
        no_sunglasses_fail.id,
        clean.id,
    ]
    evaluated = rows.add([stored_check(rules=(*OPEN_RULES, "no_head_covering"))])
    assert _ids(accepted_photos(session, PHOTO, head_covering_open)) == [evaluated.id]


def test_without_open_rules_no_photo_is_an_example(session: Session, rows: PhotoRows) -> None:
    rows.add()
    closed = {rule.id: {"enabled": False} for rule in read_photo_rules(None)}

    assert accepted_photos(session, PHOTO, closed) == ()


def test_only_photo_types_have_accepted_photos(session: Session, rows: PhotoRows) -> None:
    passport = rows.add(type_slug=PASSPORT)
    photo = rows.add()

    assert accepted_photos(session, PASSPORT, None) == ()
    assert _ids(accepted_photos(session, PHOTO, None)) == [photo.id]
    assert passport.id != photo.id


def test_a_whole_file_source_needs_every_page_of_the_file(
    session: Session, rows: PhotoRows
) -> None:
    # Bütün dosya: kökendeki sayfa listesi boş (K15).
    both = rows.add([stored_check(), stored_check()], pages=[])
    rows.add([stored_check(), stored_check({"face_visible": "fail"})], pages=[])
    rows.add([stored_check(), None], pages=[])

    assert _ids(accepted_photos(session, PHOTO, None)) == [both.id]


def test_every_listed_source_page_must_pass(session: Session, rows: PhotoRows) -> None:
    # Köken yalnız ilk sayfayı gösteriyorsa ikinci sayfanın kontrolü okunmaz.
    first_only = rows.add([stored_check(), stored_check({"face_visible": "fail"})], pages=[0])
    rows.add([stored_check(), stored_check({"face_visible": "fail"})], pages=[0, 1])

    assert _ids(accepted_photos(session, PHOTO, None)) == [first_only.id]


def test_reading_the_marks_writes_nothing(session: Session, rows: PhotoRows) -> None:
    rows.add()
    rows.add([stored_check({"single_person": "fail"})])
    session.commit()
    before = {
        model.__name__: session.scalar(select(func.count()).select_from(model))
        for model in (Document, Page, Event)
    }

    accepted_photos(session, PHOTO, None)

    assert not session.new and not session.dirty and not session.deleted
    assert {
        model.__name__: session.scalar(select(func.count()).select_from(model))
        for model in (Document, Page, Event)
    } == before


# --- kabul edilen fotoğraflar açıklamayı besler ----------------------------------------------


def test_accepted_photos_feed_the_description_without_being_changed(
    session: Session, rows: PhotoRows, layout: DataLayout, settings: Settings
) -> None:
    older = rows.add(content=make_portrait_image_bytes(size=(480, 600)))
    newer = rows.add(content=make_portrait_image_bytes(size=(600, 800)))
    session.commit()
    photos = accepted_photos(session, PHOTO, None)
    before = _files(layout.root)
    provider = _photo_provider()

    generated = describe_type(PHOTO_ENTRY, layout, settings, provider, photos=photos)

    (request,) = provider.descriptions
    # Yeniden eskiye; her fotoğraf EXIF yönelimi uygulanmış bellek kopyasıyla (analiz görüntüsü).
    assert [image.data for image in request.images] == [
        _copy(layout.resolve(newer.path).read_bytes(), settings),
        _copy(layout.resolve(older.path).read_bytes(), settings),
    ]
    assert request.instructions == load_type_description_instructions()
    assert request.prompt.splitlines()[-4:] == [
        "",
        "Görüntüler (2, gönderildiği sırayla):",
        "1. kabul edilen fotoğraf 1",
        "2. kabul edilen fotoğraf 2",
    ]
    assert "Fotoğraf türü: evet" in request.prompt.splitlines()
    assert (generated.pages, generated.omitted, generated.skipped) == ((), 0, ())
    assert (generated.photos, generated.photos_omitted) == ((newer.id, older.id), 0)
    assert generated.description.accepted_photo == DEFINITION
    assert generated.text == format_description(generated.description)
    assert generated.text.endswith(f"Kabul edilen fotoğraf: {DEFINITION}.")
    # Fotoğraf değişmez, kopyalanmaz; açıklama hiçbir dosya yazmaz (K11).
    assert _files(layout.root) == before


def test_the_request_carries_no_identity_of_the_photos(
    session: Session, rows: PhotoRows, layout: DataLayout, settings: Settings
) -> None:
    document = rows.add()
    provider = _photo_provider()

    describe_type(
        PHOTO_ENTRY, layout, settings, provider, photos=accepted_photos(session, PHOTO, None)
    )

    (request,) = provider.descriptions
    for value in (FOLDER, "Ornek", "E0001", document.path, "Profile-Picture-", "belge"):
        assert value not in request.prompt, value


@pytest.mark.parametrize(
    ("example_pages", "photo_count", "sent_pages", "sent_photos", "omitted", "photos_omitted"),
    [
        pytest.param(10, 6, 4, 4, 6, 2, id="ikisi-de-fazla-yari-yariya"),
        pytest.param(2, 10, 2, 6, 0, 4, id="ornek-az-foto-bosluga"),
        pytest.param(10, 1, 7, 1, 3, 0, id="tek-foto-bir-yer"),
        pytest.param(10, 0, 8, 0, 2, 0, id="foto-yok-11-3-gibi"),
        pytest.param(0, 10, 0, 8, 0, 2, id="ornek-yok"),
        pytest.param(3, 2, 3, 2, 0, 0, id="hepsi-sigar"),
    ],
)
def test_examples_and_photos_share_the_page_limit(
    session: Session,
    rows: PhotoRows,
    layout: DataLayout,
    settings: Settings,
    example_pages: int,
    photo_count: int,
    sent_pages: int,
    sent_photos: int,
    omitted: int,
    photos_omitted: int,
) -> None:
    if example_pages:
        _place_example(layout, "ornek.pdf", make_pdf_bytes(example_pages))
    for _ in range(photo_count):
        rows.add()
    photos = accepted_photos(session, PHOTO, None)
    provider = _photo_provider()

    generated = describe_type(PHOTO_ENTRY, layout, settings, provider, photos=photos)

    assert MAX_DESCRIPTION_PAGES == 8
    (request,) = provider.descriptions
    assert len(request.images) == sent_pages + sent_photos
    assert (len(generated.pages), len(generated.photos)) == (sent_pages, sent_photos)
    assert (generated.omitted, generated.photos_omitted) == (omitted, photos_omitted)
    # Örnek sayfalar önce, en yeni fotoğraflar sonra.
    assert generated.photos == tuple(_ids(photos)[:sent_photos])
    lines = request.prompt.splitlines()
    assert lines[-(sent_pages + sent_photos) :] == [
        *(f"{number}. örnek 1, sayfa {number}" for number in range(1, sent_pages + 1)),
        *(
            f"{sent_pages + number}. kabul edilen fotoğraf {number}"
            for number in range(1, sent_photos + 1)
        ),
    ]


def test_an_unreadable_photo_is_skipped_and_the_next_one_is_sent(
    session: Session, rows: PhotoRows, layout: DataLayout, settings: Settings
) -> None:
    good = rows.add()
    corrupt = rows.add(content=b"\xff\xd8\xff bozuk jpeg")
    missing = rows.add()
    layout.resolve(missing.path).unlink()
    word = rows.add(content=make_docx_bytes(), extension="docx")
    escaping = rows.add()
    escaping.path = "../disari.jpeg"
    empty_pdf = rows.add(content=_pageless_pdf(), extension="pdf")
    photos = accepted_photos(session, PHOTO, None)
    provider = _photo_provider()

    generated = describe_type(PHOTO_ENTRY, layout, settings, provider, photos=photos, max_pages=2)

    # Açılamayanlar sınırı tüketmez; mesaj belge numarasını taşır, dosya adını değil.
    assert generated.photos == (good.id,)
    assert generated.skipped == tuple(
        f"Kabul edilen fotoğraf (belge {document.id}) açılamadı."
        for document in (empty_pdf, escaping, word, missing, corrupt)
    )
    assert generated.photos_omitted == 0
    assert all(FOLDER not in message for message in generated.skipped)


def test_an_oversized_photo_is_skipped_without_being_read(
    session: Session, rows: PhotoRows, layout: DataLayout
) -> None:
    small = rows.add(content=make_half_filled_image_bytes(size=(20, 20)))
    large = rows.add()
    limit = layout.resolve(small.path).stat().st_size
    settings = Settings(_env_file=None, database_url="sqlite://", max_upload_file_size_bytes=limit)
    provider = _photo_provider()

    generated = describe_type(
        PHOTO_ENTRY, layout, settings, provider, photos=accepted_photos(session, PHOTO, None)
    )

    assert generated.photos == (small.id,)
    assert generated.skipped == (f"Kabul edilen fotoğraf (belge {large.id}) 0 MB sınırını aşıyor.",)


def test_without_any_readable_example_or_photo_nothing_is_requested(
    session: Session, rows: PhotoRows, layout: DataLayout, settings: Settings
) -> None:
    broken = rows.add(content=b"bozuk")
    provider = _photo_provider()

    with pytest.raises(NoExamplePagesError) as caught:
        describe_type(
            PHOTO_ENTRY,
            layout,
            settings,
            provider,
            photos=accepted_photos(session, PHOTO, None),
        )

    assert caught.value.skipped == (f"Kabul edilen fotoğraf (belge {broken.id}) açılamadı.",)
    assert provider.descriptions == []


def test_a_pdf_photo_is_sent_as_its_first_page(
    session: Session, rows: PhotoRows, layout: DataLayout, settings: Settings
) -> None:
    content = make_pdf_bytes(2)
    rows.add(content=content, extension="pdf")
    provider = _photo_provider()

    generated = describe_type(
        PHOTO_ENTRY, layout, settings, provider, photos=accepted_photos(session, PHOTO, None)
    )

    (request,) = provider.descriptions
    rendered, _ = render_pdf_images(
        content,
        dpi=settings.page_render_dpi,
        max_long_edge=settings.page_render_max_long_edge_px,
        jpeg_quality=settings.page_render_jpeg_quality,
        max_pages=1,
    )
    assert [image.data for image in request.images] == rendered
    assert len(generated.photos) == 1


# --- fotoğraf türü olmayan tür ----------------------------------------------------------------


@pytest.fixture
def card(make_record: RecordFactory) -> CatalogEntry:
    return validate_catalog([make_record()]).root[0]


def test_photos_are_ignored_for_a_type_that_is_not_a_photo(
    session: Session, rows: PhotoRows, layout: DataLayout, settings: Settings, card: CatalogEntry
) -> None:
    example = make_half_filled_image_bytes()
    _place_example(layout, "ornek.jpg", example, slug=card.slug)
    rows.add()
    photos = accepted_photos(session, PHOTO, None)
    provider = DescribingProvider(description_payload())

    generated = describe_type(card, layout, settings, provider, photos=photos)

    assert photos
    (request,) = provider.descriptions
    assert [image.data for image in request.images] == [_copy(example, settings)]
    assert "Fotoğraf türü" not in request.prompt
    assert "kabul edilen fotoğraf" not in request.prompt
    assert (generated.photos, generated.photos_omitted) == ((), 0)
    assert "Kabul edilen fotoğraf" not in generated.text


def test_an_accepted_photo_definition_for_a_non_photo_type_is_rejected(
    layout: DataLayout, settings: Settings, card: CatalogEntry
) -> None:
    _place_example(layout, "ornek.jpg", make_half_filled_image_bytes(), slug=card.slug)
    provider = DescribingProvider(description_payload(accepted_photo=DEFINITION))

    with pytest.raises(TypeDescriptionError) as caught:
        describe_type(card, layout, settings, provider)

    assert caught.value.problems == ["accepted_photo: fotoğraf türü olmayan belgede null olmalı"]


def test_a_photo_type_may_leave_the_definition_empty(
    session: Session, rows: PhotoRows, layout: DataLayout, settings: Settings
) -> None:
    rows.add()
    provider = DescribingProvider(description_payload(accepted_photo=None))

    generated = describe_type(
        PHOTO_ENTRY, layout, settings, provider, photos=accepted_photos(session, PHOTO, None)
    )

    assert generated.photos
    assert "Kabul edilen fotoğraf" not in generated.text


# --- istek metni, talimat ve açıklama metni --------------------------------------------------


def test_the_prompt_marks_the_photo_type_and_numbers_photos_after_the_examples() -> None:
    prompt = build_description_prompt(
        PHOTO_ENTRY, [ExamplePage("a.jpg", 1), ExamplePage("b.pdf", 1)], photos=2
    )

    assert prompt.splitlines() == [
        "Belge türü: Profile Picture (`profile_picture`)",
        "Ülke: belirtilmemiş",
        "Yüz yapısı: tek yüz (single)",
        "Beklenen sayfa: 1–1",
        "Zorunlu alanlar: yok",
        "Fotoğraf türü: evet",
        "",
        "Görüntüler (4, gönderildiği sırayla):",
        "1. örnek 1, sayfa 1",
        "2. örnek 2, sayfa 1",
        "3. kabul edilen fotoğraf 1",
        "4. kabul edilen fotoğraf 2",
    ]


def test_the_instructions_ask_for_the_accepted_photo_without_describing_people() -> None:
    text = load_type_description_instructions()

    assert "`accepted_photo`" in text
    assert '"Fotoğraf türü: evet"' in text
    assert "kabul ettiği fotoğraflar" in text
    assert "Fotoğraftaki kişiyi tarif etme" in text
    assert "Fotoğraf türü\n  olmayan belgede her zaman `null`" in text


@pytest.mark.parametrize(
    ("definition", "sentence"),
    [
        ("Düz açık arka plan", "Kabul edilen fotoğraf: Düz açık arka plan."),
        ("  Düz arka plan;\n renkli.  ", "Kabul edilen fotoğraf: Düz arka plan; renkli."),
    ],
)
def test_the_definition_closes_the_description_text(definition: str, sentence: str) -> None:
    described = validate_type_description(
        description_payload(side_differences="Arkada MRZ", accepted_photo=definition)
    )

    assert format_description(described).endswith(f"Ön/arka yüz: Arkada MRZ. {sentence}")
