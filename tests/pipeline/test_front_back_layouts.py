"""04.1.2, 11.1.2 — `front_back` türün kabul ettiği düzenler, analizden plana ve çıktıya kadar.

Ön ve arka yüzlü kart iki ayrı sayfada (`separate`) da, iki yüzü tek sayfaya konmuş (`combined`,
sayfanın yüzü `front_and_back`) da gelebilir; tür hangi düzenleri kabul ettiğini bilir. Yapay zekâ
yalnız gördüğü yüzü söyler (kayıtlı yanıt), belgenin geçip geçmediğine kod karar verir: türün
seçmediği düzende gelen belge ve bir sayfada iki kişinin kartı Unresolved'a gider. Tek sayfadaki iki
yüz bölünmez, kırpılmaz; sayfa olduğu gibi çıktı olur (K11, K17). Dönüşüm yalnız türün izin
verdiğidir (K12).

Partiler gerçek adımlardan geçer (`process_upload`: render, kayıtlı yanıtla analiz, gruplama,
plan, uygulama). Belgeler `tests/fixtures/gen.py` ile üretilen sentetik sayfalardır
(CONVENTIONS §6).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog import Catalog, import_catalog, load_seed_catalog, validate_catalog
from app.config import Settings
from app.db.models import Document, Employee, QueueItem, Upload, UploadFile, UploadStatus
from app.pipeline.orchestrate import current_plan, process_upload
from app.pipeline.plan import Operation, PlanItem, Route, read_plan
from app.pipeline.validate import ValidationName
from app.storage import DataLayout, find_original_by_sha256, write_to_inbox
from tests.fixtures.gen import (
    MULTIPLE_DOCUMENTS_NOTE,
    PERSON_ORNEKOVA,
    PERSON_SIDOROV,
    SyntheticPage,
    driving_license_combined_page,
    driving_license_pages,
    make_document_pdf_bytes,
    make_page_image_bytes,
    recorded_provider,
    two_driving_licenses_page,
    work_permit_page,
)

SEED = load_seed_catalog()
SETTINGS = Settings(_env_file=None, database_url="sqlite://")
LICENSE = "serbian_driving_license"
LICENSE_NUMBER = "000123456"
EXPIRY = date(2031, 6, 30)
FOLDER = "Ivan_Sidorov_E0001"
OUTPUT = "Ivan_Sidorov-Driving-License.pdf"
SEPARATE_TEXT = "ön ve arka ayrı sayfalarda, önce ön sonra arka (separate: front, back)"
COMBINED_TEXT = "iki yüz tek sayfada (combined: front_and_back)"


def _catalog_with(**changes: Any) -> Catalog:
    """Tohum katalog; ehliyet kaydı `changes` ile değişmiş."""
    return validate_catalog(
        [
            {**entry.model_dump(mode="json"), **(changes if entry.slug == LICENSE else {})}
            for entry in SEED
        ]
    )


SEPARATE_ONLY = _catalog_with(front_back_layouts=["separate"], expected_pages={"min": 2, "max": 2})
COMBINED_ONLY = _catalog_with(front_back_layouts=["combined"], expected_pages={"min": 1, "max": 1})


def _combined() -> SyntheticPage:
    return driving_license_combined_page(
        PERSON_SIDOROV, document_number=LICENSE_NUMBER, expiry_date=EXPIRY
    )


def _separate() -> tuple[SyntheticPage, SyntheticPage]:
    return driving_license_pages(PERSON_SIDOROV, document_number=LICENSE_NUMBER, expiry_date=EXPIRY)


def _process(
    session: Session,
    layout: DataLayout,
    tmp_path: Path,
    files: list[tuple[str, bytes, list[SyntheticPage]]],
    *,
    catalog: Catalog = SEED,
) -> tuple[Upload, tuple[PlanItem, ...]]:
    """Kataloğu yükler, partiyi Inbox'a yazar ve boru hattından geçirir; plan öğelerini döner."""
    import_catalog(session, catalog)
    upload = Upload(id="u_20260921_0001", channel="web")
    session.add(upload)
    session.flush()
    for name, content, _ in files:
        stored = write_to_inbox(layout, upload.id, name, content)
        assert find_original_by_sha256(session, stored.sha256) is None
        session.add(
            UploadFile(
                upload=upload,
                original_name=name,
                stored_path=layout.relative(stored.path),
                sha256=stored.sha256,
                mime="application/octet-stream",
            )
        )
        session.flush()
    session.commit()
    provider = recorded_provider(tmp_path / "kayit", *(pages for _, _, pages in files))

    result = process_upload(session, layout, upload, settings=SETTINGS, provider=provider)

    assert result.status is UploadStatus.DONE
    plan = current_plan(session, upload)
    assert plan is not None
    return upload, read_plan(plan).items


