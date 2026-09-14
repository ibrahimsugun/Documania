"""Yapay zekâ sağlayıcı soyutlaması — PRD 03.2.1.

Boru hattı sayfa analizini yalnız bu modülün arayüzüyle ister: `create_provider(settings)`
`.env`'deki `AI_PROVIDER` adına göre somut sağlayıcıyı kurar, çağıran
`AnalysisProvider.analyze_page(PageAnalysisRequest)` ile §8.4'e uyan `PageAnalysis` alır.
Sağlayıcı değişince boru hattı kodu değişmez; yeni sağlayıcı `PROVIDER_FACTORIES`'e bir ad ekler.

Sorumluluk ayrımı:

- İstek sağlayıcıdan bağımsızdır: sayfa görüntüsü, sistem talimatı, sayfaya özgü metin ve
  analizde kullanılan kataloğun slug'ları. Talimat ve metnin içeriği sağlayıcının işi değildir
  (03.4 prompt, 03.7 çalıştırıcı); sağlayıcı onları yalnız kendi API biçimine yerleştirir.
- Yanıt kabulü ortaktır ve atlanamaz: `analyze_page` sağlayıcının ham yapılandırılmış çıktısını
  `validate_page_analysis`'ten geçirir, istenen sayfanın yanıtı olduğunu denetler. Somut
  sağlayıcı yalnız `_request_analysis`'i uygular.
- İki hata ailesi ayrıdır: çağrı tamamlanamadıysa `ProviderError` (yanıt yok; hız sınırı, 5xx
  ve bağlantı alt türleri 03.5'in yeniden deneme kararına girer), yanıt geldi ama şemaya
  uymuyorsa `PageAnalysisError` (yeniden sormak yerine reddedilir).
"""

from __future__ import annotations

import abc
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Literal, final

from app.ai.schemas import PageAnalysis, PageAnalysisError, validate_page_analysis
from app.config import Settings
from app.storage.filetype import FileKind, UnsupportedFileTypeError, detect_file_kind

ImageMediaType = Literal["image/jpeg", "image/png"]

_MEDIA_TYPES: dict[FileKind, ImageMediaType] = {
    FileKind.JPEG: "image/jpeg",
    FileKind.PNG: "image/png",
}


class ProviderConfigError(RuntimeError):
    """Sağlayıcı kurulamıyor: bilinmeyen `AI_PROVIDER` veya seçilen sağlayıcının ayarı eksik."""


