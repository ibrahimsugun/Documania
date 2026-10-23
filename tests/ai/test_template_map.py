"""15.1.2 — alan haritası sözleşmesi (§8.7), sağlayıcının ortak `examine_template` adımı, kayıtlı
yanıt sağlayıcısı, talimat metni ve incelemenin çekirdeği (`app.output_templates.examine`).

Yapay zekâ canlı çağrılmaz: kayıtlı yanıt (`tests/fixtures/ai/template_maps/`). Şablon sentetiktir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.ai import (
    TemplateFieldMap,
    TemplateFieldMapError,
    TemplateMapRequest,
    validate_template_field_map,
)
from app.ai.prompts import load_template_map_instructions
from app.ai.provider import PageImage
from app.ai.recording_provider import RecordingProvider
from app.ai.schemas import TEMPLATE_FIELD_KINDS, TEMPLATE_FIELD_SOURCES
from app.output_templates.examine import (
    ExamineError,
    TemplateSource,
    build_map_prompt,
    canonical_map_json,
    examine,
    map_hash,
)
from app.storage import DataLayout, prepare_data_dir
from tests.fixtures.gen import make_half_filled_image_bytes

ROOT = Path(__file__).resolve().parents[2]
MAPS = ROOT / "tests" / "fixtures" / "ai" / "template_maps"
PRD = ROOT / "urun-gereksinim-dokumani-PRD.md"


def _field(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "field_id": "f1",
        "page": 0,
        "box": [0.31, 0.142, 0.78, 0.168],
        "kind": "text",
        "label_text": "Ime i prezime",
        "source": "full_name",
        "font_size": 10,
        "max_chars": 40,
    }
    data.update(changes)
    return data


def _map(*fields: dict[str, Any]) -> dict[str, Any]:
    return {"fields": list(fields), "notes": "One-page form."}


def _problems(data: object, page_count: int = 2) -> list[str]:
    with pytest.raises(TemplateFieldMapError) as caught:
        validate_template_field_map(data, page_count=page_count)
    return caught.value.problems


def test_the_recorded_contract_map_follows_the_prd_example() -> None:
    raw = (MAPS / "contract" / "0.json").read_text(encoding="utf-8")

    field_map = validate_template_field_map(raw, page_count=2)

    assert field_map.fillable_count == 6
    kinds = {item.field_id: item.kind for item in field_map.fields}
    assert (kinds["f7"], kinds["f8"]) == ("signature", "stamp")
    assert {item.source for item in field_map.fields if item.kind in {"signature", "stamp"}} == {
        None
    }


def test_kind_and_source_lists_match_the_prd() -> None:
    # §8.7 satırları: `kind` ve `source` sabit listedir.
    text = " ".join(PRD.read_text(encoding="utf-8").split())
    kinds = " · ".join(TEMPLATE_FIELD_KINDS)
    sources = " · ".join(TEMPLATE_FIELD_SOURCES)
    assert f"`kind`: {kinds}." in text
    assert f"`source` (yalnız `text`/`date`): {sources}." in text


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        (_field(kind="signature"), "signature alanı doldurulmaz"),
        (_field(kind="stamp", source=None, font_size=None, max_chars=None, page=0), None),
        (_field(source=None), "text alanında dolu olmalı: source"),
        (_field(source="salary"), "fields.0.source"),
        (_field(box=[0.5, 0.1, 1.2, 0.2]), "fields.0.box.2"),
        (_field(box=[0.5, 0.1, 0.4, 0.2]), "kutu x0 < x1"),
        (_field(page=2), "şablonda 2 sayfa var"),
        (_field(extra="x"), "fields.0.extra"),
    ],
    ids=[
        "imza-kaynakli",
        "kase-gecerli",
        "kaynaksiz",
        "liste-disi",
        "aralik",
        "ters",
        "sayfa",
        "ek",
    ],
)
def test_field_rules(field: dict[str, Any], expected: str | None) -> None:
    if expected is None:
        assert validate_template_field_map(_map(field), page_count=2).fillable_count == 0
        return
    assert any(expected in problem for problem in _problems(_map(field)))


def test_field_ids_are_unique_and_values_stay_out_of_messages() -> None:
    problems = _problems(_map(_field(), _field(label_text="Prezime OrnekovaSoyad")))

    assert problems == ["fields: field_id tekrarsız olmalı"]
    assert "Ornekova" not in " ".join(problems)


def test_examine_template_returns_the_recorded_map_and_sends_every_page() -> None:
    provider = RecordingProvider.from_directory(MAPS / "contract")
    images = tuple(PageImage(make_half_filled_image_bytes("JPEG", (60 + i, 80))) for i in range(2))
    request = TemplateMapRequest(
        images=images,
        instructions=load_template_map_instructions(),
        prompt="Sayfa sayısı: 2",
        page_count=2,
    )

    field_map = provider.examine_template(request)

    assert isinstance(field_map, TemplateFieldMap)
    assert provider.template_map_requests == [request]


def _layout_with_pages(tmp_path: Path, template_id: int, pages: int) -> DataLayout:
    layout = prepare_data_dir(tmp_path / "data")
    for index in range(pages):
        path = layout.template_page_image_path(template_id, index)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(make_half_filled_image_bytes("JPEG", (60 + index, 80)))
    return layout


def test_examine_returns_the_map_or_an_error_code_without_retrying(tmp_path: Path) -> None:
    layout = _layout_with_pages(tmp_path, 7, 2)
    source = TemplateSource(7, "Ugovor o radu", 2)

    good = examine(source, layout, RecordingProvider.from_directory(MAPS / "contract"))
    invalid_provider = RecordingProvider.from_directory(MAPS / "invalid")
    bad = examine(TemplateSource(7, "Ugovor o radu", 1), layout, invalid_provider)

    assert good.error is None and good.field_map is not None
    assert (bad.field_map, bad.error) == (None, ExamineError.INVALID_RESPONSE)
    assert len(invalid_provider.template_map_requests) == 1
    request = invalid_provider.template_map_requests[0]
    assert request.page_count == 1 and len(request.images) == 1


def test_examine_without_page_images_does_not_call_the_provider(tmp_path: Path) -> None:
    layout = _layout_with_pages(tmp_path, 7, 1)
    provider = RecordingProvider.from_directory(MAPS / "contract")

    result = examine(TemplateSource(7, "Ugovor", 2), layout, provider)

    assert result.error is ExamineError.NO_PAGES
    assert provider.template_map_requests == []


def test_prompt_lists_the_pages_in_order() -> None:
    prompt = build_map_prompt(TemplateSource(3, "Ugovor", 2))

    assert prompt.splitlines() == [
        "Şablon adı: Ugovor",
        "Sayfa sayısı: 2",
        "Görüntüler sayfa sırasıyladır:",
        "- 1. görüntü: sayfa 0 (`page: 0`)",
        "- 2. görüntü: sayfa 1 (`page: 1`)",
    ]


def test_map_hash_is_the_sha256_of_the_canonical_json() -> None:
    data = {"version": 1, "fields": [], "notes": "Şablon", "template_id": 3}

    assert canonical_map_json(data) == (
        '{"fields":[],"notes":"Şablon","template_id":3,"version":1}'.encode()
    )
    assert map_hash(data) == map_hash(json.loads(json.dumps(data, sort_keys=False)))
    assert len(map_hash(data)) == 64


def test_instructions_mark_non_fillable_areas_and_do_not_reproduce_text() -> None:
    text = " ".join(load_template_map_instructions().split())

    assert "Şablonun basılı metnini okuyup yeniden yazma" in text
    for kind in ("signature", "stamp", "logo", "photo", "decoration"):
        assert f"`{kind}`" in text
    assert "`notes` İngilizce yazılır" in text
    for source in TEMPLATE_FIELD_SOURCES:
        assert f"`{source}`" in text
