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
- İki hata ailesi ayrıdır: çağrı tamamlanamadıysa `ProviderError` (yanıt yok; hız sınırı ve
  5xx `analyze_page` içinde geri çekilmeli yeniden denenir — 03.5.1), yanıt geldi ama şemaya
  uymuyorsa `PageAnalysisError` (yeniden sormak yerine reddedilir).
- Yeniden deneme yalnız `ProviderRateLimitError` (429) ve `ProviderServerError` (5xx) içindir.
  `ProviderConnectionError` ve diğer `ProviderError` alt türleri kalıcı kabul edilir ve ilk
  denemede yükselir — tekrar denense de aynı sonucu verme ihtimalleri yeniden deneme maliyetini
  haklı çıkarmaz.

**Tür açıklaması (11.3.1).** Aynı sağlayıcı ikinci bir iş yapar: `describe_type
(TypeDescriptionRequest)` bir belge türünün örnek sayfalarından (birkaç görüntü tek istekte)
yapılandırılmış `TypeDescription` üretir. Sözleşme sayfa analizininkiyle aynıdır — yanıt kabulü
(`validate_type_description`) ve yeniden deneme ortak, somut sağlayıcı yalnız
`_request_description`'ı uygular; şemaya uymayan yanıt `TypeDescriptionError`'dır. Bu işi
uygulamayan sağlayıcı (test sağlayıcıları) `ProviderError` verir.

**Fotoğraf kontrolü (11.7.1).** Üçüncü iş: `check_photo(PhotoCheckRequest)` fotoğraf türündeki bir
sayfanın görüntüsünü katalogda açık olan kurallara göre değerlendirtir, her kural için
`pass`/`fail`/`unsure` alır (`PhotoCheck`). Yanıt kabulü (`validate_photo_check`: sorulan her kural
bir kez, başkası yok) ve yeniden deneme ortaktır; somut sağlayıcı `_request_photo_check`'i uygular,
şemaya uymayan yanıt `PhotoCheckError`'dır. Uygulamayan sağlayıcı `ProviderError` verir.

**Belge isteği (12.3.1).** Dördüncü iş görüntüsüzdür: `read_document_query(DocumentQueryRequest)`
İK'nın Telegram'a yazdığı metni katalogla birlikte verir ve karşılığı olan araç çağrısını
(`DocumentQuery`: kimin, hangi tür belgesi) alır. Yanıt kabulü (`validate_document_query`: katalog
dışı slug yok) ve yeniden deneme ortaktır; somut sağlayıcı `_request_document_query`'yi uygular,
şemaya uymayan yanıt `DocumentQueryError`'dır. Uygulamayan sağlayıcı `ProviderError` verir.

**Tür taslağı (11.5.5).** Beşinci iş: `propose_type(TypeProposalRequest)` katalog dışı bir aday
türün örnek sayfalarından (birkaç görüntü tek istekte) tam katalog kaydı taslağı (`TypeProposal`:
ad, etiket, ülke, yapı, zorunlu alanlar, kabul kriterleri, görünüş) ürettirir. Yanıt kabulü
(`validate_type_proposal`) ve yeniden deneme ortaktır; somut sağlayıcı `_request_type_proposal`'ı
uygular, şemaya uymayan yanıt `TypeProposalError`'dır. Uygulamayan sağlayıcı `ProviderError` verir.

**Eğitim sınıflandırması (11.9.3).** Altıncı iş: `classify_training_page
(TrainingClassificationRequest)` eğitim modunda mekanik tanınmayan belgenin ilk sayfasından (PDF'te
ilk iki sayfasından) belgenin türünü ister (`TrainingClassification`: katalog türü, ülke, tür
sözlüğündeki tür, önerilen ad, yüz; kişisel alan yok). Yanıt kabulü
(`validate_training_classification`: istemdeki katalog ve tür sözlüğü dışında değer yok) ve yeniden
deneme ortaktır; somut sağlayıcı `_request_training_classification`'ı uygular, şemaya uymayan yanıt
`TrainingClassificationError`'dır. Uygulamayan sağlayıcı `ProviderError` verir.

