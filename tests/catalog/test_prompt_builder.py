"""11.4.1 — aktif türler kompakt katalog metnine derlenir; 11.4.2 — katalog metni sınırı aşarsa
açıklamalar kısaltılır ve uyarı loglanır.

Derleyici `app/catalog/prompt_builder.py`'dir; metin analiz talimatının `{{catalog}}` yuvasına
girer (`build_page_analysis_instructions`) ve her analizde katalogdan baştan derlenir.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.ai import build_page_analysis_instructions
from app.ai.prompts import load_page_analysis_template
from app.ai.recording_provider import RecordingProvider
from app.catalog import (
    CATALOG_TOKEN_BUDGET,
    Catalog,
    CompiledCatalog,
    compile_catalog,
    estimate_tokens,
    export_catalog,
    import_catalog,
    load_seed_catalog,
    validate_catalog,
)
from app.catalog.prompt_builder import NO_TYPES_TEXT
from app.config import Settings
from app.db.models import Upload, UploadFile, UploadStatus
from app.pipeline.orchestrate import process_upload
from app.storage import DataLayout, prepare_data_dir, write_to_inbox
from tests.catalog.conftest import RecordFactory
from tests.fixtures.gen import make_text_pdf_bytes

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "recordings"
SETTINGS = Settings(_env_file=None, database_url="sqlite://")
SEED = load_seed_catalog()
LOGGER = "app.catalog.prompt_builder"

WORDS = (
    "kartın üst kenarında ülke adı ve arması, sol yanda vesikalık fotoğraf, sağ yanda numaralı "
    "alanlar ve altta makine okunur bölge bulunur"
)


def catalog(*records: dict[str, Any]) -> Catalog:
    return validate_catalog(list(records))


def blocks(text: str) -> dict[str, str]:
    """Derlenen metnin tür blokları, slug'a göre."""
    found = re.findall(r"^### `([a-z0-9_]+)` — .*?(?=\n\n### |\Z)", text, re.MULTILINE | re.DOTALL)
    parts = text.split("\n\n")
    assert len(found) == len(parts)
    return dict(zip(found, parts, strict=True))


def descriptions(text: str) -> dict[str, str]:
    """Tür başına `- Tanım:` satırının metni; tanımı olmayan tür yer almaz."""
    result: dict[str, str] = {}
    for slug, block in blocks(text).items():
        for line in block.splitlines():
            if line.startswith("- Tanım: "):
                result[slug] = line.removeprefix("- Tanım: ")
    return result


def without_descriptions(text: str) -> list[str]:
    return [line for line in text.splitlines() if not line.startswith("- Tanım: ")]


def long_catalog(make_record: RecordFactory, count: int = 6) -> Catalog:
    return catalog(
        *(
            make_record(
                slug=f"type_{index:02d}",
                name=f"Type {index:02d}",
                prompt_description=" ".join([WORDS] * (index + 1)),
                acceptance_criteria=[f"Madde {index} kelimesi kelimesine korunur, kısaltılmaz"],
            )
            for index in range(count)
        )
    )


# --- 11.4.1: kompakt katalog metni ------------------------------------------------------------


def test_seed_compiles_every_active_analyzed_type_within_the_default_budget(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER)

    compiled = compile_catalog(SEED)

    expected = sorted(entry.slug for entry in SEED if entry.active and entry.analyze)
    assert isinstance(compiled, CompiledCatalog)
    assert list(blocks(compiled.text)) == expected
    assert compiled.known_slugs == set(expected)
    assert "attachment" not in compiled.known_slugs  # Word/Excel analize gitmez (K2)
    assert compiled.estimated_tokens == estimate_tokens(compiled.text)
    assert compiled.estimated_tokens <= compiled.token_budget == CATALOG_TOKEN_BUDGET
    assert compiled.shortened_slugs == ()
    assert not compiled.over_budget
    assert caplog.records == []


def test_entry_compiles_to_a_heading_and_short_lines(make_record: RecordFactory) -> None:
    source = catalog(
        make_record(
            sides="front_back",
            front_back_layouts=["separate"],
            expected_pages={"min": 2, "max": 2},
            prompt_description="Ön yüzde\n  fotoğraf, arka yüzde MRZ.",
            acceptance_criteria=["Kenarlar kesilmemiş olmalı", "MRZ\nokunabilir olmalı"],
        )
    )

    assert compile_catalog(source).text == (
        "### `sample_card` — Sample Card\n"
        "- Ülke: RS · Yüz yapısı: `front_back` · Kabul edilen düzenler: ön ve arka ayrı "
        "sayfalarda (`separate`) · Beklenen sayfa: 2\n"
        "- Zorunlu alanlar: `surname`, `document_number`\n"
        "- Tanım: Ön yüzde fotoğraf, arka yüzde MRZ.\n"
        "- Kabul kriterleri:\n"
        "  - Kenarlar kesilmemiş olmalı\n"
        "  - MRZ okunabilir olmalı"
    )


