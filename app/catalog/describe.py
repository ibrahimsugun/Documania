"""Tür açıklaması üretimi — PRD 11.3.1, 11.8.1.

Bir belge türünün örnek belgelerinden (11.2.1, `KnownDocuments/examples/<slug>/`) yapay zekâya
yapılandırılmış tür açıklaması (`app.ai.type_description.TypeDescription`) ürettirir ve onu
katalogdaki `prompt_description` metnine çevirir (`format_description`). Açıklama bir kez üretilir,
analiz talimatına metin olarak girer (11.4): her analizde örnek görüntü göndermek gerekmez.

- **Girdi:** türün örnekleri ad sırasıyla, her birinin sayfaları sırasıyla; toplam en çok
  `MAX_DESCRIPTION_PAGES` sayfa tek istekte gider, gerisi gönderilmez ve sayılır. PDF sayfası analiz
  görüntüsüyle aynı ölçekte JPEG'e render edilir, JPEG/PNG'nin EXIF yönelimi uygulanır — ikisi de
  bellekte yapılır, diske yazılmaz; örnek dosyası değişmez (K10, K11). Açılamayan örnek (elle
  konmuş bozuk dosya, sınırı aşan boyut) atlanır ve bildirilir. Hiç sayfa kalmazsa
  `NoExamplePagesError`.
- **İstek:** sistem talimatı `app.ai.prompts.type_description`; kullanıcı metni türün katalog
  bilgileri (ad, ülke, yüz yapısı, beklenen sayfa, zorunlu alanlar) ve görüntülerin hangi örneğin
  hangi sayfası olduğu. Örneklerin dosya adı isteğe konmaz, sıra numarasıyla anılır.
- **Yalnız analiz edilen tür** (`analyze: true`): öteki türün açıklaması analiz talimatına girmez
  (11.4.1), üretilmez (`TypeNotAnalyzedError`).
- **Hiçbir şey kaydedilmez.** Sonuç öneridir: panel onu formun "Analizci için açıklama" alanına
  yazar, İK düzenleyip türü kaydeder (`update_type`, 11.1.1). Örnekteki kişiye ait bir değer
  yanıta sızmışsa kaydetmeden önce görülür.

**Fotoğraf örneklerinden öğrenme (11.8.1).** Fotoğraf türünde (`PHOTO_RULE_TYPES`) **kabul edilen
fotoğraflar** kendiliğinden örnek işaretlenir (`accepted_photos`) ve açıklamayı besler:

- **Kabul edilen fotoğraf:** türün `active` çıktı belgesi (çalışanın Hazir klasöründe) ve kaynak
  sayfalarının her birinin saklı fotoğraf kontrolünde (`pages.photo_check_json`, 11.7.1) türün
  **şu an** açık olan her kuralı `pass` (`is_accepted_photo`). `fail`, `unsure`, değerlendirilmemiş
  kural (kontrolü yok, sonradan açılmış kural) ya da okunamayan kayıt fotoğrafı örnek yapmaz; hiç
  açık kural yoksa örnek yoktur. Eski sürüm (K18) ve arşivlenmiş belge örnek değildir. İşaret
  ayrıca saklanmaz, kayıtlardan her okumada yeniden çıkarılır: kural seti değişince örnekler de
  değişir.
- **Girdi:** fotoğraflar yeniden eskiye, her biri tek görüntü (dosyanın ilk sayfası), örnek
  belgelerin sayfalarından sonra aynı istekte. Sınır paylaşılır: fotoğraf varsa sınırın yarısına
  kadarı (`min(fotoğraf sayısı, sınır // 2)`) fotoğraflara ayrılır, örnek sayfalar kalanı alır,
  örneklerin kullanmadığı yer yine fotoğraflarındır. Fotoğraf dosyası okunur; değiştirilmez,
  kopyalanmaz (K11). İsteğe belge kimliği, dosya adı ya da çalışan bilgisi konmaz. Açılamayan
  fotoğraf atlanır ve belge numarasıyla bildirilir.
- **Çıktı:** kullanıcı metni "Fotoğraf türü: evet" satırını taşır; yanıtın `accepted_photo` alanı
  şirketin kabul ettiği fotoğrafın tanımıdır ve metne "Kabul edilen fotoğraf: …" olarak girer.
  Fotoğraf türü olmayan türün yanıtında `accepted_photo` doluysa yanıt reddedilir
  (`TypeDescriptionError`), düzeltilmez.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.photo_check import PhotoCheck, PhotoRuleResult
from app.ai.prompts.type_description import load_type_description_instructions
from app.ai.provider import AnalysisProvider, PageImage, TypeDescriptionRequest
from app.ai.schemas import Script
from app.ai.type_description import TypeDescription, TypeDescriptionError
from app.catalog.photo_rules import PHOTO_RULE_TYPES, PhotoRuleSetting, enabled_photo_rules
from app.catalog.schema import CatalogEntry, Sides
from app.config import Settings
from app.db.models import Document, DocumentStatus, Page
from app.pipeline.render import RenderError, image_copy, render_pdf_images
from app.storage import DataLayout, FileKind, UnsupportedFileTypeError, detect_file_kind
from app.storage.examples import (
    ExampleFile,
    ExampleRejectedError,
    check_example,
    example_path,
    list_examples,
)

MAX_DESCRIPTION_PAGES = 8
"""Bir tür açıklaması isteğine giren en çok görüntü (örnek sayfa + kabul edilen fotoğraf)."""

SCRIPT_LABELS = {
    Script.LATIN: "Latin",
    Script.CYRILLIC: "Kiril",
    Script.ARABIC: "Arap",
    Script.OTHER: "diğer",
}

_SENTENCE_ENDINGS = (".", "!", "?", "…")
_PHOTO_FILE_KINDS = frozenset({FileKind.PDF, FileKind.JPEG, FileKind.PNG})
_NOT_PHOTO_TYPE = "accepted_photo: fotoğraf türü olmayan belgede null olmalı"


class TypeNotAnalyzedError(ValueError):
    """Tür analiz edilmiyor (`analyze: false`); açıklaması analizde kullanılmaz."""


class NoExamplePagesError(ValueError):
    """Türün açılabilen örnek sayfası yok; `skipped` atlanan örneklerin mesajlarıdır."""

    def __init__(self, skipped: Sequence[str] = ()) -> None:
        self.skipped = tuple(skipped)
        super().__init__("Türün açılabilen örnek sayfası yok.")


class PhotoUnreadableError(ValueError):
    """Kabul edilen fotoğrafın dosyası açılamadı; mesaj panelde gösterilir."""


@dataclass(frozen=True, slots=True)
class ExamplePage:
    """İsteğe giren bir örnek sayfa: örnek dosyanın adı ve 1 tabanlı sayfa numarası."""

    example: str
    page: int


@dataclass(frozen=True, slots=True)
class ExamplePages:
    """Toplanan örnek sayfalar ve görüntüleri (aynı sırada); `omitted` sınır yüzünden
    gönderilmeyen sayfa sayısı, `skipped` açılamayan örneklerin mesajları."""

    pages: tuple[ExamplePage, ...]
    images: tuple[PageImage, ...]
    omitted: int
    skipped: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AcceptedPhoto:
    """Örnek işaretlenen kabul edilmiş fotoğraf (11.8.1): türün Hazir'daki çıktı belgesi; `path`
    veri köküne göreli dosya yoludur (`documents.path`)."""

    document_id: int
    path: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PhotoPages:
    """İsteğe giren kabul edilmiş fotoğraflar (belge kimlikleri) ve görüntüleri (aynı sırada);
    `omitted` sınır yüzünden gönderilmeyen fotoğraf sayısı, `skipped` açılamayanların mesajları."""

    photos: tuple[int, ...]
    images: tuple[PageImage, ...]
    omitted: int
    skipped: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GeneratedDescription:
    """Üretilen açıklama: yapılandırılmış hâli, `prompt_description` metni ve girdisi. `photos`
    isteğe giren kabul edilmiş fotoğrafların belge kimlikleri, `photos_omitted` sınır yüzünden
    gönderilmeyen fotoğraf sayısı (11.8.1); `skipped` açılamayan örnek ve fotoğrafların
    mesajları."""

    description: TypeDescription
    text: str
    pages: tuple[ExamplePage, ...]
    omitted: int
    skipped: tuple[str, ...]
    photos: tuple[int, ...] = ()
    photos_omitted: int = 0


# --- kabul edilen fotoğraflar (11.8.1) -------------------------------------------------------


def is_accepted_photo(
    rules: Sequence[PhotoRuleSetting], checks: Sequence[PhotoCheck | None]
) -> bool:
    """Fotoğraf örnek sayılır mı (11.8.1); saf işlevdir.

    `rules` türün açık kuralları, `checks` fotoğrafın kaynak sayfalarının saklı kontrolleri (`None`:
    kontrol yok ya da okunamadı). Her sayfada her kural `pass` ise evet; açık kural ya da sayfa
    yoksa, bir kural `fail`/`unsure` ya da değerlendirilmemişse hayır.
    """
    if not rules or not checks:
        return False
    for check in checks:
        if check is None:
            return False
        for rule in rules:
            verdict = check.verdict(rule.id)
            if verdict is None or verdict.result is not PhotoRuleResult.PASS:
                return False
    return True


def accepted_photos(
    session: Session, type_slug: str, photo_rules: Mapping[str, Any] | None
) -> tuple[AcceptedPhoto, ...]:
    """Türün örnek işaretlenen kabul edilmiş fotoğrafları, yeniden eskiye (11.8.1).

    `photo_rules` türün kayıtlı kural setidir (`known_document_types.photo_rules`); tür formu kural
    taşımaz. Fotoğraf türü değilse ya da açık kural yoksa boş. Yalnız okur; oturum commit edilmez.
    """
    if type_slug not in PHOTO_RULE_TYPES:
        return ()
    rules = enabled_photo_rules(photo_rules)
    if not rules:
        return ()
    documents = list(
        session.scalars(
            select(Document)
            .where(
                Document.type_slug == type_slug,
                Document.status == DocumentStatus.ACTIVE.value,
            )
            .order_by(Document.created_at.desc(), Document.id.desc())
        )
    )
    sources = {document.id: _source_refs(document.source_refs_json) for document in documents}
    file_ids = {file_id for refs in sources.values() for file_id, _ in refs or ()}
    pages: dict[int, dict[int, Page]] = {}
    if file_ids:
        for page in session.scalars(select(Page).where(Page.file_id.in_(file_ids))):
            pages.setdefault(page.file_id, {})[page.index] = page
    accepted = []
    for document in documents:
        refs = sources[document.id]
        if refs is None:
            continue
        checks = [
            _stored_check(page)
            for file_id, indexes in refs
            for page in _source_pages(pages, file_id, indexes)
        ]
        if is_accepted_photo(rules, checks):
            accepted.append(AcceptedPhoto(document.id, document.path, document.created_at))
    return tuple(accepted)


def _source_refs(raw: object) -> list[tuple[int, tuple[int, ...]]] | None:
    """`source_refs_json` → `(file_id, sayfalar)`; biçim bozuksa ya da boşsa `None` (fotoğraf
    örnek sayılmaz). Boş sayfa listesi bütün dosyadır (K15)."""
    if not isinstance(raw, list) or not raw:
        return None
    refs = []
    for ref in raw:
        if not isinstance(ref, dict):
            return None
        file_id, indexes = ref.get("file_id"), ref.get("pages")
        if type(file_id) is not int or not isinstance(indexes, list):
            return None
        if any(type(index) is not int for index in indexes):
            return None
        refs.append((file_id, tuple(indexes)))
    return refs


def _source_pages(
    pages: Mapping[int, Mapping[int, Page]], file_id: int, indexes: tuple[int, ...]
) -> list[Page | None]:
    """Kaynağın sayfa satırları; bulunmayan sayfa `None`. Bütün dosya (boş liste) dosyanın bütün
    sayfalarıdır; dosyanın sayfası yoksa tek `None`."""
    of_file = pages.get(file_id, {})
    if not indexes:
        return [of_file[index] for index in sorted(of_file)] or [None]
    return [of_file.get(index) for index in indexes]


def _stored_check(page: Page | None) -> PhotoCheck | None:
    if page is None or page.photo_check_json is None:
        return None
    try:
        return PhotoCheck.model_validate(page.photo_check_json)
    except ValidationError:
        # Okunamayan kayıt değerlendirme sayılmaz (planın okuyuşu, 11.7.1).
        return None


# --- isteğin görüntüleri ---------------------------------------------------------------------


def collect_example_pages(
    layout: DataLayout,
    settings: Settings,
    type_slug: str,
    *,
    max_pages: int = MAX_DESCRIPTION_PAGES,
) -> ExamplePages:
    """Türün örneklerinden en çok `max_pages` sayfanın analiz görüntüsünü toplar (ad sırasıyla,
    sayfa sırasıyla). Örnek dosyası okunur, değiştirilmez; görüntüler bellektedir."""
    pages: list[ExamplePage] = []
    images: list[PageImage] = []
    omitted = 0
    skipped: list[str] = []
    for example in list_examples(layout, type_slug):
        try:
            rendered, page_count = _render(
                layout, settings, type_slug, example, max_pages - len(images)
            )
        except (ExampleRejectedError, RenderError, OSError) as exc:
            # Bozuk görüntü Pillow'da `OSError`dır (kesik dosya, tanınmayan içerik).
            skipped.append(
                str(exc)
                if isinstance(exc, ExampleRejectedError)
                else f"'{example.name}' dosyası açılamadı; bozuk olabilir."
            )
            continue
        for number, data in enumerate(rendered, start=1):
            pages.append(ExamplePage(example.name, number))
            images.append(PageImage(data))
        omitted += page_count - len(rendered)
    return ExamplePages(tuple(pages), tuple(images), omitted, tuple(skipped))


def _render(
    layout: DataLayout, settings: Settings, type_slug: str, example: ExampleFile, limit: int
) -> tuple[list[bytes], int]:
    """Örneğin ilk `limit` sayfasının görüntüsü ve toplam sayfa sayısı."""
    max_bytes = settings.max_upload_file_size_bytes
    if example.size > max_bytes:
        # Dosya belleğe alınmadan reddedilir; mesaj yüklemedekiyle aynıdır.
        raise ExampleRejectedError(
            f"'{example.name}' dosyası {max_bytes / (1024 * 1024):.0f} MB sınırını aşıyor."
        )
    path = example_path(layout, type_slug, example.name)
    if path is None:
        raise ExampleRejectedError(f"'{example.name}' dosyası bulunamadı.")
    content = path.read_bytes()
    kind = check_example(example.name, content, max_bytes=max_bytes)
    return page_images(content, kind, settings, limit)


def page_images(
    content: bytes, kind: FileKind, settings: Settings, limit: int
) -> tuple[list[bytes], int]:
    """PDF'in ilk `limit` sayfasının analiz ölçeğindeki JPEG'i ya da JPEG/PNG'nin EXIF yönelimi
    uygulanmış kopyası (bellekte) ve dosyanın sayfa sayısı.

    Paylaşılan yardımcıdır: tür açıklaması (örnekler, kabul edilen fotoğraflar) ve eğitim modunun
    yapay zekâ adımı (`app.training.classification`, 11.9.3) aynı ölçekte görüntü gönderir. Dosya
    okunmaz ve yazılmaz; içerik değişmez (K10, K11). PDF render edilemezse `RenderError`, görüntü
    çözülemezse Pillow'un `OSError`'ı yükselir.
    """
    if kind is FileKind.PDF:
        return render_pdf_images(
            content,
            dpi=settings.page_render_dpi,
            max_long_edge=settings.page_render_max_long_edge_px,
            jpeg_quality=settings.page_render_jpeg_quality,
            max_pages=limit,
        )
    if limit <= 0:
        return [], 1
    copy = image_copy(content, jpeg_quality=settings.page_render_jpeg_quality)
    return [copy.content], 1


def collect_photo_pages(
    layout: DataLayout,
    settings: Settings,
    photos: Sequence[AcceptedPhoto],
    *,
    max_pages: int,
) -> PhotoPages:
    """Kabul edilen fotoğrafların görüntüleri, verilen sırayla, en çok `max_pages` fotoğraf; her
    fotoğraf tek görüntüdür (dosyanın ilk sayfası). Dosya okunur, değiştirilmez; görüntüler
    bellektedir. Açılamayan fotoğraf atlanır ve sınıra sayılmaz."""
    sent: list[int] = []
    images: list[PageImage] = []
    skipped: list[str] = []
    tried = 0
    for photo in photos:
        if len(images) >= max_pages:
            break
        tried += 1
        try:
            image = _photo_image(layout, settings, photo)
        except PhotoUnreadableError as exc:
            skipped.append(str(exc))
            continue
        sent.append(photo.document_id)
        images.append(PageImage(image))
    return PhotoPages(tuple(sent), tuple(images), len(photos) - tried, tuple(skipped))


def _photo_image(layout: DataLayout, settings: Settings, photo: AcceptedPhoto) -> bytes:
    # Mesaj belge numarasını taşır, dosya adını değil: ad çalışanın adıdır (CONVENTIONS §6).
    label = f"Kabul edilen fotoğraf (belge {photo.document_id})"
    max_bytes = settings.max_upload_file_size_bytes
    try:
        path = layout.resolve(photo.path)
        if path.stat().st_size > max_bytes:
            raise PhotoUnreadableError(
                f"{label} {max_bytes / (1024 * 1024):.0f} MB sınırını aşıyor."
            )
        content = path.read_bytes()
        kind = detect_file_kind(content)
        if kind not in _PHOTO_FILE_KINDS:
            raise UnsupportedFileTypeError
        rendered, _ = page_images(content, kind, settings, 1)
    except PhotoUnreadableError:
        raise
    except (ValueError, OSError):
        # `ValueError`: geçersiz saklı yol, tanınmayan içerik, `RenderError` (sayfasız PDF dahil);
        # `OSError`: dosya yok ya da görüntü bozuk.
        raise PhotoUnreadableError(f"{label} açılamadı.") from None
    return rendered[0]


# --- istek ve metin --------------------------------------------------------------------------


def build_description_prompt(
    entry: CatalogEntry, pages: Sequence[ExamplePage], *, photos: int = 0
) -> str:
    """İsteğin kullanıcı metni: türün katalog bilgileri ve görüntülerin sırası. Örnekler dosya
    adıyla değil ilk göründükleri sırayla numaralanır; `photos` örnek sayfalardan sonra gelen
    kabul edilmiş fotoğrafların sayısıdır (11.8.1). Fotoğraf türünde "Fotoğraf türü: evet" yazılır.
    """
    numbers: dict[str, int] = {}
    for page in pages:
        numbers.setdefault(page.example, len(numbers) + 1)
    sides = "ön ve arka yüz (front_back)" if entry.sides is Sides.FRONT_BACK else "tek yüz (single)"
    lines = [
        f"Belge türü: {entry.name} (`{entry.slug}`)",
        f"Ülke: {entry.country or 'belirtilmemiş'}",
        f"Yüz yapısı: {sides}",
    ]
    if entry.expected_pages is not None:
        lines.append(f"Beklenen sayfa: {entry.expected_pages.min}–{entry.expected_pages.max}")
    lines.append(f"Zorunlu alanlar: {', '.join(entry.required_fields) or 'yok'}")
    if entry.slug in PHOTO_RULE_TYPES:
        lines.append("Fotoğraf türü: evet")
    lines += [
        "",
        f"Görüntüler ({len(pages) + photos}, gönderildiği sırayla):",
        *(
            f"{index}. örnek {numbers[page.example]}, sayfa {page.page}"
            for index, page in enumerate(pages, start=1)
        ),
        *(
            f"{len(pages) + number}. kabul edilen fotoğraf {number}"
            for number in range(1, photos + 1)
        ),
    ]
    return "\n".join(lines)


def describe_type(
    entry: CatalogEntry,
    layout: DataLayout,
    settings: Settings,
    provider: AnalysisProvider,
    *,
    photos: Sequence[AcceptedPhoto] = (),
    max_pages: int = MAX_DESCRIPTION_PAGES,
) -> GeneratedDescription:
    """Türün örneklerinden — fotoğraf türünde ayrıca kabul edilen fotoğraflardan (`photos`,
    `accepted_photos`; 11.8.1) — yapılandırılmış açıklama ürettirir; hiçbir şey kaydetmez.
    Fotoğraf türü olmayan türde `photos` yok sayılır.

    Sağlayıcı hataları (`ProviderError`) ve şemaya uymayan yanıt (`TypeDescriptionError`) olduğu
    gibi yükselir.
    """
    if not entry.analyze:
        raise TypeNotAnalyzedError(entry.slug)
    is_photo_type = entry.slug in PHOTO_RULE_TYPES
    if not is_photo_type:
        photos = ()
    reserved = min(len(photos), max_pages // 2)
    collected = collect_example_pages(layout, settings, entry.slug, max_pages=max_pages - reserved)
    taken = collect_photo_pages(
        layout, settings, photos, max_pages=max_pages - len(collected.images)
    )
    skipped = (*collected.skipped, *taken.skipped)
    if not collected.images and not taken.images:
        raise NoExamplePagesError(skipped)
    request = TypeDescriptionRequest(
        images=(*collected.images, *taken.images),
        instructions=load_type_description_instructions(),
        prompt=build_description_prompt(entry, collected.pages, photos=len(taken.images)),
    )
    description = provider.describe_type(request)
    if not is_photo_type and description.accepted_photo is not None:
        # Kabul edilen fotoğrafın tanımı yalnız fotoğraf türünün açıklamasına girer; yanıt
        # düzeltilmez, reddedilir.
        raise TypeDescriptionError([_NOT_PHOTO_TYPE])
    return GeneratedDescription(
        description=description,
        text=format_description(description),
        pages=collected.pages,
        omitted=collected.omitted,
        skipped=skipped,
        photos=taken.photos,
        photos_omitted=taken.omitted,
    )


def format_description(description: TypeDescription) -> str:
    """Yapılandırılmış açıklamanın `prompt_description` metni: tek satır, kısa cümleler.

    Sıra: düzen, başlıklar, dil/alfabe, alanların yeri, MRZ (yoksa "MRZ yok."), ön/arka yüz farkı,
    kabul edilen fotoğraf (11.8.1). Boş liste ve `null` alanın cümlesi yazılmaz; MRZ'nin yokluğu
    türü tanıttığı için yazılır.
    """
    parts = [_sentence(description.layout)]
    if description.headings:
        parts.append(f"Başlıklar: {' / '.join(description.headings)}.")
    language = []
    if description.languages:
        language.append(f"dil: {', '.join(description.languages)}")
    if description.scripts:
        labels = ", ".join(SCRIPT_LABELS[script] for script in description.scripts)
        language.append(f"alfabe: {labels}")
    if language:
        text = "; ".join(language)
        parts.append(f"{text[0].upper()}{text[1:]}.")
    if description.field_locations:
        locations = "; ".join(
            f"{item.field} — {_phrase(item.location)}" for item in description.field_locations
        )
        parts.append(f"Alanlar: {locations}.")
    if description.mrz is None:
        parts.append("MRZ yok.")
    else:
        parts.append(
            f"MRZ: {description.mrz.line_count} satır, {_phrase(description.mrz.location)}."
        )
    if description.side_differences is not None:
        parts.append(f"Ön/arka yüz: {_sentence(description.side_differences)}")
    if description.accepted_photo is not None:
        parts.append(f"Kabul edilen fotoğraf: {_sentence(description.accepted_photo)}")
    return " ".join(" ".join(part.split()) for part in parts)


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith(_SENTENCE_ENDINGS) else f"{text}."


def _phrase(text: str) -> str:
    """Cümle içine giren parça: sondaki nokta ve noktalı virgül atılır."""
    return text.strip().rstrip(".;").rstrip()