**Ön eleme modeli (13.2.1).** Sağlayıcı ana modelinin yanında aynı API'nin ucuz bir modelini
taşıyabilir (`<SAĞLAYICI>_PRESCREEN_MODEL`): `prescreen_provider()` o modelle çalışan kopyayı verir.
Kopyanın sözleşmesi aynıdır (yanıt kabulü, yeniden deneme); somut sağlayıcı yalnız `_with_model`'i
uygular.
"""

from __future__ import annotations

import abc
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Literal, final

from app.ai.document_query import DocumentQuery, validate_document_query
from app.ai.photo_check import PhotoCheck, validate_photo_check
from app.ai.profile_answer import ProfileAnswer, validate_profile_answer
from app.ai.schemas import PageAnalysis, PageAnalysisError, validate_page_analysis
from app.ai.training_classification import (
    TrainingClassification,
    validate_training_classification,
)
from app.ai.type_description import TypeDescription, validate_type_description
from app.ai.type_proposal import TypeProposal, validate_type_proposal
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


MAX_ANALYSIS_ATTEMPTS = 3
"""Hız sınırı (429) ve sağlayıcı hatası (5xx) için toplam deneme sayısı (03.5.1)."""

RETRY_BACKOFF_SECONDS = 1.0
"""İlk yeniden denemeden önceki bekleme; her sonraki denemede ikiye katlanır."""

_RETRYABLE_ERRORS: tuple[type[ProviderError], ...] = (ProviderRateLimitError, ProviderServerError)


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


@dataclass(frozen=True, slots=True, kw_only=True)
class TypeDescriptionRequest:
    """Tür açıklaması isteği (11.3.1); hiçbir alanı sağlayıcıya özgü değildir.

    - `images`: türün örnek sayfaları, istemde anlatılan sırayla (en az bir).
    - `instructions`: sistem talimatı (`app.ai.prompts.type_description`).
    - `prompt`: türe özgü metin (ad, ülke, yüz yapısı, zorunlu alanlar, görüntülerin sırası).
    """

    images: tuple[PageImage, ...]
    instructions: str = field(repr=False)
    prompt: str = field(repr=False)

    def __post_init__(self) -> None:
        # Çağıran liste verebilir; istek değişmez olsun diye demete çevrilir.
        images = tuple(self.images)
        if not images:
            raise ValueError("images en az bir görüntü içermeli")
        if not all(isinstance(image, PageImage) for image in images):
            raise TypeError("images yalnız PageImage içermeli")
        if not self.instructions.strip():
            raise ValueError("instructions boş olamaz")
        if not self.prompt.strip():
            raise ValueError("prompt boş olamaz")
        object.__setattr__(self, "images", images)


@dataclass(frozen=True, slots=True, kw_only=True)
class TypeProposalRequest:
    """Tür taslağı isteği (11.5.5); hiçbir alanı sağlayıcıya özgü değildir.

    - `images`: aday türün örnek sayfaları (arka yüzler dahil), istemde anlatılan sırayla (en az
      bir).
    - `instructions`: sistem talimatı (`app.ai.prompts.type_proposal`).
    - `prompt`: adaya özgü metin (aday adı, gözlenen kanıt, katalog türleri, görüntülerin sırası).
    """

    images: tuple[PageImage, ...]
    instructions: str = field(repr=False)
    prompt: str = field(repr=False)

    def __post_init__(self) -> None:
        # Çağıran liste verebilir; istek değişmez olsun diye demete çevrilir.
        images = tuple(self.images)
        if not images:
            raise ValueError("images en az bir görüntü içermeli")
        if not all(isinstance(image, PageImage) for image in images):
            raise TypeError("images yalnız PageImage içermeli")
        if not self.instructions.strip():
            raise ValueError("instructions boş olamaz")
        if not self.prompt.strip():
            raise ValueError("prompt boş olamaz")
        object.__setattr__(self, "images", images)


@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingClassificationRequest:
    """Eğitim sınıflandırması isteği (11.9.3); hiçbir alanı sağlayıcıya özgü değildir.

    - `images`: belgenin ilk sayfası (PDF'te ilk iki sayfası), istemde anlatılan sırayla (en az
      bir).
    - `instructions`: sistem talimatı; katalog metni ve tür sözlüğü içindedir
      (`app.ai.prompts.training_classification`).
    - `prompt`: öğeye özgü metin (dosya türü, sayfa sayısı, görüntülerin sırası).
    - `known_slugs`: talimattaki katalog türlerinin slug'ları; başka `catalog_slug` reddedilir.
    - `doc_kinds`: talimattaki tür sözlüğü; başka `doc_kind` reddedilir.
    """

    images: tuple[PageImage, ...]
    instructions: str = field(repr=False)
    prompt: str = field(repr=False)
    known_slugs: frozenset[str]
    doc_kinds: frozenset[str]

    def __post_init__(self) -> None:
        # Çağıran liste verebilir; istek değişmez olsun diye demete çevrilir.
        images = tuple(self.images)
        if not images:
            raise ValueError("images en az bir görüntü içermeli")
        if not all(isinstance(image, PageImage) for image in images):
            raise TypeError("images yalnız PageImage içermeli")
        if not self.instructions.strip():
            raise ValueError("instructions boş olamaz")
        if not self.prompt.strip():
            raise ValueError("prompt boş olamaz")
        for name in ("known_slugs", "doc_kinds"):
            if isinstance(getattr(self, name), str):
                raise TypeError(f"{name} tek bir metin değil, değer koleksiyonu olmalı")
        object.__setattr__(self, "images", images)
        # Çağıran liste/demet verebilir; istek değişmez olsun diye kopyalanır.
        object.__setattr__(self, "known_slugs", frozenset(self.known_slugs))
        object.__setattr__(self, "doc_kinds", frozenset(self.doc_kinds))


@dataclass(frozen=True, slots=True, kw_only=True)
class PhotoCheckRequest:
    """Fotoğraf kontrolü isteği (11.7.1); hiçbir alanı sağlayıcıya özgü değildir.

    - `image`: fotoğraf sayfasının analiz görüntüsü (sayfa analizine giden görüntünün aynısı).
    - `instructions`: sistem talimatı (`app.ai.prompts.photo_check`).
    - `prompt`: değerlendirilecek kuralların metni (kimlik, ad, açıklama).
    - `rules`: sorulan kural kimlikleri, metindeki sırayla; yanıt tam olarak bunları taşımalı.
    """

    image: PageImage
    instructions: str = field(repr=False)
    prompt: str = field(repr=False)
    rules: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.image, PageImage):
            raise TypeError("image bir PageImage olmalı")
        if not self.instructions.strip():
            raise ValueError("instructions boş olamaz")
        if not self.prompt.strip():
            raise ValueError("prompt boş olamaz")
        if isinstance(self.rules, str):
            raise TypeError("rules tek bir metin değil, kural kimliği koleksiyonu olmalı")
        # Çağıran liste verebilir; istek değişmez olsun diye demete çevrilir.
        rules = tuple(self.rules)
        if not rules:
            raise ValueError("rules en az bir kural içermeli")
        if len(set(rules)) != len(rules):
            raise ValueError("rules tekrarsız olmalı")
        object.__setattr__(self, "rules", rules)


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentQueryRequest:
    """Belge isteğinin okunması (12.3.1); hiçbir alanı sağlayıcıya özgü değildir. Görüntü yoktur.

    - `instructions`: sistem talimatı (`app.ai.prompts.document_query`).
    - `prompt`: katalog türleri ve İK'nın mesajı (`app.telegram.intent.build_query_prompt`).
    - `known_slugs`: istemdeki kataloğun slug'ları; başka slug taşıyan yanıt reddedilir.
    - `known_groups`: istemdeki belge gruplarının kimlikleri (12.3.7); başka grup reddedilir.
    """

    instructions: str = field(repr=False)
    prompt: str = field(repr=False)
    known_slugs: frozenset[str]
    known_groups: frozenset[int] = frozenset()

    def __post_init__(self) -> None:
        if not self.instructions.strip():
            raise ValueError("instructions boş olamaz")
        if not self.prompt.strip():
            raise ValueError("prompt boş olamaz")
        if isinstance(self.known_slugs, str):
            raise TypeError("known_slugs tek bir metin değil, slug koleksiyonu olmalı")
        # Çağıran liste/demet verebilir; istek değişmez olsun diye kopyalanır.
        object.__setattr__(self, "known_slugs", frozenset(self.known_slugs))
        object.__setattr__(self, "known_groups", frozenset(self.known_groups))


@dataclass(frozen=True, slots=True, kw_only=True)
class ProfileAnswerRequest:
    """Profil sorusunun yanıtı (12.3.8): talimat ve istem (profiller, soru, dil). Görüntü yoktur.
    Metinler kişisel veri taşır; `repr`'a girmez."""

    instructions: str = field(repr=False)
    prompt: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.instructions.strip():
            raise ValueError("instructions boş olamaz")
        if not self.prompt.strip():
            raise ValueError("prompt boş olamaz")


