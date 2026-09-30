"""11.3.1 — örneklerden yapılandırılmış tür açıklaması üretimi (`app.catalog.describe`).

Örnekler sentetiktir (`tests/fixtures/gen.py`); yapay zekâ canlı çağrılmaz — kayıtlı yanıt
(`tests/fixtures/ai/type_descriptions/passport`) ya da ağsız test sağlayıcısı kullanılır.
"""

from __future__ import annotations

import json
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

from app.ai import (
    AnalysisProvider,
    PageAnalysisRequest,
    ProviderServerError,
    TypeDescriptionError,
    TypeDescriptionRequest,
    validate_type_description,
)
from app.ai.prompts import load_type_description_instructions
from app.ai.recording_provider import RecordingProvider
from app.catalog import CatalogEntry, compile_catalog, validate_catalog
from app.catalog.describe import (
    EXCLUDED_MESSAGE,
    MAX_DESCRIPTION_PAGES,
    ExamplePage,
    NoExamplePagesError,
    TypeNotAnalyzedError,
    build_description_prompt,
    collect_example_pages,
    describe_type,
    format_description,
    unverified_ai_examples,
)
from app.config import Settings
from app.db.models import ExampleFileRecord, ExampleLabel, ExampleMethod, utcnow
from app.storage import DataLayout, FileKind, detect_file_kind, prepare_data_dir, sha256_file
from tests.ai.payloads import description_payload
from tests.catalog.conftest import RecordFactory
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    make_document_pdf_bytes,
    make_half_filled_image_bytes,
    make_owner_locked_pdf_bytes,
    make_pdf_bytes,
    passport_page,
)

ROOT = Path(__file__).resolve().parents[2]
RECORDING = ROOT / "tests" / "fixtures" / "ai" / "type_descriptions" / "passport"
SLUG = "sample_card"