def test_missing_parts_are_left_out_instead_of_written_as_placeholders(
    make_record: RecordFactory,
) -> None:
    source = catalog(
        make_record(slug="photo", country=None, expected_pages=None, required_fields=[]),
        make_record(slug="letter", expected_pages={"min": 1, "max": 3}, description="Mektup."),
    )

    compiled = blocks(compile_catalog(source).text)

    # Tanımı, kabul kriteri, ülkesi ve sayfa aralığı olmayan tür üç satırdır.
    assert compiled["photo"] == (
        "### `photo` — Sample Card\n- Yüz yapısı: `single`\n- Zorunlu alanlar: yok"
    )
    # `prompt_description` yoksa `description` tanım olur.
    assert compiled["letter"].splitlines()[1:] == [
        "- Ülke: RS · Yüz yapısı: `single` · Beklenen sayfa: 1–3",
        "- Zorunlu alanlar: `surname`, `document_number`",
        "- Tanım: Mektup.",
    ]


def test_side_values_are_explained_once_in_the_template_not_per_type() -> None:
    text = compile_catalog(SEED).text
    template = " ".join(load_page_analysis_template().split())

    assert "`front_back`" in text and "`single`" in text
    assert "`front` veya `back`" not in text and "değeri `single`" not in text
    assert "Katalogda yüz yapısı `front_back` olan türde" in template
    assert "`front_and_back`" in template and "`front_and_back`" not in text
    assert "Türün zorunlu alanı yoksa" in template


def test_front_back_type_lists_every_accepted_layout_and_single_sided_type_none(
    make_record: RecordFactory,
) -> None:
    # 04.1.2: analizci türün kabul ettiği düzenleri görür; yüzü yine yalnız gördüğüne göre seçer.
    source = catalog(
        make_record(
            slug="two_layouts",
            sides="front_back",
            front_back_layouts=["separate", "combined"],
            expected_pages={"min": 1, "max": 2},
        ),
        make_record(
            slug="one_page",
            sides="front_back",
            front_back_layouts=["combined"],
            expected_pages={"min": 1, "max": 1},
        ),
        make_record(slug="plain"),
    )

    compiled = blocks(compile_catalog(source).text)

    assert compiled["two_layouts"].splitlines()[1] == (
        "- Ülke: RS · Yüz yapısı: `front_back` · Kabul edilen düzenler: ön ve arka ayrı "
        "sayfalarda (`separate`), iki yüz tek sayfada (`combined`) · Beklenen sayfa: 1–2"
    )
    assert compiled["one_page"].splitlines()[1] == (
        "- Ülke: RS · Yüz yapısı: `front_back` · Kabul edilen düzenler: iki yüz tek sayfada "
        "(`combined`) · Beklenen sayfa: 1"
    )
    assert "Kabul edilen düzenler" not in compiled["plain"]


def test_decision_engine_fields_stay_out_of_the_text(make_record: RecordFactory) -> None:
    # Direkt Belge, dönüşüm, çıktı biçimi, dosya etiketi ve fotoğraf kuralları karar motorunundur;
    # analizci onları kullanmaz, metne girmez.
    source = catalog(
        make_record(
            file_label="Etiketxyz",
            expected_file_types=["pdf", "png"],
            allowed_conversions=["merge", "wrap_image"],
            output_format="pdf",
            photo_rules={"kural": "fotokuralxyz"},
        )
    )

    text = compile_catalog(source).text

    for absent in ("Etiketxyz", "pdf", "png", "merge", "wrap_image", "fotokuralxyz", "direct"):
        assert absent not in text


def test_only_active_analyzed_types_are_compiled_in_slug_order(
    make_record: RecordFactory,
) -> None:
    records = [
        make_record(slug="zeta_card"),
        make_record(slug="retired_card", active=False),
        make_record(
            slug="office_file",
            expected_file_types=["docx"],
            analyze=False,
            direct=True,
            required_fields=[],
            allowed_conversions=[],
            output_format="keep",
        ),
        make_record(slug="alpha_card"),
    ]

    forward = compile_catalog(catalog(*records))
    backward = compile_catalog(catalog(*reversed(records)))

    assert forward == backward
    assert forward.text == backward.text
    assert list(blocks(forward.text)) == ["alpha_card", "zeta_card"]
    assert forward.known_slugs == {"alpha_card", "zeta_card"}