def _item(*args: Any, **kwargs: Any) -> PlanItem:
    """Tek belgeli partinin tek plan öğesi."""
    _, (item,) = _process(*args, **kwargs)
    return item


def _failed(item: PlanItem) -> tuple[ValidationName, ...]:
    return tuple(ValidationName(check.name) for check in item.validations if not check.ok)


def _unresolved_without_output(session: Session, layout: DataLayout, item: PlanItem) -> None:
    """Belge kuyruktadır: çalışan açılmadı, çıktı yazılmadı, işlem seçilmedi."""
    assert item.route is Route.UNRESOLVED
    assert (item.operation, item.target_name) == (None, None)
    assert session.scalar(select(func.count()).select_from(Employee)) == 0
    assert session.scalar(select(func.count()).select_from(Document)) == 0
    assert not layout.employee_dir(FOLDER).exists()
    (queued,) = session.scalars(select(QueueItem))
    assert (queued.kind, queued.reason) == ("unresolved", item.route_reason)


# --- iki düzen de kabul edilir (tohum: separate + combined, 1–2 sayfa) --------------------------


def test_front_and_back_on_separate_pages_is_ready_as_one_two_page_document(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    front, back = _separate()
    content = make_document_pdf_bytes([front, back])

    item = _item(session, layout, tmp_path, [("ehliyet.pdf", content, [front, back])])

    assert (item.route, item.operation, item.target_name) == (
        Route.READY,
        Operation.PASSTHROUGH,
        OUTPUT,
    )
    assert [(source.file_id, source.pages) for source in item.sources] == [(1, (0, 1))]
    output = layout.ready_dir(FOLDER) / OUTPUT
    assert output.read_bytes() == content


def test_both_faces_on_one_pdf_page_are_ready_and_the_output_is_that_page_unchanged(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    # Tek sayfalık PDF olduğu gibi kopyalanır (passthrough): yüzler bölünmez, kırpılmaz.
    page = _combined()
    content = make_document_pdf_bytes([page])

    item = _item(session, layout, tmp_path, [("iki-yuz.pdf", content, [page])])

    assert (item.route, item.operation, item.target_name) == (
        Route.READY,
        Operation.PASSTHROUGH,
        OUTPUT,
    )
    assert all(check.ok for check in item.validations)
    assert (layout.ready_dir(FOLDER) / OUTPUT).read_bytes() == content
    (document,) = session.scalars(select(Document))
    assert document.source_refs_json == [{"file_id": 1, "pages": [0]}]


def test_both_faces_page_inside_a_longer_pdf_is_extracted_alone(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    # Aynı taramada ardından başka bir belge (çalışma izni) gelir: iki yüzlü sayfa onu almaz,
    # çıktısı yalnız kendi sayfasıdır (extract), merge yok.
    page = _combined()
    permit = work_permit_page(PERSON_SIDOROV, document_number="WP-0000042", expiry_date=EXPIRY)
    content = make_document_pdf_bytes([page, permit])

    _, items = _process(session, layout, tmp_path, [("tarama.pdf", content, [page, permit])])

    item = next(item for item in items if item.document_type_slug == LICENSE)
    assert len(items) == 2
    assert (item.route, item.operation) == (Route.READY, Operation.EXTRACT)
    assert [(source.file_id, source.pages) for source in item.sources] == [(1, (0,))]
    with pymupdf.open(layout.ready_dir(FOLDER) / OUTPUT) as output:
        assert output.page_count == 1


def test_both_faces_in_one_jpeg_are_wrapped_losslessly_as_the_type_allows(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    page = _combined()
    jpeg = make_page_image_bytes(page)

    item = _item(session, layout, tmp_path, [("iki-yuz.jpg", jpeg, [page])])

    assert (item.route, item.operation, item.target_name) == (
        Route.READY,
        Operation.WRAP_IMAGE,
        OUTPUT,
    )
    with pymupdf.open(layout.ready_dir(FOLDER) / OUTPUT) as output:
        assert output.page_count == 1
        ((xref, *_),) = output[0].get_images(full=True)
        assert output.extract_image(xref)["image"] == jpeg  # kayıpsız sarma: aynı baytlar


def test_both_faces_in_one_jpeg_are_not_converted_when_the_type_does_not_allow_it(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    # K12: dönüşüm yalnız türün izin verdiğidir; tek sayfalı kart da istisna değildir.
    page = _combined()
    catalog = _catalog_with(allowed_conversions=["merge"])

    item = _item(
        session,
        layout,
        tmp_path,
        [("iki-yuz.jpg", make_page_image_bytes(page), [page])],
        catalog=catalog,
    )

    assert item.route is Route.UNRESOLVED
    assert item.route_reason is not None and "wrap_image" in item.route_reason
    assert session.scalar(select(func.count()).select_from(Document)) == 0


# --- türün seçmediği düzen Unresolved'a gider ---------------------------------------------------


def test_one_page_card_goes_to_unresolved_when_the_type_accepts_only_separate_pages(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    page = _combined()
    content = make_document_pdf_bytes([page])

    item = _item(
        session, layout, tmp_path, [("iki-yuz.pdf", content, [page])], catalog=SEPARATE_ONLY
    )

    _unresolved_without_output(session, layout, item)
    assert _failed(item) == (ValidationName.PAGE_COUNT, ValidationName.SIDES)
    assert item.route_reason == (
        "Beklenen sayfa sayısı kontrolü (04.5.1): bu aday 1 sayfa (dosya 1, sayfa 1) taşıyor, tür "
        f"2 sayfa bekliyor. Yüz doğrulaması (06.5.1, sides): tür yalnız şu düzeni kabul ediyor: "
        f"{SEPARATE_TEXT}. Gelen düzen {COMBINED_TEXT}, tür bu düzeni kabul etmiyor; bu adayın "
        "yüzleri: dosya 1, sayfa 1: front_and_back."
    )


def test_separate_pages_go_to_unresolved_when_the_type_accepts_only_one_page(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    front, back = _separate()
    content = make_document_pdf_bytes([front, back])

    item = _item(
        session, layout, tmp_path, [("ehliyet.pdf", content, [front, back])], catalog=COMBINED_ONLY
    )

    _unresolved_without_output(session, layout, item)
    assert _failed(item) == (ValidationName.PAGE_COUNT, ValidationName.SIDES)
    assert item.route_reason is not None
    assert f"tür yalnız şu düzeni kabul ediyor: {COMBINED_TEXT}" in item.route_reason
    assert f"Gelen düzen {SEPARATE_TEXT}, tür bu düzeni kabul etmiyor" in item.route_reason


def test_lone_front_page_goes_to_unresolved_even_though_one_page_is_a_valid_count(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    # Tohumda aralık 1–2: tek sayfa sayıca geçer, ama yalnız ön yüz hiçbir düzen değildir.
    front, _ = _separate()
    content = make_document_pdf_bytes([front])

    item = _item(session, layout, tmp_path, [("on.pdf", content, [front])])

    _unresolved_without_output(session, layout, item)
    assert _failed(item) == (ValidationName.SIDES,)
    assert item.route_reason is not None
    assert "Gelen düzen hiçbir düzene uymuyor" in item.route_reason


@pytest.mark.parametrize("catalog", [SEED, SEPARATE_ONLY], ids=["iki-duzen", "yalniz-ayri"])
def test_two_people_on_one_page_go_to_unresolved_and_the_page_is_not_split(
    session: Session, layout: DataLayout, tmp_path: Path, catalog: Catalog
) -> None:
    # Analizci iki kişinin kartını `unknown` okur ve "birden fazla belge" notu düşer; hiçbir kişi
    # seçilmez, sayfa bölünmez.
    page = two_driving_licenses_page(
        PERSON_SIDOROV, PERSON_ORNEKOVA, numbers=(LICENSE_NUMBER, "000654321")
    )
    content = make_document_pdf_bytes([page])

    upload, (item,) = _process(
        session, layout, tmp_path, [("iki-kisi.pdf", content, [page])], catalog=catalog
    )

    _unresolved_without_output(session, layout, item)
    assert ValidationName.SIDES in _failed(item)
    assert item.route_reason is not None
    assert "bu adayın yüzleri: dosya 1, sayfa 1: unknown." in item.route_reason
    (stored,) = upload.files[0].pages
    assert stored.analysis_json is not None
    assert stored.analysis_json["notes"] == MULTIPLE_DOCUMENTS_NOTE