class ProviderError(RuntimeError):
    """Sağlayıcı çağrısı yanıtla tamamlanamadı. `status_code` HTTP durumudur, yoksa `None`."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProviderRateLimitError(ProviderError):
    """Sağlayıcı hız sınırına takıldı (HTTP 429)."""


class ProviderServerError(ProviderError):
    """Sağlayıcı tarafında hata (HTTP 5xx, aşırı yük dahil)."""


class ProviderConnectionError(ProviderError):
    """Sağlayıcıya ulaşılamadı veya istek zaman aşımına uğradı; HTTP yanıtı yok."""


@dataclass(frozen=True, slots=True)
class PageImage:
    """Analize gönderilen sayfa görüntüsü; ortam türü baytların imzasından çıkarılır.

    Yalnız JPEG ve PNG kabul edilir (K2 — sayfa görüntüleri 02.1/02.3 önbelleğidir). Tür
    çağırandan alınmaz: uzantı ile içerik tutmazsa sağlayıcı isteği reddeder.
    """

    data: bytes = field(repr=False)
    media_type: ImageMediaType = field(init=False)

    def __post_init__(self) -> None:
        try:
            media_type = _MEDIA_TYPES.get(detect_file_kind(self.data))
        except UnsupportedFileTypeError:
            media_type = None
        if media_type is None:
            raise ValueError("sayfa görüntüsü JPEG veya PNG olmalı")
        object.__setattr__(self, "media_type", media_type)


@dataclass(frozen=True, slots=True, kw_only=True)
class PageAnalysisRequest:
    """Tek sayfanın analiz isteği; hiçbir alanı sağlayıcıya özgü değildir.

    - `page_index`: dosya içindeki 0 tabanlı sayfa sırası; yanıtın `page_index`'i buna eşit olmalı.
    - `instructions`: sistem talimatı (kurallar ve katalog, 03.4).
    - `prompt`: sayfaya özgü metin (sayfa sırası, metin katmanı, önceki sayfa özeti; 03.7).
    - `known_slugs`: talimattaki kataloğun slug'ları; katalog dışı `document_type_slug` reddedilir.
    """

    page_index: int
    image: PageImage
    instructions: str = field(repr=False)
    prompt: str = field(repr=False)
    known_slugs: frozenset[str]

    def __post_init__(self) -> None:
        if type(self.page_index) is not int or self.page_index < 0:
            raise ValueError("page_index 0 veya pozitif tamsayı olmalı")
        if not isinstance(self.image, PageImage):
            raise TypeError("image bir PageImage olmalı")
        if not self.instructions.strip():
            raise ValueError("instructions boş olamaz")
        if not self.prompt.strip():
            raise ValueError("prompt boş olamaz")
        if isinstance(self.known_slugs, str):
            raise TypeError("known_slugs tek bir metin değil, slug koleksiyonu olmalı")
        # Çağıran liste/demet verebilir; istek değişmez olsun diye kopyalanır.
        object.__setattr__(self, "known_slugs", frozenset(self.known_slugs))


class AnalysisProvider(abc.ABC):
    """Sayfa analizi sağlayıcısı. `name` `AI_PROVIDER` değeridir, `model` kullanılan modeldir."""

    name: ClassVar[str]

    def __init__(self, *, model: str) -> None:
        if not model:
            raise ValueError("model adı boş olamaz")
        self.model = model

    @final
    def analyze_page(self, request: PageAnalysisRequest) -> PageAnalysis:
        """Sayfayı analiz ettirir ve §8.4'e uyan yanıtı döner.

        Çağrı tamamlanamazsa `ProviderError`, yanıt şemaya veya isteğe uymazsa
        `PageAnalysisError` fırlatır. Yanıt düzeltilmez, eksik alan doldurulmaz.
        """
        raw = self._request_analysis(request)
        analysis = validate_page_analysis(raw, known_slugs=request.known_slugs)
        if analysis.page_index != request.page_index:
            # Değerler sayfa sırasıdır, kişisel veri taşımaz.
            raise PageAnalysisError(
                [
                    f"page_index: istenen sayfa {request.page_index}, "
                    f"yanıt sayfa {analysis.page_index} için"
                ]
            )
        return analysis

    @abc.abstractmethod
    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        """Sağlayıcıyı bir kez çağırır, yapılandırılmış çıktıyı doğrulamadan döner.

        Dönüş JSON metni veya çözülmüş JSON nesnesidir. Çağrı tamamlanamazsa `ProviderError`
        (uygun alt türüyle), yanıtta yapılandırılmış çıktı yoksa `PageAnalysisError` fırlatır.
        Kendi içinde yeniden deneme yapmaz (03.5).
        """


ProviderFactory = Callable[[Settings], AnalysisProvider]


def _anthropic(settings: Settings) -> AnalysisProvider:
    # SDK yalnız bu sağlayıcı seçildiğinde içe aktarılır.
    from app.ai.anthropic_provider import AnthropicProvider

    return AnthropicProvider.from_settings(settings)


PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "anthropic": _anthropic,
}


def create_provider(settings: Settings) -> AnalysisProvider:
    """`settings.ai_provider` adındaki sağlayıcıyı kurar; ad tanımsızsa `ProviderConfigError`."""
    factory = PROVIDER_FACTORIES.get(settings.ai_provider)
    if factory is None:
        known = ", ".join(sorted(PROVIDER_FACTORIES))
        raise ProviderConfigError(
            f"Bilinmeyen AI_PROVIDER '{settings.ai_provider}'. Tanımlı sağlayıcılar: {known}."
        )
    return factory(settings)