class AnalysisProvider(abc.ABC):
    """Sayfa analizi sağlayıcısı. `name` `AI_PROVIDER` değeridir, `model` kullanılan modeldir.

    `prescreen_model` aynı sağlayıcının ucuz ön eleme modelidir (13.2.1); boş ya da `model`'le
    aynıysa `None` olur ve ön eleme yapılmaz.
    """

    name: ClassVar[str]

    def __init__(self, *, model: str, prescreen_model: str | None = None) -> None:
        if not model:
            raise ValueError("model adı boş olamaz")
        self.model = model
        prescreen = (prescreen_model or "").strip() or None
        self.prescreen_model = None if prescreen == model else prescreen

    def prescreen_provider(self) -> AnalysisProvider | None:
        """Ucuz ön eleme modeliyle çalışan kopya (13.2.1); `prescreen_model` yoksa `None`.

        Kopya aynı sağlayıcının aynı istemcisini kullanır, kendi ön elemesi yoktur. Hangi sayfanın
        onda kalacağına sağlayıcı değil, boru hattı karar verir (`app.pipeline.analyze`).
        """
        if self.prescreen_model is None:
            return None
        return self._with_model(self.prescreen_model)

    def _with_model(self, model: str) -> AnalysisProvider:
        """Aynı sağlayıcının `model`'le çalışan, ön elemesiz kopyası. Varsayılan: sağlayıcı ön eleme
        modeli desteklemez."""
        raise ProviderConfigError(f"'{self.name}' sağlayıcısı ön eleme modeli desteklemiyor")

    @final
    def analyze_page(self, request: PageAnalysisRequest) -> PageAnalysis:
        """Sayfayı analiz ettirir ve §8.4'e uyan yanıtı döner.

        Hız sınırı (429) ve sağlayıcı hatasında (5xx) en fazla `MAX_ANALYSIS_ATTEMPTS`
        deneme geri çekilmeli yapılır (03.5.1); son denemede de başarısız olursa aynı hata
        yükselir. Diğer `ProviderError` alt türleri ve `PageAnalysisError` yeniden denenmez.
        Yanıt düzeltilmez, eksik alan doldurulmaz.
        """
        raw = self._request_analysis_with_retry(request)
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

    def _request_analysis_with_retry(self, request: PageAnalysisRequest) -> object:
        """`_request_analysis`'i hız sınırı/5xx'te geri çekilmeli yeniden dener (03.5.1)."""
        return _with_retry(self._request_analysis, request)

    @final
    def describe_type(self, request: TypeDescriptionRequest) -> TypeDescription:
        """Türün örnek sayfalarından yapılandırılmış tür açıklaması ürettirir (11.3.1).

        Yeniden deneme `analyze_page`'teki gibidir (03.5.1). Yanıt `validate_type_description`'dan
        geçer; uymayan yanıt `TypeDescriptionError` olur, düzeltilmez.
        """
        return validate_type_description(_with_retry(self._request_description, request))

    @final
    def check_photo(self, request: PhotoCheckRequest) -> PhotoCheck:
        """Fotoğrafı sorulan kurallara göre değerlendirtir (11.7.1).

        Yeniden deneme `analyze_page`'teki gibidir (03.5.1). Yanıt `validate_photo_check`'ten geçer:
        sorulan her kural tam bir kez, başka kural yok; uymayan yanıt `PhotoCheckError` olur,
        düzeltilmez.
        """
        raw = _with_retry(self._request_photo_check, request)
        return validate_photo_check(raw, rules=request.rules)

    @final
    def read_document_query(self, request: DocumentQueryRequest) -> DocumentQuery:
        """İK'nın mesajını belge isteği araç çağrısına çevirtir (12.3.1).

        Yeniden deneme `analyze_page`'teki gibidir (03.5.1). Yanıt `validate_document_query`'den
        geçer: istemdeki katalog dışında slug yok; uymayan yanıt `DocumentQueryError` olur,
        düzeltilmez.
        """
        raw = _with_retry(self._request_document_query, request)
        return validate_document_query(
            raw, known_slugs=request.known_slugs, known_groups=request.known_groups
        )

    @final
    def answer_profile_question(self, request: ProfileAnswerRequest) -> ProfileAnswer:
        """Verilen profillerden soruyu yanıtlatır (12.3.8). Yeniden deneme `analyze_page`'teki
        gibidir; uymayan yanıt `ProfileAnswerError` olur, düzeltilmez."""
        return validate_profile_answer(_with_retry(self._request_profile_answer, request))

    @final
    def propose_type(self, request: TypeProposalRequest) -> TypeProposal:
        """Aday türün örnek sayfalarından tam katalog kaydı taslağı ürettirir (11.5.5).

        Yeniden deneme `analyze_page`'teki gibidir (03.5.1). Yanıt `validate_type_proposal`'dan
        geçer; uymayan yanıt `TypeProposalError` olur, düzeltilmez.
        """
        return validate_type_proposal(_with_retry(self._request_type_proposal, request))

    @final
    def classify_training_page(
        self, request: TrainingClassificationRequest
    ) -> TrainingClassification:
        """Eğitim öğesinin türünü ilk sayfasından sınıflandırtır (11.9.3).

        Yeniden deneme `analyze_page`'teki gibidir (03.5.1). Yanıt
        `validate_training_classification`'dan geçer: istemdeki katalog ve tür sözlüğü dışında değer
        yok; uymayan yanıt `TrainingClassificationError` olur, düzeltilmez.
        """
        raw = _with_retry(self._request_training_classification, request)
        return validate_training_classification(
            raw, known_slugs=request.known_slugs, doc_kinds=request.doc_kinds
        )

    @abc.abstractmethod
    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        """Sağlayıcıyı bir kez çağırır, yapılandırılmış çıktıyı doğrulamadan döner.

        Dönüş JSON metni veya çözülmüş JSON nesnesidir. Çağrı tamamlanamazsa `ProviderError`
        (uygun alt türüyle), yanıtta yapılandırılmış çıktı yoksa `PageAnalysisError` fırlatır.
        Kendi içinde yeniden deneme yapmaz — yeniden deneme `analyze_page`'in işidir (03.5).
        """

    def _request_description(self, request: TypeDescriptionRequest) -> object:
        """Tür açıklaması için sağlayıcıyı bir kez çağırır, yapılandırılmış çıktıyı doğrulamadan
        döner (sözleşmesi `_request_analysis`'inkidir; yapılandırılmış çıktı yoksa
        `TypeDescriptionError`). Varsayılan: sağlayıcı bu işi yapmaz."""
        raise ProviderError(f"'{self.name}' sağlayıcısı tür açıklaması üretmiyor")

    def _request_photo_check(self, request: PhotoCheckRequest) -> object:
        """Fotoğraf kontrolü için sağlayıcıyı bir kez çağırır, yapılandırılmış çıktıyı doğrulamadan
        döner (sözleşmesi `_request_analysis`'inkidir; yapılandırılmış çıktı yoksa
        `PhotoCheckError`). Varsayılan: sağlayıcı bu işi yapmaz."""
        raise ProviderError(f"'{self.name}' sağlayıcısı fotoğraf kontrolü yapmıyor")

    def _request_document_query(self, request: DocumentQueryRequest) -> object:
        """Belge isteği için sağlayıcıyı bir kez çağırır, yapılandırılmış çıktıyı doğrulamadan döner
        (sözleşmesi `_request_analysis`'inkidir; yapılandırılmış çıktı yoksa
        `DocumentQueryError`). Varsayılan: sağlayıcı bu işi yapmaz."""
        raise ProviderError(f"'{self.name}' sağlayıcısı belge isteği okumuyor")

    def _request_profile_answer(self, request: ProfileAnswerRequest) -> object:
        """Profil sorusu için sağlayıcıyı bir kez çağırır, yapılandırılmış çıktıyı doğrulamadan
        döner (yapılandırılmış çıktı yoksa `ProfileAnswerError`). Varsayılan: bu işi yapmaz."""
        raise ProviderError(f"'{self.name}' sağlayıcısı profil sorusu yanıtlamıyor")

    def _request_type_proposal(self, request: TypeProposalRequest) -> object:
        """Tür taslağı için sağlayıcıyı bir kez çağırır, yapılandırılmış çıktıyı doğrulamadan döner
        (sözleşmesi `_request_analysis`'inkidir; yapılandırılmış çıktı yoksa `TypeProposalError`).
        Varsayılan: sağlayıcı bu işi yapmaz."""
        raise ProviderError(f"'{self.name}' sağlayıcısı tür taslağı üretmiyor")

    def _request_training_classification(self, request: TrainingClassificationRequest) -> object:
        """Eğitim sınıflandırması için sağlayıcıyı bir kez çağırır, yapılandırılmış çıktıyı
        doğrulamadan döner (sözleşmesi `_request_analysis`'inkidir; yapılandırılmış çıktı yoksa
        `TrainingClassificationError`). Varsayılan: sağlayıcı bu işi yapmaz."""
        raise ProviderError(f"'{self.name}' sağlayıcısı eğitim sınıflandırması yapmıyor")


def _with_retry[R](call: Callable[[R], object], request: R) -> object:
    """`call(request)`'i hız sınırı (429) ve sağlayıcı hatasında (5xx) geri çekilmeli yeniden dener
    (03.5.1); son denemede de başarısız olursa aynı hata yükselir."""
    for attempt in range(1, MAX_ANALYSIS_ATTEMPTS + 1):
        try:
            return call(request)
        except _RETRYABLE_ERRORS:
            if attempt == MAX_ANALYSIS_ATTEMPTS:
                raise
            time.sleep(RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1))


ProviderFactory = Callable[[Settings], AnalysisProvider]


def _anthropic(settings: Settings) -> AnalysisProvider:
    # SDK yalnız bu sağlayıcı seçildiğinde içe aktarılır.
    from app.ai.anthropic_provider import AnthropicProvider

    return AnthropicProvider.from_settings(settings)


def _openai(settings: Settings) -> AnalysisProvider:
    # SDK yalnız bu sağlayıcı seçildiğinde içe aktarılır.
    from app.ai.openai_provider import OpenAIProvider

    return OpenAIProvider.from_settings(settings)


PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "anthropic": _anthropic,
    "openai": _openai,
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
