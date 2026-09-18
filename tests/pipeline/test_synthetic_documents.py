"""09.3.1 — üretilen sentetik belgeler ve kayıtlı yanıtları gerçek boru hattından geçer.

Dosyalar ve sağlayıcının yanıtları `tests/fixtures/gen.py`'den aynı sayfa tanımlarıyla üretilir;
parti yükleme uç noktasının bıraktığı gibi kurulur ve `process_upload` ile render → analiz → plan →
uygulama adımlarından geçer (yapay zekâ canlı çağrılmaz). Üretecin sayfaları render adımının
fiziksel tespitleriyle (boş sayfa, tek gömülü görüntü) ve analiz çalıştırıcısının istek sırasıyla
tutmalıdır — kabul senaryoları (09.3.2–09.3.4) buna dayanır.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import Document, Page, UploadFile, UploadStatus
from app.pipeline.analyze import PageAnalysisStatus
from app.pipeline.orchestrate import process_upload
from app.storage import DataLayout
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_SIDOROV,
    blank_page,
    driving_license_pages,
    make_document_pdf_bytes,
    make_docx_bytes,
    make_page_image_bytes,
    passport_page,
    profile_picture_page,
    recorded_provider,
    residence_card_pages,
    work_permit_page,
)
from tests.pipeline.test_process_upload import _received_upload

SETTINGS = Settings(_env_file=None, database_url="sqlite://")


@pytest.fixture
def catalog(session: Session) -> None:
    import_catalog(session, load_seed_catalog())
    session.commit()


def _pages(session: Session, upload_file: UploadFile) -> list[Page]:
    query = select(Page).where(Page.file_id == upload_file.id).order_by(Page.index)
    return list(session.scalars(query))


@pytest.mark.usefixtures("catalog")
def test_a_generated_passport_goes_to_hazir_with_its_generated_recording(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    passport = passport_page(
        PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1)
    )
    pages = [passport, blank_page()]
    upload = _received_upload(session, layout, ("pasaport.pdf", make_document_pdf_bytes(pages)))
    provider = recorded_provider(tmp_path / "kayit", pages)

    result = process_upload(session, layout, upload, settings=SETTINGS, provider=provider)

    assert result.status is UploadStatus.DONE
    assert [request.page_index for request in provider.requests] == [0]
    (output,) = session.scalars(select(Document)).all()
    assert (output.employee_id, output.status) == ("E0001", "active")
    ready = layout.ready_dir("Test_Ornekova_E0001") / "Test_Ornekova-Passport.pdf"
    # Çıktı kaynak sayfanın kendisidir: metin katmanında görünen değerler ve MRZ olduğu gibi.
    with pymupdf.open(ready) as document:
        assert document.page_count == 1
        text = document[0].get_text()
    for line in passport.mrz_lines:
        assert line in text


@pytest.mark.usefixtures("catalog")
def test_a_generated_multi_file_batch_is_analyzed_page_by_page_in_request_order(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    license_front, license_back = driving_license_pages(
        PERSON_SIDOROV, document_number="000123456", expiry_date=date(2031, 6, 30)
    )
    residence_front, residence_back = residence_card_pages(
        PERSON_SIDOROV,
        document_number="AB1234567",
        expiry_date=date(2029, 12, 31),
        with_mrz=True,
    )
    scan = [
        license_front,
        blank_page(),
        license_back,
        profile_picture_page(),
        residence_front,
        residence_back,
    ]
    permit = work_permit_page(
        PERSON_SIDOROV, document_number="WP-0000042", expiry_date=date(2027, 3, 31)
    )
    upload = _received_upload(
        session,
        layout,
        ("tarama.pdf", make_document_pdf_bytes(scan)),
        ("izin.jpg", make_page_image_bytes(permit)),
        ("cv.docx", make_docx_bytes()),
    )
    provider = recorded_provider(tmp_path / "kayit", scan, [permit], [])

    result = process_upload(session, layout, upload, settings=SETTINGS, provider=provider)

    # Her yanıt kabul edildi (şema, katalog, sayfa sırası); boş sayfa ve Word eki analize gitmedi.
    assert result.status is UploadStatus.DONE
    assert [request.page_index for request in provider.requests] == [0, 2, 3, 4, 5, 0]
    pdf, image, word = upload.files
    scanned = _pages(session, pdf)
    assert [page.is_blank for page in scanned] == [False, True, False, False, False, False]
    assert [page.has_single_embedded_image for page in scanned] == [
        False,
        False,
        False,
        True,
        False,
        False,
    ]
    done, skipped = PageAnalysisStatus.DONE, PageAnalysisStatus.SKIPPED
    assert [page.analysis_status for page in scanned] == [done, skipped, done, done, done, done]
    assert [page.analysis_status for page in _pages(session, image)] == [done]
    assert _pages(session, word) == []
    slugs = [page.analysis_json["document_type_slug"] for page in scanned if not page.is_blank]
    assert slugs == [
        "serbian_driving_license",
        "serbian_driving_license",
        "profile_picture",
        "serbian_residence_card",
        "serbian_residence_card",
    ]