def test_catalog_without_analyzable_types_compiles_to_a_notice(
    make_record: RecordFactory,
) -> None:
    compiled = compile_catalog(catalog(make_record(active=False)))

    assert compiled.text == NO_TYPES_TEXT
    assert compiled.known_slugs == frozenset()
    assert compiled.shortened_slugs == ()


def test_instructions_carry_the_compiled_catalog_in_the_slot() -> None:
    compiled = compile_catalog(SEED)

    instructions = build_page_analysis_instructions(SEED)

    assert instructions.text == load_page_analysis_template().replace("{{catalog}}", compiled.text)
    assert instructions.known_slugs == compiled.known_slugs


# --- 11.4.2: token bütçesi ------------------------------------------------------------------------


def test_estimate_counts_utf8_bytes_conservatively() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abc") == 1
    assert estimate_tokens("abcd") == 2
    # Latin olmayan harf 2 bayttır: Kiril metin Latin metinden daha çok token sayılır.
    assert estimate_tokens("Жд") == 2
    assert estimate_tokens("ş") == 1


@pytest.mark.parametrize("budget", [0, -1])
def test_budget_must_be_positive(budget: int) -> None:
    with pytest.raises(ValueError, match="pozitif"):
        compile_catalog(SEED, token_budget=budget)


def test_text_exactly_at_the_budget_is_not_shortened(
    make_record: RecordFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER)
    source = long_catalog(make_record)
    full = compile_catalog(source, token_budget=10**6)

    exact = compile_catalog(source, token_budget=full.estimated_tokens)

    assert exact.text == full.text
    assert exact.shortened_slugs == ()
    assert caplog.records == []


def test_over_budget_shortens_descriptions_to_fit_and_logs_a_warning(
    make_record: RecordFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER)
    source = long_catalog(make_record)
    full = compile_catalog(source, token_budget=10**6)
    budget = full.estimated_tokens * 2 // 3

    compiled = compile_catalog(source, token_budget=budget)

    assert compiled.estimated_tokens == estimate_tokens(compiled.text) <= budget
    assert not compiled.over_budget
    assert compiled.shortened_slugs
    original = descriptions(full.text)
    for slug, text in descriptions(compiled.text).items():
        if slug in compiled.shortened_slugs:
            # Kelime sınırında kesilir ve kısaltıldığı belli olur.
            assert text.endswith("…")
            assert (original[slug] + " ").startswith(text.removesuffix("…") + " ")
        else:
            assert text == original[slug]
    (record,) = caplog.records
    assert record.levelno == logging.WARNING
    message = record.getMessage()
    assert f"tahmini {full.estimated_tokens} > {budget}" in message
    assert f"{len(compiled.shortened_slugs)} türün tanımı kısaltıldı" in message
    assert ", ".join(compiled.shortened_slugs) in message
    assert f"derlenen metin tahmini {compiled.estimated_tokens} token" in message


