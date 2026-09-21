"""13.1.1 — sayfa analizi olayları sağlayıcıya harcatılan token toplamını taşır.

Sağlayıcı ağ çağrısı yapmaz: sıralı yanıtlar, her yanıtla birlikte bildirilen token sayılarıyla
verilir. Ölçüm sayfa başınadır; analiz ve fotoğraf kontrolü aynı sayfanın toplamına girer, hiç
yanıt vermeyen çağrı (hız sınırı, bağlantı hatası) sayıya girmez ve alan yazılmaz.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.ai import (
    AnalysisProvider,
    PageAnalysisRequest,
    PhotoCheckRequest,
    ProviderConnectionError,
    ProviderServerError,
)
from app.ai.provider import MAX_ANALYSIS_ATTEMPTS
from app.ai.usage import report_usage
from app.config import ModelPrice
from app.db.models import Upload
from app.events import USAGE_DATA_KEY, EventType
from app.pipeline.analyze import PageAnalysisStatus
from app.storage import DataLayout
from app.web.routers.metrics import build_overview, build_upload_metrics
from tests.ai.payloads import analysis_payload
from tests.fixtures.gen import make_portrait_image_bytes, make_text_pdf_bytes, photo_check_response
from tests.pipeline.test_photo_check import _analyze, _events, _photo, _upload


class MeteredProvider(AnalysisProvider):
    """Sıralı yanıt verir. Öğe `(kullanım, yanıt)` çiftiyse yanıtla birlikte kullanımı bildirir,
    yalın yanıtsa hiçbir şey bildirmez; yanıt hata örneğiyse fırlatılır (bildirimden sonra)."""

    name = "metered"

    def __init__(self, *script: object) -> None:
        super().__init__(model="metered-model")
        self._script = list(script)

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        return self._serve()

    def _request_photo_check(self, request: PhotoCheckRequest) -> object:
        return self._serve()

    def _serve(self) -> object:
        item = self._script.pop(0)
        usage, response = item if isinstance(item, tuple) else (None, item)
        if usage is not None:
            report_usage(*usage)
        if isinstance(response, Exception):
            raise response
        return response


def _pdf(session: Session, layout: DataLayout, pages: int) -> Upload:
    text = [f"SAYFA {number}" for number in range(pages)]
    return _upload(session, layout, ("tarama.pdf", make_text_pdf_bytes(text)))


def _usage_of(session: Session, event_type: EventType) -> list[object]:
    return [event.data_json.get(USAGE_DATA_KEY) for event in _events(session, event_type)]


def test_analyzed_page_event_carries_the_tokens_of_its_call(
    session: Session, layout: DataLayout
) -> None:
    upload = _pdf(session, layout, 1)
    provider = MeteredProvider(((1200, 300), analysis_payload(page_index=0)))

    _analyze(session, layout, upload, provider)

    (event,) = _events(session, EventType.PAGE_ANALYZED)
    assert event.data_json[USAGE_DATA_KEY] == {"input_tokens": 1200, "output_tokens": 300}
    assert event.data_json["provider"] == "metered"
    assert event.data_json["model"] == "metered-model"


def test_cached_input_of_the_call_is_written_with_the_tokens(
    session: Session, layout: DataLayout
) -> None:
    upload = _pdf(session, layout, 1)
    provider = MeteredProvider(((1200, 300, 1024), analysis_payload(page_index=0)))

    _analyze(session, layout, upload, provider)

    (event,) = _events(session, EventType.PAGE_ANALYZED)
    assert event.data_json[USAGE_DATA_KEY] == {
        "input_tokens": 1200,
        "output_tokens": 300,
        "cached_input_tokens": 1024,
    }


def test_each_page_gets_its_own_total(session: Session, layout: DataLayout) -> None:
    upload = _pdf(session, layout, 3)
    provider = MeteredProvider(
        ((1000, 100), analysis_payload(page_index=0)),
        ((2000, 200), analysis_payload(page_index=1)),
        ((3000, 300), analysis_payload(page_index=2)),
    )

    _analyze(session, layout, upload, provider)

    assert _usage_of(session, EventType.PAGE_ANALYZED) == [
        {"input_tokens": 1000, "output_tokens": 100},
        {"input_tokens": 2000, "output_tokens": 200},
        {"input_tokens": 3000, "output_tokens": 300},
    ]


def test_a_provider_that_reports_nothing_leaves_the_field_out(
    session: Session, layout: DataLayout
) -> None:
    upload = _pdf(session, layout, 1)
    provider = MeteredProvider(analysis_payload(page_index=0))

    _analyze(session, layout, upload, provider)

    (event,) = _events(session, EventType.PAGE_ANALYZED)
    assert USAGE_DATA_KEY not in event.data_json


def test_rejected_response_still_counts_its_tokens(session: Session, layout: DataLayout) -> None:
    upload = _pdf(session, layout, 2)
    broken = analysis_payload(page_index=0)
    del broken["side"]
    provider = MeteredProvider(
        ((1500, 400), broken),
        ((1000, 100), analysis_payload(page_index=1)),
    )

    result = _analyze(session, layout, upload, provider)

    assert [o.status for o in result.outcomes] == [
        PageAnalysisStatus.FAILED,
        PageAnalysisStatus.DONE,
    ]
    assert _usage_of(session, EventType.PAGE_ANALYSIS_FAILED) == [
        {"input_tokens": 1500, "output_tokens": 400}
    ]
    # Başarısız sayfanın tokenları sonraki sayfanın toplamına karışmaz.
    assert _usage_of(session, EventType.PAGE_ANALYZED) == [
        {"input_tokens": 1000, "output_tokens": 100}
    ]


def test_call_without_a_response_has_no_usage(session: Session, layout: DataLayout) -> None:
    upload = _pdf(session, layout, 1)
    provider = MeteredProvider(ProviderConnectionError("zaman aşımı"))

    _analyze(session, layout, upload, provider)

    (event,) = _events(session, EventType.PAGE_ANALYSIS_FAILED)
    assert event.data_json["error"] == "ProviderConnectionError"
    assert USAGE_DATA_KEY not in event.data_json


def test_retried_calls_without_a_response_add_no_tokens(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.ai.provider.time.sleep", lambda _seconds: None)
    upload = _pdf(session, layout, 1)
    errors = [ProviderServerError("HTTP 500", status_code=500)] * (MAX_ANALYSIS_ATTEMPTS - 1)
    provider = MeteredProvider(*errors, ((1200, 300), analysis_payload(page_index=0)))

    _analyze(session, layout, upload, provider)

    # Yalnız yanıt veren deneme sayılır; başarısız denemeler token harcamaz.
    assert _usage_of(session, EventType.PAGE_ANALYZED) == [
        {"input_tokens": 1200, "output_tokens": 300}
    ]


def test_photo_check_tokens_join_the_page_total(session: Session, layout: DataLayout) -> None:
    upload = _upload(session, layout, ("foto.jpg", make_portrait_image_bytes()))
    provider = MeteredProvider(((1000, 100), _photo()), ((400, 50), photo_check_response()))

    _analyze(session, layout, upload, provider)

    assert _usage_of(session, EventType.PAGE_ANALYZED) == [
        {"input_tokens": 1400, "output_tokens": 150}
    ]


def test_failed_photo_check_keeps_the_tokens_the_page_already_spent(
    session: Session, layout: DataLayout
) -> None:
    upload = _upload(session, layout, ("foto.jpg", make_portrait_image_bytes()))
    provider = MeteredProvider(((1000, 100), _photo()), ProviderConnectionError("kesildi"))

    _analyze(session, layout, upload, provider)

    (event,) = _events(session, EventType.PAGE_ANALYSIS_FAILED)
    assert event.data_json["step"] == "photo_check"
    assert event.data_json[USAGE_DATA_KEY] == {"input_tokens": 1000, "output_tokens": 100}
    assert _events(session, EventType.PAGE_ANALYZED) == []


def test_metrics_read_back_what_the_analysis_wrote(session: Session, layout: DataLayout) -> None:
    upload = _pdf(session, layout, 3)
    provider = MeteredProvider(
        ((1000, 100), analysis_payload(page_index=0)),
        ((2000, 200), analysis_payload(page_index=1)),
        ProviderConnectionError("zaman aşımı"),
    )
    _analyze(session, layout, upload, provider)
    prices = {"metered-model": ModelPrice(input_per_mtok=Decimal(10), output_per_mtok=Decimal(50))}

    overview = build_overview(session, prices)
    detail = build_upload_metrics(session, upload, prices)

    # 3000 girdi × 10 + 300 çıktı × 50 = 45000 / 1e6; bağlantı hatası sayfası ölçülmemiş.
    assert (overview.total.analyses, overview.total.unmetered) == (3, 1)
    assert (overview.total.input_tokens, overview.total.output_tokens) == ("3.000", "300")
    assert overview.total.cost == "0.0450 USD"
    assert [row.label for row in overview.batches] == [upload.id]
    assert [(row.total_tokens, row.cost) for row in detail.pages] == [
        ("1.100", "0.0150 USD"),
        ("2.200", "0.0300 USD"),
        ("0", "—"),
    ]
    assert [row.label.rsplit(" ", 1)[-1] for row in detail.pages] == ["1", "2", "3"]