class DescribingProvider(AnalysisProvider):
    """Ağsız test sağlayıcısı: tür açıklaması isteğini saklar, verilen yanıtı/hatayı döner."""

    name = "aciklayan"

    def __init__(self, response: object) -> None:
        super().__init__(model="aciklayan-model")
        self.response = response
        self.descriptions: list[TypeDescriptionRequest] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        raise AssertionError("sayfa analizi istenmemeli")

    def _request_description(self, request: TypeDescriptionRequest) -> object:
        self.descriptions.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Yeniden denemenin beklemesini kaydeder, beklemez (03.5.1)."""
    calls: list[float] = []
    monkeypatch.setattr("app.ai.provider.time.sleep", calls.append)
    return calls


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, database_url="sqlite://")


@pytest.fixture
def entry(make_record: RecordFactory) -> CatalogEntry:
    return validate_catalog([make_record()]).root[0]


def _place(layout: DataLayout, name: str, content: bytes, slug: str = SLUG) -> Path:
    """Örneği dizine elle koyar (11.2.1 yüklemesinin yazdığı yer; içerik denetlenmeden)."""
    directory = layout.type_examples_dir(slug)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(content)
    return path


def _passport_pdf() -> bytes:
    page = passport_page(
        PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1)
    )
    return make_document_pdf_bytes([page])


def _files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# --- örnek sayfaları --------------------------------------------------------------------------


def test_pages_come_from_examples_in_name_order_and_page_order(
    layout: DataLayout, settings: Settings
) -> None:
    _place(layout, "b-foto.png", make_half_filled_image_bytes("PNG"))
    _place(layout, "a-sablon.pdf", make_pdf_bytes(2))
    _place(layout, "c-tarama.jpg", make_half_filled_image_bytes("JPEG"))

    collected = collect_example_pages(layout, settings, SLUG)

    assert collected.pages == (
        ExamplePage("a-sablon.pdf", 1),
        ExamplePage("a-sablon.pdf", 2),
        ExamplePage("b-foto.png", 1),
        ExamplePage("c-tarama.jpg", 1),
    )
    assert [image.media_type for image in collected.images] == [
        "image/jpeg",
        "image/jpeg",
        "image/png",
        "image/jpeg",
    ]
    assert (collected.omitted, collected.skipped) == (0, ())


def test_pdf_pages_use_the_analysis_render_settings(layout: DataLayout) -> None:
    _place(layout, "a.pdf", make_pdf_bytes(1))
    small = Settings(_env_file=None, database_url="sqlite://", page_render_max_long_edge_px=300)

    (image,) = collect_example_pages(layout, small, SLUG).images

    assert detect_file_kind(image.data) is FileKind.JPEG
    with Image.open(BytesIO(image.data)) as opened:
        assert max(opened.size) <= 300


def test_page_limit_is_applied_across_examples_and_the_rest_is_counted(
    layout: DataLayout, settings: Settings
) -> None:
    _place(layout, "a.pdf", make_pdf_bytes(2))
    _place(layout, "b.pdf", make_pdf_bytes(4))
    _place(layout, "c.png", make_half_filled_image_bytes("PNG"))

    collected = collect_example_pages(layout, settings, SLUG, max_pages=3)

    assert collected.pages == (
        ExamplePage("a.pdf", 1),
        ExamplePage("a.pdf", 2),
        ExamplePage("b.pdf", 1),
    )
    assert len(collected.images) == 3
    assert collected.omitted == 3 + 1


def test_default_limit_is_the_documented_one(layout: DataLayout, settings: Settings) -> None:
    _place(layout, "a.pdf", make_pdf_bytes(MAX_DESCRIPTION_PAGES + 2))

    collected = collect_example_pages(layout, settings, SLUG)

    assert len(collected.pages) == MAX_DESCRIPTION_PAGES
    assert collected.omitted == 2


def test_owner_locked_pdf_example_is_rendered_not_skipped(
    layout: DataLayout, settings: Settings
) -> None:
    # tm 137: resmî kurum PDF'i (sahip parolalı, AES) örnek olarak işlenir; açmak için parola
    # isteyen PDF atlanır ve raporlanır.
    _place(layout, "a-resmi-form.pdf", make_owner_locked_pdf_bytes(2))
    _place(layout, "b-acma-parolali.pdf", make_owner_locked_pdf_bytes(1, user_password="gizli"))

    collected = collect_example_pages(layout, settings, SLUG)

    assert collected.pages == (
        ExamplePage("a-resmi-form.pdf", 1),
        ExamplePage("a-resmi-form.pdf", 2),
    )
    assert len(collected.skipped) == 1
    assert "'b-acma-parolali.pdf'" in collected.skipped[0]


def test_unreadable_examples_are_skipped_and_reported(
    layout: DataLayout, settings: Settings
) -> None:
    _place(layout, "a-bozuk.pdf", b"%PDF-1.4 bozuk")
    _place(layout, "b-kesik.png", make_half_filled_image_bytes("PNG")[:60])
    _place(layout, "c-metin.jpg", b"duz metin")
    _place(layout, "d-iyi.jpg", make_half_filled_image_bytes("JPEG"))

    collected = collect_example_pages(layout, settings, SLUG)

    assert collected.pages == (ExamplePage("d-iyi.jpg", 1),)
    assert len(collected.skipped) == 3
    assert "'a-bozuk.pdf'" in collected.skipped[0]
    assert "'b-kesik.png'" in collected.skipped[1]
    assert "'c-metin.jpg'" in collected.skipped[2]


def test_truncated_image_that_passes_the_check_is_skipped(
    layout: DataLayout, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Pillow'un `verify()`'ı geçip kopyalamada düşen görüntü (kesik veri) de atlanır.
    _place(layout, "a.jpg", make_half_filled_image_bytes("JPEG"))

    def broken(content: bytes, *, jpeg_quality: int) -> Any:
        raise OSError("image file is truncated")

    monkeypatch.setattr("app.catalog.describe.image_copy", broken)

    collected = collect_example_pages(layout, settings, SLUG)

    assert collected.pages == ()
    assert collected.skipped == ("'a.jpg' dosyası açılamadı; bozuk olabilir.",)


def test_oversized_example_is_skipped_without_reading_it(
    layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    _place(layout, "buyuk.pdf", make_pdf_bytes(3))
    tight = Settings(_env_file=None, database_url="sqlite://", max_upload_file_size_bytes=100)
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail(f"{self.name} okunmamalıydı"))

    collected = collect_example_pages(layout, tight, SLUG)

    assert collected.pages == ()
    assert collected.skipped == ("'buyuk.pdf' dosyası 0 MB sınırını aşıyor.",)


def test_example_removed_after_listing_is_skipped(
    layout: DataLayout, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _place(layout, "a.pdf", make_pdf_bytes(1))
    monkeypatch.setattr("app.catalog.describe.example_path", lambda *args: None)

    collected = collect_example_pages(layout, settings, SLUG)

    assert collected.skipped == ("'a.pdf' dosyası bulunamadı.",)


def test_examples_of_other_types_are_not_used(layout: DataLayout, settings: Settings) -> None:
    _place(layout, "baska.pdf", make_pdf_bytes(1), slug="other_type")

    assert collect_example_pages(layout, settings, SLUG).pages == ()


# --- istek metni -------------------------------------------------------------------------------


def test_prompt_carries_the_type_facts_and_the_image_order_without_file_names(
    entry: CatalogEntry,
) -> None:
    pages = [
        ExamplePage("Ornekova-pasaport.pdf", 1),
        ExamplePage("Ornekova-pasaport.pdf", 2),
        ExamplePage("ikinci.jpg", 1),
    ]

    prompt = build_description_prompt(entry, pages)

    assert prompt == (
        "Belge türü: Sample Card (`sample_card`)\n"
        "Ülke: RS\n"
        "Yüz yapısı: tek yüz (single)\n"
        "Beklenen sayfa: 1–2\n"
        "Zorunlu alanlar: surname, document_number\n"
        "\n"
        "Görüntüler (3, gönderildiği sırayla):\n"
        "1. örnek 1, sayfa 1\n"
        "2. örnek 1, sayfa 2\n"
        "3. örnek 2, sayfa 1"
    )
    assert "Ornekova" not in prompt


def test_prompt_for_a_front_back_type_without_country_or_fields(
    make_record: RecordFactory,
) -> None:
    entry = validate_catalog(
        [
            make_record(
                country=None,
                sides="front_back",
                front_back_layouts=["separate"],
                expected_pages={"min": 2, "max": 2},
                required_fields=[],
            )
        ]
    ).root[0]

    prompt = build_description_prompt(entry, [ExamplePage("a.png", 1)])

    assert "Ülke: belirtilmemiş\n" in prompt
    assert "Yüz yapısı: ön ve arka yüz (front_back)\n" in prompt
    assert "Beklenen sayfa: 2–2\n" in prompt
    assert "Zorunlu alanlar: yok\n" in prompt


def test_prompt_for_a_type_without_a_page_range_leaves_the_pages_out(
    make_record: RecordFactory,
) -> None:
    entry = validate_catalog([make_record(expected_pages=None)]).root[0]

    prompt = build_description_prompt(entry, [ExamplePage("a.png", 1)])

    assert "Yüz yapısı: tek yüz (single)\n" in prompt
    assert "Beklenen sayfa" not in prompt


# --- üretim ------------------------------------------------------------------------------------


def test_description_is_generated_from_examples_with_a_recorded_response(
    layout: DataLayout, settings: Settings, entry: CatalogEntry
) -> None:
    _place(layout, "pasaport.pdf", _passport_pdf())
    _place(layout, "tarama.png", make_half_filled_image_bytes("PNG"))
    before = _files(layout.root)
    provider = RecordingProvider.from_directory(RECORDING)

    generated = describe_type(entry, layout, settings, provider)

    recorded = validate_type_description((RECORDING / "0.json").read_text("utf-8"))
    assert generated.description == recorded
    assert generated.text == format_description(recorded)
    assert generated.pages == (ExamplePage("pasaport.pdf", 1), ExamplePage("tarama.png", 1))
    assert (generated.omitted, generated.skipped) == (0, ())
    (request,) = provider.description_requests
    assert request.instructions == load_type_description_instructions()
    assert request.prompt == build_description_prompt(entry, generated.pages)
    assert len(request.images) == 2
    assert provider.requests == []
    # Örnek dosyaları değişmez, veri dizinine hiçbir dosya yazılmaz (K10, K11).
    assert _files(layout.root) == before


def test_types_that_are_not_analyzed_are_not_described(
    layout: DataLayout, settings: Settings, make_record: RecordFactory
) -> None:
    entry = validate_catalog(
        [make_record(analyze=False, required_fields=[], expected_file_types=["docx"])]
    ).root[0]
    _place(layout, "a.pdf", make_pdf_bytes(1))
    provider = DescribingProvider(description_payload())

    with pytest.raises(TypeNotAnalyzedError):
        describe_type(entry, layout, settings, provider)

    assert provider.descriptions == []


def test_without_readable_examples_nothing_is_requested(
    layout: DataLayout, settings: Settings, entry: CatalogEntry
) -> None:
    _place(layout, "bozuk.pdf", b"%PDF-1.4 bozuk")
    provider = DescribingProvider(description_payload())

    with pytest.raises(NoExamplePagesError) as caught:
        describe_type(entry, layout, settings, provider)

    assert caught.value.skipped == ("'bozuk.pdf' dosyası açılamadı; bozuk olabilir.",)
    assert provider.descriptions == []


def test_without_any_example_nothing_is_requested(
    layout: DataLayout, settings: Settings, entry: CatalogEntry
) -> None:
    provider = DescribingProvider(description_payload())

    with pytest.raises(NoExamplePagesError) as caught:
        describe_type(entry, layout, settings, provider)

    assert caught.value.skipped == ()
    assert provider.descriptions == []


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (ProviderServerError("503", status_code=503), ProviderServerError),
        (description_payload(layout=""), TypeDescriptionError),
    ],
    ids=["saglayici", "sema"],
)
def test_provider_and_schema_errors_propagate(
    layout: DataLayout,
    settings: Settings,
    entry: CatalogEntry,
    response: object,
    error: type[Exception],
    no_sleep: list[float],
) -> None:
    _place(layout, "a.pdf", make_pdf_bytes(1))

    with pytest.raises(error):
        describe_type(entry, layout, settings, DescribingProvider(response))


# --- prompt_description metni ------------------------------------------------------------------


def test_text_lists_every_part_in_order() -> None:
    description = validate_type_description(
        description_payload(side_differences="Ön yüzde fotoğraf, arka yüzde MRZ")
    )

    assert format_description(description) == (
        "Pasaport kimlik sayfası, yatay; fotoğraf solda, etiketli satırlar sağda. "
        "Başlıklar: ПАСПОРТ / PASSPORT. "
        "Dil: ru, en; alfabe: Kiril, Latin. "
        "Alanlar: surname — fotoğrafın sağında, ilk satır; document_number — sağ üst köşe. "
        "MRZ: 2 satır, sayfanın altında. "
        "Ön/arka yüz: Ön yüzde fotoğraf, arka yüzde MRZ."
    )


def test_empty_parts_are_left_out_but_a_missing_mrz_is_stated() -> None:
    description = validate_type_description(
        description_payload(
            layout="A4 form.", headings=[], languages=[], scripts=[], field_locations=[], mrz=None
        )
    )

    assert format_description(description) == "A4 form. MRZ yok."


def test_scripts_alone_and_arabic_other_labels() -> None:
    description = validate_type_description(
        description_payload(languages=[], scripts=["arabic", "other"])
    )

    assert "Alfabe: Arap, diğer." in format_description(description)


def test_text_is_one_line_and_inner_punctuation_is_not_doubled() -> None:
    description = validate_type_description(
        description_payload(
            layout="Kart\nyatay!",
            field_locations=[{"field": "surname", "location": "üst satır.  "}],
            mrz={"line_count": 3, "location": "arka yüzün altında;"},
            side_differences="Arkada\n  MRZ",
        )
    )

    text = format_description(description)

    assert "\n" not in text
    assert text.startswith("Kart yatay! ")
    assert "Alanlar: surname — üst satır. " in text
    assert "MRZ: 3 satır, arka yüzün altında. " in text
    assert text.endswith("Ön/arka yüz: Arkada MRZ.")


def test_generated_text_is_a_valid_prompt_description_and_enters_the_catalog_text(
    make_record: RecordFactory,
) -> None:
    text = format_description(validate_type_description(description_payload()))

    catalog = validate_catalog([make_record(prompt_description=text)])

    assert catalog.root[0].prompt_description == text
    assert text in compile_catalog(catalog).text


def test_recorded_fixture_is_a_valid_description() -> None:
    payload = json.loads((RECORDING / "0.json").read_text("utf-8"))

    assert validate_type_description(payload).mrz is not None


# --- doğrulanmamış "AI kararı" örneği dışlanır (11.9.4) -------------------------------------------


def _record(
    session: Session,
    name: str,
    label: ExampleLabel | None,
    *,
    slug: str = SLUG,
    removed: bool = False,
) -> None:
    session.add(
        ExampleFileRecord(
            type_slug=slug,
            name=name,
            sha256=name.ljust(64, "0")[:64],
            method=ExampleMethod.AI.value if label else ExampleMethod.MECHANICAL.value,
            label=label.value if label else None,
            removed_at=utcnow() if removed else None,
        )
    )


def test_only_active_unverified_ai_decisions_are_on_the_exclusion_list(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _record(session, "ai.png", ExampleLabel.AI_DECISION)
        _record(session, "dogru.png", ExampleLabel.VERIFIED)
        _record(session, "mekanik.png", None)
        _record(session, "cikarilan.png", ExampleLabel.AI_DECISION, removed=True)
        _record(session, "baska.png", ExampleLabel.AI_DECISION, slug="other_card")
        session.commit()

        assert unverified_ai_examples(session, SLUG) == frozenset({"ai.png"})
        assert unverified_ai_examples(session, "other_card") == frozenset({"baska.png"})


def test_excluded_examples_are_not_collected_and_are_counted(
    layout: DataLayout, settings: Settings
) -> None:
    _place(layout, "a-ai.png", make_half_filled_image_bytes("PNG"))
    _place(layout, "b-dogru.pdf", make_pdf_bytes(2))

    collected = collect_example_pages(layout, settings, SLUG, exclude={"a-ai.png", "yok.png"})

    assert collected.pages == (ExamplePage("b-dogru.pdf", 1), ExamplePage("b-dogru.pdf", 2))
    assert (collected.excluded, collected.omitted, collected.skipped) == (1, 0, ())


def test_the_description_does_not_learn_from_an_unverified_ai_decision(
    layout: DataLayout, settings: Settings, entry: CatalogEntry
) -> None:
    _place(layout, "ai.png", make_half_filled_image_bytes("PNG"))
    _place(layout, "dogru.png", make_half_filled_image_bytes("PNG", (240, 120)))
    provider = DescribingProvider(description_payload())

    generated = describe_type(entry, layout, settings, provider, exclude={"ai.png"})

    assert generated.pages == (ExamplePage("dogru.png", 1),)
    assert generated.excluded == 1
    (request,) = provider.descriptions
    assert len(request.images) == 1


def test_when_every_example_is_excluded_nothing_is_requested_and_the_reason_is_given(
    layout: DataLayout, settings: Settings, entry: CatalogEntry
) -> None:
    _place(layout, "ai.png", make_half_filled_image_bytes("PNG"))
    provider = DescribingProvider(description_payload())

    with pytest.raises(NoExamplePagesError) as raised:
        describe_type(entry, layout, settings, provider, exclude={"ai.png"})

    assert raised.value.skipped == (EXCLUDED_MESSAGE.format(count=1),)
    assert provider.descriptions == []