def test_nothing_but_descriptions_is_shortened_and_no_type_is_dropped(
    make_record: RecordFactory,
) -> None:
    source = long_catalog(make_record)
    full = compile_catalog(source, token_budget=10**6)

    compiled = compile_catalog(source, token_budget=full.estimated_tokens // 2)

    # Başlık, ülke/yüz/sayfa, zorunlu alanlar ve kabul kriterleri kelimesi kelimesine aynıdır
    # (04.4.2: karşılanmayan madde katalogdaki metniyle yazılır).
    assert without_descriptions(compiled.text) == without_descriptions(full.text)
    assert compiled.known_slugs == full.known_slugs
    for entry in source:
        for criterion in entry.acceptance_criteria:
            assert f"  - {criterion}\n" in compiled.text + "\n"


def test_longest_descriptions_are_shortened_first(make_record: RecordFactory) -> None:
    short = "Kısa tanım."
    source = catalog(
        make_record(slug="short_type", prompt_description=short),
        make_record(slug="long_type", prompt_description=" ".join([WORDS] * 6)),
    )
    full = compile_catalog(source, token_budget=10**6)

    compiled = compile_catalog(source, token_budget=full.estimated_tokens - 1)

    assert compiled.shortened_slugs == ("long_type",)
    assert descriptions(compiled.text)["short_type"] == short
    # Bütçeye sığan en uzun tanım seçilir: bir tokenlik aşım için yalnız son kelimeler gider.
    kept = descriptions(compiled.text)["long_type"]
    assert len(descriptions(full.text)["long_type"]) - len(kept) < 30


def test_descriptions_that_cannot_keep_a_word_are_dropped(make_record: RecordFactory) -> None:
    source = long_catalog(make_record)
    bare = compile_catalog(
        catalog(*(entry.model_dump(exclude={"prompt_description"}) for entry in source)),
        token_budget=10**6,
    )

    compiled = compile_catalog(source, token_budget=bare.estimated_tokens)

    assert compiled.text == bare.text
    assert "- Tanım:" not in compiled.text
    assert compiled.shortened_slugs == tuple(sorted(entry.slug for entry in source))
    assert not compiled.over_budget


def test_types_stay_even_when_the_catalog_cannot_fit_and_the_warning_says_so(
    make_record: RecordFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER)
    source = long_catalog(make_record)
    full = compile_catalog(source, token_budget=10**6)

    compiled = compile_catalog(source, token_budget=10)

    assert compiled.over_budget
    assert compiled.estimated_tokens > 10
    assert "- Tanım:" not in compiled.text
    assert without_descriptions(compiled.text) == without_descriptions(full.text)
    (record,) = caplog.records
    assert "bütçeye sığmıyor" in record.getMessage()
    assert f"tahmini {compiled.estimated_tokens} token" in record.getMessage()


def test_catalog_without_descriptions_over_budget_is_logged(
    make_record: RecordFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER)
    source = catalog(*(make_record(slug=f"card_{index}") for index in range(5)))

    compiled = compile_catalog(source, token_budget=10)

    assert compiled.over_budget
    assert compiled.shortened_slugs == ()
    assert compiled.text == compile_catalog(source, token_budget=10**6).text
    (record,) = caplog.records
    assert "0 türün tanımı kısaltıldı (yok)" in record.getMessage()


def test_instructions_use_the_given_budget(
    make_record: RecordFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER)
    source = long_catalog(make_record)
    budget = compile_catalog(source, token_budget=10**6).estimated_tokens // 2

    instructions = build_page_analysis_instructions(source, token_budget=budget)

    assert compile_catalog(source, token_budget=budget).text in instructions.text
    assert "…" in instructions.text
    assert len(caplog.records) == 2  # biri talimat, biri karşılaştırma için derlendi


# --- Entegrasyon: analiz talimatı her partide bütçeli katalogla kurulur ---------------------------


def _passport_batch(session: Session, layout: DataLayout) -> Upload:
    upload = Upload(id="u_20260919_0001", channel="web")
    session.add(upload)
    session.flush()
    content = make_text_pdf_bytes(["PASAPORT"])
    stored = write_to_inbox(layout, upload.id, "pasaport.pdf", content)
    session.add(
        UploadFile(
            upload=upload,
            original_name="pasaport.pdf",
            stored_path=layout.relative(stored.path),
            sha256=stored.sha256,
            mime="application/pdf",
        )
    )
    session.commit()
    return upload


def test_a_large_catalog_reaches_the_analysis_shortened_within_the_default_budget(
    session_factory: sessionmaker[Session],
    make_record: RecordFactory,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER)
    layout = prepare_data_dir(tmp_path / "data")
    fillers = long_catalog(make_record, count=12)
    with session_factory() as session:
        import_catalog(session, validate_catalog([*SEED, *fillers]))
        session.commit()
        stored = export_catalog(session)
    full = compile_catalog(stored, token_budget=10**6)
    assert full.estimated_tokens > CATALOG_TOKEN_BUDGET
    caplog.clear()

    with session_factory() as session:
        provider = RecordingProvider.from_directory(RECORDINGS / "russian_passport")
        result = process_upload(
            session, layout, _passport_batch(session, layout), settings=SETTINGS, provider=provider
        )

    (request,) = provider.requests
    compiled = compile_catalog(stored)
    assert compiled.text in request.instructions
    assert estimate_tokens(compiled.text) <= CATALOG_TOKEN_BUDGET
    assert request.known_slugs == full.known_slugs  # hiçbir tür düşmedi
    assert result.status is UploadStatus.DONE
    warnings = [r for r in caplog.records if r.name == LOGGER]
    assert len(warnings) == 2  # analiz + yukarıdaki karşılaştırma derlemesi
    assert all(r.levelno == logging.WARNING for r in warnings)
