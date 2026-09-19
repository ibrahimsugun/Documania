"""Tür açıklaması üretimi — PRD 11.3.1.

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
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.ai.prompts.type_description import load_type_description_instructions
from app.ai.provider import AnalysisProvider, PageImage, TypeDescriptionRequest
from app.ai.schemas import Script
from app.ai.type_description import TypeDescription
from app.catalog.schema import CatalogEntry, Sides
from app.config import Settings
from app.pipeline.render import RenderError, image_copy, render_pdf_images
from app.storage import DataLayout, FileKind
from app.storage.examples import (
    ExampleFile,
    ExampleRejectedError,
    check_example,
    example_path,
    list_examples,
)

MAX_DESCRIPTION_PAGES = 8
"""Bir tür açıklaması isteğine giren en çok örnek sayfa."""

SCRIPT_LABELS = {
    Script.LATIN: "Latin",
    Script.CYRILLIC: "Kiril",
    Script.ARABIC: "Arap",
    Script.OTHER: "diğer",
}

_SENTENCE_ENDINGS = (".", "!", "?", "…")


class TypeNotAnalyzedError(ValueError):
    """Tür analiz edilmiyor (`analyze: false`); açıklaması analizde kullanılmaz."""


class NoExamplePagesError(ValueError):
    """Türün açılabilen örnek sayfası yok; `skipped` atlanan örneklerin mesajlarıdır."""

    def __init__(self, skipped: Sequence[str] = ()) -> None:
        self.skipped = tuple(skipped)
        super().__init__("Türün açılabilen örnek sayfası yok.")


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
class GeneratedDescription:
    """Üretilen açıklama: yapılandırılmış hâli, `prompt_description` metni ve girdisi."""

    description: TypeDescription
    text: str
    pages: tuple[ExamplePage, ...]
    omitted: int
    skipped: tuple[str, ...]


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


def build_description_prompt(entry: CatalogEntry, pages: Sequence[ExamplePage]) -> str:
    """İsteğin kullanıcı metni: türün katalog bilgileri ve görüntülerin sırası. Örnekler dosya
    adıyla değil ilk göründükleri sırayla numaralanır."""
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
    lines += [
        f"Zorunlu alanlar: {', '.join(entry.required_fields) or 'yok'}",
        "",
        f"Görüntüler ({len(pages)}, gönderildiği sırayla):",
        *(
            f"{index}. örnek {numbers[page.example]}, sayfa {page.page}"
            for index, page in enumerate(pages, start=1)
        ),
    ]
    return "\n".join(lines)


def describe_type(
    entry: CatalogEntry,
    layout: DataLayout,
    settings: Settings,
    provider: AnalysisProvider,
    *,
    max_pages: int = MAX_DESCRIPTION_PAGES,
) -> GeneratedDescription:
    """Türün örneklerinden yapılandırılmış açıklama ürettirir; hiçbir şey kaydetmez.

    Sağlayıcı hataları (`ProviderError`) ve şemaya uymayan yanıt (`TypeDescriptionError`) olduğu
    gibi yükselir.
    """
    if not entry.analyze:
        raise TypeNotAnalyzedError(entry.slug)
    collected = collect_example_pages(layout, settings, entry.slug, max_pages=max_pages)
    if not collected.images:
        raise NoExamplePagesError(collected.skipped)
    request = TypeDescriptionRequest(
        images=collected.images,
        instructions=load_type_description_instructions(),
        prompt=build_description_prompt(entry, collected.pages),
    )
    description = provider.describe_type(request)
    return GeneratedDescription(
        description=description,
        text=format_description(description),
        pages=collected.pages,
        omitted=collected.omitted,
        skipped=collected.skipped,
    )


def format_description(description: TypeDescription) -> str:
    """Yapılandırılmış açıklamanın `prompt_description` metni: tek satır, kısa cümleler.

    Sıra: düzen, başlıklar, dil/alfabe, alanların yeri, MRZ (yoksa "MRZ yok."), ön/arka yüz farkı.
    Boş liste ve `null` alanın cümlesi yazılmaz; MRZ'nin yokluğu türü tanıttığı için yazılır.
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
    return " ".join(" ".join(part.split()) for part in parts)


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith(_SENTENCE_ENDINGS) else f"{text}."


def _phrase(text: str) -> str:
    """Cümle içine giren parça: sondaki nokta ve noktalı virgül atılır."""
    return text.strip().rstrip(".;").rstrip()
