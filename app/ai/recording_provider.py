"""Kayıtlı yanıt sağlayıcısı — PRD 03.6.1 (test altyapısı).

`AnalysisProvider`'ı ağ erişimi olmadan uygular: `_request_analysis` bir HTTP çağrısı yapmaz,
diske önceden kaydedilmiş bir yanıtı olduğu gibi okuyup döner. Böylece boru hattını çağıran
testler (03.7 sayfa analizi çalıştırıcısı ve sonrası) gerçek bir sağlayıcıya bağlanmadan, her
koşuda aynı sonuçla sınanabilir. `tests/ai/test_provider.py`'deki `CannedProvider`/
`QueuedProvider` yalnız `provider.py`'nin kendi yanıt-kabul/yeniden-deneme testleri içindir ve
yanıtı Python değişmezi olarak taşır; bu sağlayıcı `tests/fixtures/ai/recordings/` altındaki
JSON dosyalarını okuyan, başka test modüllerinin de kullanabileceği paylaşılan altyapıdır.

Bir kayıt dizini, sıradaki her `analyze_page` çağrısına karşılık gelen sayfanın ham yanıtını
taşıyan `<sıra>.json` dosyalarından oluşur (`0.json`, `1.json`, ...) ve dosya adına göre
sıralı okunur. Tür açıklaması isteği (`describe_type`, 11.3.1), tür taslağı isteği
(`propose_type`, 11.5.5), fotoğraf kontrolü isteği (`check_photo`, 11.7.1) ve belge isteği
(`read_document_query`, 12.3.1) aynı sıradan bir kayıt alır: kayıtlar istek türüne bakılmadan
geldiği sırayla dağıtılır — fotoğraf türündeki sayfanın kontrol kaydı o sayfanın analiz kaydının
hemen ardından gelir. İçerik ayrıştırılmadan olduğu gibi döner — doğrulama
`AnalysisProvider.analyze_page` içindeki `validate_page_analysis`'in (tür açıklamasında
`validate_type_description`'ın, tür taslağında `validate_type_proposal`'ın, fotoğraf kontrolünde
`validate_photo_check`'in, belge isteğinde `validate_document_query`'nin) işidir (bozuk kayıt
orada `PageAnalysisError` olur, burada değil — somut sağlayıcılarla aynı sorumluluk ayrımı, bkz.
`provider.py`). Tür açıklaması ve tür taslağı kayıtları sayfa analizi kayıtlarından ayrı
dizinlerdedir (`tests/fixtures/ai/type_descriptions/`, `tests/fixtures/ai/type_proposals/`).

`AI_PROVIDER` kayıt defterine (`PROVIDER_FACTORIES`) eklenmez: bu sağlayıcının kurulması bir
dizin yolu ister, `.env`'den okunacak bir ayar değil, testin kendisidir. Testler
`RecordingProvider.from_directory(...)`'yi doğrudan çağırır ve gerekiyorsa
`monkeypatch.setitem(PROVIDER_FACTORIES, ...)` ile enjekte eder (bkz. `test_provider.py`daki
`kayitli` örneği).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.ai.provider import (
    AnalysisProvider,
    DocumentQueryRequest,
    PageAnalysisRequest,
    PhotoCheckRequest,
    TypeDescriptionRequest,
    TypeProposalRequest,
)


class RecordingNotFoundError(RuntimeError):
    """Verilen dizinde hiç kayıt (`*.json`) yok."""


class RecordingExhaustedError(RuntimeError):
    """İstek sayısı yüklenen kayıt sayısını aştı — kayıt dizini eksik hazırlanmış."""


class RecordingProvider(AnalysisProvider):
    """Kayıtlı JSON yanıtlarını sırayla döner; hiçbir ağ çağrısı yapmaz."""

    name = "recording"

    def __init__(self, recordings: Sequence[Path], *, model: str = "recording") -> None:
        super().__init__(model=model)
        if not recordings:
            raise RecordingNotFoundError("recordings boş olamaz")
        self._recordings = list(recordings)
        self._served = 0
        self.requests: list[PageAnalysisRequest] = []
        self.description_requests: list[TypeDescriptionRequest] = []
        self.proposal_requests: list[TypeProposalRequest] = []
        self.photo_check_requests: list[PhotoCheckRequest] = []
        self.query_requests: list[DocumentQueryRequest] = []

    @classmethod
    def from_directory(cls, directory: Path, *, model: str = "recording") -> RecordingProvider:
        """`directory` altındaki `*.json` dosyalarını ada göre sıralı yükler (`0.json`, `1.json`).

        Kayıt yoksa `RecordingNotFoundError` — sessizce boş sağlayıcı kurulmaz.
        """
        recordings = sorted(directory.glob("*.json"))
        if not recordings:
            raise RecordingNotFoundError(f"'{directory}' altında kayıt (*.json) yok")
        return cls(recordings, model=model)

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        self.requests.append(request)
        return self._next_recording()

    def _request_description(self, request: TypeDescriptionRequest) -> object:
        self.description_requests.append(request)
        return self._next_recording()

    def _request_type_proposal(self, request: TypeProposalRequest) -> object:
        self.proposal_requests.append(request)
        return self._next_recording()

    def _request_photo_check(self, request: PhotoCheckRequest) -> object:
        self.photo_check_requests.append(request)
        return self._next_recording()

    def _request_document_query(self, request: DocumentQueryRequest) -> object:
        self.query_requests.append(request)
        return self._next_recording()

    def _next_recording(self) -> str:
        index = self._served
        self._served += 1
        if index >= len(self._recordings):
            raise RecordingExhaustedError(
                f"{len(self._recordings)} kayıt yüklendi, {index + 1}. istek için kayıt yok"
            )
        return self._recordings[index].read_text(encoding="utf-8")
