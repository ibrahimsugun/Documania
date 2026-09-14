"""03.7.1 — sayfalar sırayla, önceki sayfa özetiyle analiz edilir; 03.7.2 — bir sayfanın analizi
başarısız olursa parti `partial` olur, diğer sayfalar tamamlanır.

Sağlayıcı ağ çağrısı yapmaz: yanıtlar `RecordingProvider` kayıtlarıdır (03.6); sayfa görüntüleri
sentetik PDF/JPEG'lerden gerçek render adımlarıyla üretilir (gerçek kişi/belge yok).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import (
    AnalysisProvider,
    PageAnalysis,
    PageAnalysisRequest,
    ProviderConnectionError,
    ProviderServerError,
    build_page_analysis_instructions,
)
from app.ai.provider import MAX_ANALYSIS_ATTEMPTS
from app.ai.recording_provider import RecordingExhaustedError, RecordingProvider
from app.catalog import load_seed_catalog
from app.config import Settings
from app.db.models import Event, Page, Upload, UploadFile, UploadStatus
from app.events import EventType
from app.pipeline.analyze import (
    TEXT_LAYER_BEGIN,
    TEXT_LAYER_END,
    PageAnalysisStatus,
    PageImageError,
    PreviousPage,
    analyze_upload,
    build_page_prompt,
    load_page_image,
    summarize_page_analysis,
)
from app.pipeline.render import (
    extract_upload_file_text,
    mark_upload_file_blank_pages,
    render_image_file,
    render_upload_file,
)
from app.storage import DataLayout, FileKind, detect_file_kind, write_to_inbox
from tests.ai.payloads import SYNTHETIC_DOCUMENT_NUMBER, SYNTHETIC_SURNAME, analysis_payload
from tests.fixtures.gen import make_half_filled_image_bytes, make_text_pdf_bytes

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "recordings"
INSTRUCTIONS = build_page_analysis_instructions(load_seed_catalog())
UPLOAD_ID = "u_20260914_0001"

# Önceki sayfa özetinde geçmemesi gereken sentetik kişisel değerler.
SYNTHETIC_DOB = "1990-01-01"
SYNTHETIC_ORIGINAL = "Орнекова Тест"
SYNTHETIC_ADDRESS = "Ornek Sokak 7"
SYNTHETIC_MRZ = "P<RUSORNEKOVA<<TEST<<<<<<<<<<<<<<<<<<<<<<<<<"
SYNTHETIC_NOTE = "ORNEK-NOT-DEGERI"
PERSONAL_VALUES = (
    SYNTHETIC_SURNAME,
    SYNTHETIC_DOCUMENT_NUMBER,
    SYNTHETIC_DOB,
    SYNTHETIC_ORIGINAL,
    SYNTHETIC_ADDRESS,
    SYNTHETIC_MRZ,
    SYNTHETIC_NOTE,
)


def _settings() -> Settings:
    return Settings(_env_file=None, database_url="sqlite://")


def _upload(
    session: Session,
    layout: DataLayout,
    files: list[tuple[str, bytes]],
    *,
    status: UploadStatus = UploadStatus.ANALYZING,
) -> Upload:
    """Partiyi Inbox'a yazar ve her dosyanın sayfalarını gerçek render adımlarıyla üretir."""
    upload = Upload(id=UPLOAD_ID, channel="web", status=status.value)
    session.add(upload)
    for name, content in files:
        stored = write_to_inbox(layout, upload.id, name, content)
        kind = detect_file_kind(content)
        upload_file = UploadFile(
            upload=upload,
            original_name=name,
            stored_path=stored.path.relative_to(layout.root).as_posix(),
            sha256=stored.sha256,
            mime="application/pdf" if kind is FileKind.PDF else "image/jpeg",
        )
        session.add(upload_file)
        session.flush()
        if kind is FileKind.PDF:
            render_upload_file(session, layout, _settings(), upload_file)
            extract_upload_file_text(session, layout, upload_file)
            mark_upload_file_blank_pages(session, layout, upload_file)
        else:
            render_image_file(session, layout, _settings(), upload_file)
    session.flush()
    return upload


