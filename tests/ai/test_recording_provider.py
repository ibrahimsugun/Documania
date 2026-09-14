"""03.6.1 — kayıtlı yanıtla test sağlayıcısı: testler ağ erişimi olmadan çalışır ve deterministik
sonuç verir.

`RecordingProvider` hiçbir HTTP istemcisi içe aktarmaz (bu dosyada `anthropic`/`httpx2` yoktur);
`tests/fixtures/ai/recordings/` altındaki kayıtlı JSON yanıtlarını okuyup ortak yanıt kabulünden
(`AnalysisProvider.analyze_page`) geçirir.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ai import PageAnalysis, PageAnalysisError
from app.ai.recording_provider import (
    RecordingExhaustedError,
    RecordingNotFoundError,
    RecordingProvider,
)
from tests.ai.payloads import page_request

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "recordings"


def test_from_directory_loads_recordings_in_filename_order() -> None:
    provider = RecordingProvider.from_directory(RECORDINGS / "serbian_residence_card")

    front = provider.analyze_page(page_request(page_index=0))
    back = provider.analyze_page(page_request(page_index=1))

    assert isinstance(front, PageAnalysis)
    assert front.side == "front"
    assert front.continues_previous_page is False
    assert back.side == "back"
    assert back.continues_previous_page is True
    assert provider.requests[0].page_index == 0
    assert provider.requests[1].page_index == 1


def test_returns_validated_analysis_matching_recording() -> None:
    provider = RecordingProvider.from_directory(RECORDINGS / "russian_passport")

    analysis = provider.analyze_page(page_request(page_index=0))

    recorded = json.loads((RECORDINGS / "russian_passport" / "0.json").read_text("utf-8"))
    assert analysis.document_type_slug == recorded["document_type_slug"]
    assert analysis.person.surname == recorded["person"]["surname"]
    assert analysis.person.document_number == recorded["person"]["document_number"]
    assert analysis.fields["expiry_date"].value == "2030-01-01"


def test_no_network_import_and_deterministic_result() -> None:
    # Bu testin dosyasında `anthropic`/`httpx2` içe aktarılmaz (03.6.1) — sağlayıcı yalnız diskten
    # okur. İki bağımsız sağlayıcı örneği aynı kaydı okuyunca birebir aynı sonucu verir.
    first = RecordingProvider.from_directory(RECORDINGS / "russian_passport").analyze_page(
        page_request(page_index=0)
    )
    second = RecordingProvider.from_directory(RECORDINGS / "russian_passport").analyze_page(
        page_request(page_index=0)
    )

    assert first == second


def test_exhausted_recordings_raises_after_available_pages() -> None:
    provider = RecordingProvider.from_directory(RECORDINGS / "russian_passport")
    provider.analyze_page(page_request(page_index=0))

    with pytest.raises(RecordingExhaustedError, match="1 kayıt"):
        provider.analyze_page(page_request(page_index=1))


def test_recording_for_wrong_page_index_is_rejected() -> None:
    provider = RecordingProvider.from_directory(RECORDINGS / "russian_passport")

    with pytest.raises(PageAnalysisError, match="page_index"):
        provider.analyze_page(page_request(page_index=5))


def test_malformed_recording_is_rejected_by_shared_validation(tmp_path: Path) -> None:
    (tmp_path / "0.json").write_text("{bozuk json", encoding="utf-8")
    provider = RecordingProvider.from_directory(tmp_path)

    with pytest.raises(PageAnalysisError):
        provider.analyze_page(page_request(page_index=0))


def test_from_directory_without_recordings_raises(tmp_path: Path) -> None:
    with pytest.raises(RecordingNotFoundError) as caught:
        RecordingProvider.from_directory(tmp_path)

    assert str(tmp_path) in str(caught.value)


def test_direct_construction_rejects_empty_recordings() -> None:
    with pytest.raises(RecordingNotFoundError):
        RecordingProvider([])