def _recordings(tmp_path: Path, responses: list[dict[str, Any]]) -> RecordingProvider:
    """Yanıtları `0.json`, `1.json`, ... kayıtları olarak yazar ve sağlayıcıyı onlardan kurar."""
    directory = tmp_path / "recordings"
    directory.mkdir()
    for number, response in enumerate(responses):
        text = json.dumps(response, ensure_ascii=False)
        (directory / f"{number}.json").write_text(text, encoding="utf-8")
    return RecordingProvider.from_directory(directory)


def _payload(page_index: int, **top: Any) -> dict[str, Any]:
    return analysis_payload(page_index=page_index, **top)


class ScriptedProvider(AnalysisProvider):
    """Sırayla yanıt veya hata döner; hata örneği verilirse fırlatır."""

    name = "scripted"

    def __init__(self, script: list[object]) -> None:
        super().__init__(model="scripted-model")
        self._script = list(script)
        self.requests: list[PageAnalysisRequest] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        self.requests.append(request)
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _events(session: Session, event_type: EventType) -> list[Event]:
    return list(session.scalars(select(Event).where(Event.type == event_type).order_by(Event.id)))


def _pages(upload: Upload) -> list[Page]:
    return [page for upload_file in upload.files for page in upload_file.pages]


# --- 03.7.1 sıra ------------------------------------------------------------------------------


def test_pages_are_analyzed_in_order_across_files(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    upload = _upload(
        session,
        layout,
        [
            ("tarama.pdf", make_text_pdf_bytes(["SAYFA A", "SAYFA B", "SAYFA C"])),
            ("foto.jpg", make_half_filled_image_bytes("JPEG")),
        ],
    )
    provider = _recordings(tmp_path, [_payload(0), _payload(1), _payload(2), _payload(0)])

    result = analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    pdf, image = upload.files
    expected = [(pdf.id, 0), (pdf.id, 1), (pdf.id, 2), (image.id, 0)]
    assert [request.page_index for request in provider.requests] == [0, 1, 2, 0]
    assert [(o.file_id, o.page_index) for o in result.outcomes] == expected
    assert [o.status for o in result.outcomes] == [PageAnalysisStatus.DONE] * 4
    assert len(result.analyzed) == 4
    assert not result.failed
    assert not result.skipped
    assert not result.is_partial
    analyzed = _events(session, EventType.PAGE_ANALYZED)
    assert [(event.file_id, event.page_index) for event in analyzed] == expected
    assert all(event.upload_id == UPLOAD_ID for event in analyzed)


def test_successful_analysis_is_stored_and_logged(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    upload = _upload(session, layout, [("foto.jpg", make_half_filled_image_bytes("JPEG"))])
    provider = _recordings(tmp_path, [_payload(0)])

    result = analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    (page,) = _pages(upload)
    (outcome,) = result.outcomes
    assert page.analysis_status == PageAnalysisStatus.DONE
    assert outcome.analysis is not None
    assert outcome.error is None
    assert page.analysis_json == outcome.analysis.model_dump(mode="json")
    # Saklanan analiz katalogsuz geri okunur (C12).
    assert PageAnalysis.model_validate(page.analysis_json) == outcome.analysis
    (event,) = _events(session, EventType.PAGE_ANALYZED)
    assert event.data_json == {
        "provider": "recording",
        "model": "recording",
        "document_type_slug": "russian_passport",
        "side": "single",
        "is_readable": True,
    }
    assert upload.status == UploadStatus.ANALYZING
    assert not _events(session, EventType.PAGE_UNREADABLE)


def test_request_carries_instructions_catalog_image_and_page_index(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    upload = _upload(session, layout, [("tarama.pdf", make_text_pdf_bytes(["A", "B"]))])
    provider = _recordings(tmp_path, [_payload(0), _payload(1)])

    analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    for request, page in zip(provider.requests, _pages(upload), strict=True):
        assert request.instructions == INSTRUCTIONS.text
        assert request.known_slugs == INSTRUCTIONS.known_slugs
        assert request.page_index == page.index
        assert request.image.data == layout.resolve(page.image_path).read_bytes()
        assert request.image.media_type == "image/jpeg"
        assert request.prompt.startswith(f"Sayfa sırası (`page_index`): {page.index}")


def test_prompt_carries_text_layer_only_when_page_has_one(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    upload = _upload(
        session,
        layout,
        [
            ("tarama.pdf", make_text_pdf_bytes(["METIN KATMANI ORNEGI"])),
            ("foto.png", make_half_filled_image_bytes("PNG")),
        ],
    )
    provider = _recordings(tmp_path, [_payload(0), _payload(0)])

    analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    pdf_prompt, image_prompt = (request.prompt for request in provider.requests)
    assert f"{TEXT_LAYER_BEGIN}\nMETIN KATMANI ORNEGI\n{TEXT_LAYER_END}" in pdf_prompt
    assert "PDF metin katmanı: yok." in image_prompt
    assert TEXT_LAYER_BEGIN not in image_prompt
    assert provider.requests[1].image.media_type == "image/png"


# --- 03.7.1 önceki sayfa özeti ----------------------------------------------------------------


def test_each_page_gets_previous_page_summary_within_file(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    upload = _upload(
        session,
        layout,
        [
            ("kart.pdf", make_text_pdf_bytes(["ON YUZ", "ARKA YUZ"])),
            ("foto.jpg", make_half_filled_image_bytes("JPEG")),
        ],
    )
    recorded = RECORDINGS / "serbian_residence_card"
    front = json.loads((recorded / "0.json").read_text("utf-8"))
    back = json.loads((recorded / "1.json").read_text("utf-8"))
    provider = _recordings(tmp_path, [front, back, _payload(0)])

    result = analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    first, second, other_file = (request.prompt for request in provider.requests)
    assert "Önceki sayfa özeti: yok — bu sayfa dosyanın analize gönderilen ilk sayfası." in first
    front_analysis = result.outcomes[0].analysis
    assert front_analysis is not None
    assert (
        "Önceki sayfa özeti (aynı dosyada `page_index` 0; kişisel değer taşımaz):\n"
        + summarize_page_analysis(front_analysis)
    ) in second
    assert "`serbian_residence_card` (katalogda)" in second
    assert "- Yüz (`side`): front" in second
    # Özet dosyalar arasında taşınmaz (04.3'ün işi).
    assert "Önceki sayfa özeti: yok — bu sayfa dosyanın analize gönderilen ilk sayfası." in (
        other_file
    )
    assert "serbian_residence_card" not in other_file
    assert result.outcomes[1].analysis is not None
    assert result.outcomes[1].analysis.continues_previous_page is True


def test_previous_page_summary_carries_no_personal_values(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    upload = _upload(session, layout, [("tarama.pdf", make_text_pdf_bytes(["BIR", "IKI"]))])
    personal = _payload(0, notes=SYNTHETIC_NOTE)
    personal["person"].update(
        {
            "original_script_name": SYNTHETIC_ORIGINAL,
            "date_of_birth": SYNTHETIC_DOB,
            "mrz_lines": [SYNTHETIC_MRZ],
            "contact": {"phone": None, "email": None, "address": SYNTHETIC_ADDRESS},
        }
    )
    provider = _recordings(tmp_path, [personal, _payload(1)])

    analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    second = provider.requests[1].prompt
    assert "- Kişi adı yazılı: evet" in second
    assert "- Belge numarası yazılı: evet" in second
    assert "- MRZ: var" in second
    for value in PERSONAL_VALUES:
        assert value not in second
    for event in session.scalars(select(Event)):
        rendered = json.dumps(event.data_json, ensure_ascii=False) + (event.message or "")
        assert all(value not in rendered for value in PERSONAL_VALUES)


def test_blank_pages_are_not_sent_and_do_not_break_summary_chain(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    upload = _upload(
        session, layout, [("tarama.pdf", make_text_pdf_bytes([None, "ON", None, None, "ARKA"]))]
    )
    provider = _recordings(tmp_path, [_payload(1), _payload(4)])

    result = analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    assert [request.page_index for request in provider.requests] == [1, 4]
    statuses = [page.analysis_status for page in _pages(upload)]
    assert statuses == ["skipped", "done", "skipped", "skipped", "done"]
    assert [o.page_index for o in result.skipped] == [0, 2, 3]
    assert all(page.analysis_json is None for page in _pages(upload) if page.is_blank)
    assert not result.is_partial
    assert upload.status == UploadStatus.ANALYZING
    first, second = (request.prompt for request in provider.requests)
    assert "boş sayfalar analize gönderilmedi (`page_index`: 0)" in first
    assert "bu sayfa dosyanın analize gönderilen ilk sayfası" in first
    assert "boş sayfalar analize gönderilmedi (`page_index`: 2, 3)" in second
    assert "Önceki sayfa özeti (aynı dosyada `page_index` 1;" in second
    assert not _events(session, EventType.PAGE_ANALYSIS_FAILED)


def test_duplicate_file_is_not_analyzed(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    content = make_text_pdf_bytes(["TEKRAR"])
    upload = _upload(session, layout, [("ilk.pdf", content), ("tekrar.pdf", content)])
    original, duplicate = upload.files
    duplicate.is_duplicate_of = original.id
    session.flush()
    provider = _recordings(tmp_path, [_payload(0)])

    result = analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    assert len(provider.requests) == 1
    assert [(o.file_id, o.status) for o in result.outcomes] == [
        (original.id, PageAnalysisStatus.DONE),
        (duplicate.id, PageAnalysisStatus.SKIPPED),
    ]
    assert duplicate.pages[0].analysis_status == PageAnalysisStatus.SKIPPED
    assert not result.is_partial


def test_unreadable_page_is_logged(session: Session, layout: DataLayout, tmp_path: Path) -> None:
    upload = _upload(session, layout, [("foto.jpg", make_half_filled_image_bytes("JPEG"))])
    unreadable = _payload(
        0, is_readable=False, fields={"surname": {"value": None, "legible": False}}
    )
    provider = _recordings(tmp_path, [unreadable])

    result = analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    assert result.outcomes[0].status is PageAnalysisStatus.DONE
    (event,) = _events(session, EventType.PAGE_UNREADABLE)
    assert (event.file_id, event.page_index) == (upload.files[0].id, 0)
    assert _events(session, EventType.PAGE_ANALYZED)[0].data_json["is_readable"] is False


# --- 03.7.2 kısmi başarı ----------------------------------------------------------------------


def test_invalid_response_marks_upload_partial_and_other_pages_complete(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    upload = _upload(session, layout, [("tarama.pdf", make_text_pdf_bytes(["A", "B", "C"]))])
    broken = _payload(1)
    del broken["side"]
    provider = _recordings(tmp_path, [_payload(0), broken, _payload(2)])

    result = analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    assert upload.status == UploadStatus.PARTIAL
    assert result.is_partial
    assert [page.analysis_status for page in _pages(upload)] == ["done", "failed", "done"]
    assert _pages(upload)[1].analysis_json is None
    assert _pages(upload)[2].analysis_json is not None
    assert [o.page_index for o in result.failed] == [1]
    assert [o.page_index for o in result.analyzed] == [0, 2]
    assert result.failed[0].error is not None and "side" in result.failed[0].error
    (failed,) = _events(session, EventType.PAGE_ANALYSIS_FAILED)
    assert (failed.upload_id, failed.file_id, failed.page_index) == (
        UPLOAD_ID,
        upload.files[0].id,
        1,
    )
    assert failed.data_json == {
        "provider": "recording",
        "model": "recording",
        "error": "PageAnalysisError",
    }
    assert "side" in (failed.message or "")
    assert [event.page_index for event in _events(session, EventType.PAGE_ANALYZED)] == [0, 2]
    # Başarısız sayfanın özeti yok; daha eski sayfanın özeti yerine geçmez.
    third = provider.requests[2].prompt
    assert "`page_index` 1 olan önceki sayfanın analizi başarısız oldu" in third
    assert "- Belge türü:" not in third


def test_provider_error_after_retries_fails_only_that_page(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("app.ai.provider.time.sleep", sleeps.append)
    upload = _upload(session, layout, [("tarama.pdf", make_text_pdf_bytes(["A", "B", "C"]))])
    server_errors = [
        ProviderServerError("HTTP 500: api_error", status_code=500)
        for _ in range(MAX_ANALYSIS_ATTEMPTS)
    ]
    provider = ScriptedProvider([_payload(0), *server_errors, _payload(2)])

    result = analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    assert [request.page_index for request in provider.requests] == [0, 1, 1, 1, 2]
    assert len(sleeps) == MAX_ANALYSIS_ATTEMPTS - 1
    assert upload.status == UploadStatus.PARTIAL
    assert [o.status for o in result.outcomes] == [
        PageAnalysisStatus.DONE,
        PageAnalysisStatus.FAILED,
        PageAnalysisStatus.DONE,
    ]
    (failed,) = _events(session, EventType.PAGE_ANALYSIS_FAILED)
    assert failed.data_json == {
        "provider": "scripted",
        "model": "scripted-model",
        "error": "ProviderServerError",
        "status_code": 500,
    }
    assert failed.message == "HTTP 500: api_error"


def test_every_page_failing_still_leaves_upload_partial(
    session: Session, layout: DataLayout
) -> None:
    upload = _upload(session, layout, [("tarama.pdf", make_text_pdf_bytes(["A", "B"]))])
    provider = ScriptedProvider([ProviderConnectionError("zaman aşımı")] * 2)

    result = analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    assert upload.status == UploadStatus.PARTIAL
    assert [o.status for o in result.outcomes] == [PageAnalysisStatus.FAILED] * 2
    events = _events(session, EventType.PAGE_ANALYSIS_FAILED)
    assert [event.data_json["error"] for event in events] == ["ProviderConnectionError"] * 2
    assert all("status_code" not in event.data_json for event in events)


def test_missing_page_image_fails_that_page_without_calling_provider(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    upload = _upload(session, layout, [("tarama.pdf", make_text_pdf_bytes(["A", "B", "C"]))])
    pages = _pages(upload)
    layout.resolve(pages[0].image_path).unlink()
    pages[2].image_path = None
    provider = _recordings(tmp_path, [_payload(1)])

    result = analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    assert [request.page_index for request in provider.requests] == [1]
    assert [o.status for o in result.outcomes] == [
        PageAnalysisStatus.FAILED,
        PageAnalysisStatus.DONE,
        PageAnalysisStatus.FAILED,
    ]
    assert upload.status == UploadStatus.PARTIAL
    events = _events(session, EventType.PAGE_ANALYSIS_FAILED)
    assert [event.data_json["error"] for event in events] == ["PageImageError"] * 2
    assert events[0].message == "sayfa görüntüsü okunamadı (FileNotFoundError)"
    assert events[1].message == "sayfa görüntüsü üretilmemiş"


def test_rerun_replaces_analysis_and_clears_it_when_page_fails(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    upload = _upload(session, layout, [("foto.jpg", make_half_filled_image_bytes("JPEG"))])
    first_run = tmp_path / "ilk"
    first_run.mkdir()
    analyze_upload(
        session,
        layout,
        upload,
        provider=_recordings(first_run, [_payload(0)]),
        instructions=INSTRUCTIONS,
    )
    (page,) = _pages(upload)
    assert page.analysis_json is not None

    analyze_upload(
        session,
        layout,
        upload,
        provider=ScriptedProvider([ProviderConnectionError("zaman aşımı")]),
        instructions=INSTRUCTIONS,
    )

    assert page.analysis_status == PageAnalysisStatus.FAILED
    assert page.analysis_json is None
    assert upload.status == UploadStatus.PARTIAL


def test_unexpected_error_is_not_swallowed_as_partial(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    # Kayıt eksik: programlama/hazırlık hatası sayfa hatası sayılmaz, partinin `failed` olması
    # orkestrasyonun işidir (09.2.3).
    upload = _upload(session, layout, [("tarama.pdf", make_text_pdf_bytes(["A", "B"]))])
    provider = _recordings(tmp_path, [_payload(0)])

    with pytest.raises(RecordingExhaustedError):
        analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    assert upload.status == UploadStatus.ANALYZING
    assert not _events(session, EventType.PAGE_ANALYSIS_FAILED)


# --- birimler ---------------------------------------------------------------------------------


def test_build_page_prompt_for_first_page_without_text_layer() -> None:
    prompt = build_page_prompt(0, text_layer=None, previous=None)

    assert prompt == (
        "Sayfa sırası (`page_index`): 0\n\n"
        "Önceki sayfa özeti: yok — bu sayfa dosyanın analize gönderilen ilk sayfası.\n\n"
        "PDF metin katmanı: yok."
    )


def test_build_page_prompt_treats_whitespace_text_layer_as_missing() -> None:
    prompt = build_page_prompt(3, text_layer="  \n ", previous=PreviousPage(index=2))

    assert "PDF metin katmanı: yok." in prompt
    assert "`page_index` 2 olan önceki sayfanın analizi başarısız oldu" in prompt


def test_build_page_prompt_is_deterministic() -> None:
    previous = PreviousPage(index=0, analysis=PageAnalysis.model_validate(_payload(0)))
    kwargs: dict[str, Any] = {"text_layer": "METIN", "previous": previous}

    assert build_page_prompt(1, **kwargs) == build_page_prompt(1, **kwargs)


def test_summary_describes_catalog_type_and_field_legibility() -> None:
    analysis = PageAnalysis.model_validate(_payload(0))

    assert summarize_page_analysis(analysis) == "\n".join(
        [
            "- Belge türü: `russian_passport` (katalogda)",
            "- Yüz (`side`): single",
            "- Kendi önceki sayfasının devamı: hayır",
            "- Boş: hayır; okunabilir: evet",
            "- Dil / alfabe: ru / cyrillic",
            "- Kişi adı yazılı: evet",
            "- Belge numarası yazılı: evet",
            "- MRZ: yok",
            "- Okunaklı zorunlu alanlar: `surname`",
            "- Okunaksız veya o sayfada olmayan zorunlu alanlar: `expiry_date`",
        ]
    )


def test_summary_of_candidate_type_page_without_text() -> None:
    payload = _payload(
        0,
        document_type_slug=None,
        candidate_type_name="Bosnian   Identity Card",
        language=None,
        script=None,
        side="back",
        continues_previous_page=True,
        fields={},
    )
    payload["person"].update(
        {
            "surname": None,
            "given_names": None,
            "original_script_name": None,
            "document_number": None,
        }
    )

    summary = summarize_page_analysis(PageAnalysis.model_validate(payload))

    assert "- Belge türü: katalog dışı, aday tür adı: Bosnian Identity Card" in summary
    assert "- Yüz (`side`): back" in summary
    assert "- Kendi önceki sayfasının devamı: evet" in summary
    assert "- Dil / alfabe: yok / yok" in summary
    assert "- Kişi adı yazılı: hayır" in summary
    assert "- Belge numarası yazılı: hayır" in summary
    assert "- Okunaklı zorunlu alanlar: yok" in summary
    assert "- Okunaksız veya o sayfada olmayan zorunlu alanlar: yok" in summary


def test_summary_of_undetermined_type() -> None:
    payload = _payload(0, document_type_slug=None, is_blank=True, is_readable=False)

    summary = summarize_page_analysis(PageAnalysis.model_validate(payload))

    assert "- Belge türü: belirlenemedi" in summary
    assert "- Boş: evet; okunabilir: hayır" in summary


def test_load_page_image_rejects_non_image_cache_file(session: Session, layout: DataLayout) -> None:
    upload = _upload(session, layout, [("foto.jpg", make_half_filled_image_bytes("JPEG"))])
    (page,) = _pages(upload)
    layout.resolve(page.image_path).write_bytes(b"%PDF-1.7 not an image")

    with pytest.raises(PageImageError, match="JPEG veya PNG"):
        load_page_image(layout, page)


def test_load_page_image_rejects_path_outside_data_dir(
    session: Session, layout: DataLayout
) -> None:
    upload = _upload(session, layout, [("foto.jpg", make_half_filled_image_bytes("JPEG"))])
    (page,) = _pages(upload)
    page.image_path = "../disarida.jpg"

    with pytest.raises(PageImageError, match="kullanılamıyor"):
        load_page_image(layout, page)
