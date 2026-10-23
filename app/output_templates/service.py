"""Hazır şablon deposu — yükleme, liste, arşiv/geri al (15.1.1, 15.1.4; PLAN.md §D123 b, f).

**Hazır şablon** İK'nın çalışanlar için çıktı alacağı belge kalıbıdır (iş sözleşmesi, başvuru
formu). Çalışan belgesi değildir: yüklemesi parti açmaz, boru hattına, eşleştirmeye, kuyruğa ve
`documents` tablosuna girmez.

- **Dosya.** PDF, JPEG ya da PNG kabul edilir; Word/Excel ve tanınmayan biçim reddedilir (§D123 b).
  Görüntü img2pdf ile kayıpsız tek sayfalık PDF'e sarılır (K11 — `wrap_image` ile aynı yöntem),
  PDF olduğu gibi kalır. Dosya `KnownDocuments/_sablonlar/<id>/sablon.pdf` altına değişmeden
  yazılır; sayfa önizleme görüntüleri 02.1.1'in render ayarıyla `pages/` altına üretilir. Boyut ve
  sayfa sınırı yüklemeninkidir (01.3.1).
- **Tekrar.** `sha256` saklanan PDF'indir ve tekildir: aynı dosya (aynı görüntü aynı baytlara
  sarılır, 07.8.1) ikinci kez şablon olmaz — `DuplicateTemplateError`.
- **Ad tekil.** `normalize_template_name` 00.4.2 sadeleştirmesidir (belge grubu adıyla aynı kural);
  `file_label` üretilen belgenin K8 etiketidir (`Is-Sozlesmesi`, 15.2.3).
- **Silme yok (R11).** Şablon arşivlenir ve geri alınır; tek adımlıdır (§D61, K16) ve
  `TEMPLATE_ARCHIVED` / `TEMPLATE_RESTORED` olayını kullanıcı adıyla yazar. Olay verisi kişisel
  değer taşımaz (K15).
- Hiçbir fonksiyon commit etmez; iş birimini çağıran kapatır. Dosyalar satır eklendikten sonra
  yazılır (dizin adı şablonun kimliğidir).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import OutputTemplate, OutputTemplateStatus, utcnow
from app.events import EventType, record_event
from app.i18n import N_, Translatable
from app.pipeline.execute_image_utils import _IMAGE_WRAP_ERRORS, _wrap_image_to_pdf
from app.pipeline.render import RenderError, render_pdf_images
from app.storage import DataLayout, FileKind, UnsupportedFileTypeError, detect_file_kind
from app.storage.atomic import replace_file, sha256_bytes, write_file
from app.storage.naming import LABEL_SLUG_MAX_LENGTH
from app.storage.pdfinfo import count_pdf_pages
from app.storage.slug import SlugError, slugify

NAME_MAX_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 200
NORMALIZED_NAME_MAX_LENGTH = 255
# §8.7: yalnız bu türlerdeki boşluklar doldurulur; liste "alan sayısı" bunları sayar.
FILLABLE_KINDS = frozenset({"text", "date"})

NAME_REQUIRED = N_("Şablon adı boş olamaz.")
NAME_TOO_LONG = Translatable(
    N_("Şablon adı en çok {limit} karakter olabilir."), limit=NAME_MAX_LENGTH
)
NAME_UNUSABLE = N_("Şablon adı en az bir harf ya da rakam içermeli.")
DESCRIPTION_TOO_LONG = Translatable(
    N_("Açıklama en çok {limit} karakter olabilir."), limit=DESCRIPTION_MAX_LENGTH
)
FILE_REQUIRED = N_("Bir şablon dosyası seçin (PDF, JPEG ya da PNG).")
FILE_OFFICE = N_(
    "Word ve Excel dosyası şablon olarak kabul edilmez; şablonu PDF, JPEG ya da PNG olarak "
    "yükleyin."
)
FILE_UNSUPPORTED = N_("Bu dosya PDF, JPEG ya da PNG değil; şablon yalnız bu biçimlerde yüklenir.")
FILE_UNREADABLE = N_("Dosya açılamadı: bozuk ya da parola korumalı olabilir.")
FILE_IMAGE_UNWRAPPABLE = N_("Görüntü kayıpsız PDF'e sarılamadı; şablonu PDF olarak yükleyin.")
_OFFICE_KINDS = frozenset({FileKind.DOC, FileKind.DOCX, FileKind.XLS, FileKind.XLSX})
_IMAGE_KINDS = frozenset({FileKind.JPEG, FileKind.PNG})


class TemplateNotFoundError(LookupError):
    """Şablon yok."""


class TemplateFormError(ValueError):
    """Girilen değerler kurala uymuyor; `problems` alan adından mesaj listesine."""

    def __init__(self, problems: dict[str, list[str]]) -> None:
        messages = (str(message) for items in problems.values() for message in items)
        super().__init__("; ".join(messages))
        self.problems = problems


class TemplateNameTakenError(ValueError):
    """Aynı sadeleşmiş adla bir şablon var; `archived` o şablonun arşivde olup olmadığıdır."""

    def __init__(self, name: str, *, archived: bool) -> None:
        super().__init__(name)
        self.name = name
        self.archived = archived


class DuplicateTemplateError(ValueError):
    """Aynı dosya (SHA-256) zaten şablon; `template_id` o şablondur."""

    def __init__(self, template_id: int) -> None:
        super().__init__(template_id)
        self.template_id = template_id


@dataclass(frozen=True, slots=True)
class TemplateSummary:
    """Liste satırı (15.1.1)."""

    id: int
    name: str
    description: str | None
    page_count: int
    field_count: int
    status: str
    uploaded_by: str
    created_at: datetime


@dataclass(slots=True)
class _Problems:
    items: dict[str, list[str]] = field(default_factory=dict)

    def add(self, name: str, message: str) -> None:
        self.items.setdefault(name, []).append(message)

    def raise_if_any(self) -> None:
        if self.items:
            raise TemplateFormError(self.items)


@dataclass(frozen=True, slots=True)
class _PreparedFile:
    pdf: bytes
    source_kind: FileKind
    page_count: int


# --- ad ve dosya ---------------------------------------------------------------------------------


def _single_line(value: str | None) -> str:
    return " ".join((value or "").split())


def normalize_template_name(name: str) -> str:
    """Şablon adının tekillik anahtarı: 00.4.2 slug sadeleştirmesi, küçük harf
    (`"İş Sözleşmesi" → "is_sozlesmesi"`). Harf ya da rakam kalmazsa `SlugError`."""
    return slugify(name, "_", max_length=NORMALIZED_NAME_MAX_LENGTH).casefold()


def template_file_label(name: str) -> str:
    """Üretilen belgenin K8 etiketi (15.2.3): `"İş sözleşmesi" → "Is-sozlesmesi"`."""
    return slugify(name, "-", max_length=LABEL_SLUG_MAX_LENGTH)


def _clean_fields(
    name: str, description: str | None, problems: _Problems
) -> tuple[str, str, str | None]:
    clean_name = _single_line(name)
    normalized = ""
    if not clean_name:
        problems.add("name", NAME_REQUIRED)
    elif len(clean_name) > NAME_MAX_LENGTH:
        problems.add("name", NAME_TOO_LONG)
    else:
        try:
            normalized = normalize_template_name(clean_name)
        except SlugError:
            problems.add("name", NAME_UNUSABLE)
    clean_description = _single_line(description) or None
    if clean_description and len(clean_description) > DESCRIPTION_MAX_LENGTH:
        problems.add("description", DESCRIPTION_TOO_LONG)
    return clean_name, normalized, clean_description


def _prepare_file(
    content: bytes | None, settings: Settings, problems: _Problems
) -> _PreparedFile | None:
    """Dosyayı şablon PDF'ine çevirir (görüntü kayıpsız sarılır); sorun `problems`'a yazılır."""
    if not content:
        problems.add("file", FILE_REQUIRED)
        return None
    if len(content) > settings.max_upload_file_size_bytes:
        problems.add(
            "file",
            Translatable(
                N_("Dosya {limit} MB sınırını aşıyor."),
                limit=f"{settings.max_upload_file_size_bytes / (1024 * 1024):.0f}",
            ),
        )
        return None
    try:
        kind = detect_file_kind(content)
    except UnsupportedFileTypeError:
        problems.add("file", FILE_UNSUPPORTED)
        return None
    if kind in _OFFICE_KINDS:
        problems.add("file", FILE_OFFICE)
        return None
    if kind in _IMAGE_KINDS:
        try:
            pdf = _wrap_image_to_pdf(content)
        except _IMAGE_WRAP_ERRORS:
            problems.add("file", FILE_IMAGE_UNWRAPPABLE)
            return None
    elif kind is FileKind.PDF:
        pdf = content
    else:
        problems.add("file", FILE_UNSUPPORTED)
        return None
    page_count = count_pdf_pages(pdf)
    if not page_count:
        problems.add("file", FILE_UNREADABLE)
        return None
    if page_count > settings.max_upload_pdf_pages:
        problems.add(
            "file",
            Translatable(
                N_("Dosya {limit} sayfa sınırını aşıyor ({count} sayfa)."),
                limit=settings.max_upload_pdf_pages,
                count=page_count,
            ),
        )
        return None
    return _PreparedFile(pdf=pdf, source_kind=kind, page_count=page_count)


# --- okuma ---------------------------------------------------------------------------------------


def field_count(template: OutputTemplate) -> int:
    """Son harita sürümündeki doldurulacak boşluk sayısı (§8.7 `text`/`date`); harita yoksa 0."""
    if not template.maps:
        return 0
    fields = template.maps[-1].json.get("fields") or []
    return sum(
        1 for item in fields if isinstance(item, dict) and item.get("kind") in FILLABLE_KINDS
    )


def list_templates(session: Session, *, status: str | None = None) -> list[TemplateSummary]:
    """Şablonlar, en yenisi başta. `status` verilmezse arşivdekiler dışındakiler (15.1.4)."""
    query = select(OutputTemplate).order_by(
        OutputTemplate.created_at.desc(), OutputTemplate.id.desc()
    )
    if status is None:
        query = query.where(OutputTemplate.status != OutputTemplateStatus.ARCHIVED.value)
    else:
        query = query.where(OutputTemplate.status == status)
    return [
        TemplateSummary(
            id=template.id,
            name=template.name,
            description=template.description,
            page_count=template.page_count,
            field_count=field_count(template),
            status=template.status,
            uploaded_by=template.uploaded_by,
            created_at=template.created_at,
        )
        for template in session.scalars(query)
    ]


def status_counts(session: Session) -> dict[str, int]:
    """Durum başına şablon sayısı (süzgeç sekmeleri)."""
    rows = session.execute(
        select(OutputTemplate.status, func.count()).group_by(OutputTemplate.status)
    )
    counts = {member.value: 0 for member in OutputTemplateStatus}
    counts.update({status: count for status, count in rows})
    return counts


def get_template(session: Session, template_id: int) -> OutputTemplate:
    template = session.get(OutputTemplate, template_id)
    if template is None:
        raise TemplateNotFoundError(template_id)
    return template


# --- yazma ---------------------------------------------------------------------------------------


def _ensure_name_free(session: Session, name: str, normalized: str) -> None:
    other = session.scalar(
        select(OutputTemplate).where(OutputTemplate.normalized_name == normalized)
    )
    if other is not None:
        raise TemplateNameTakenError(
            name, archived=other.status == OutputTemplateStatus.ARCHIVED.value
        )


def _ensure_new_file(session: Session, sha256: str) -> None:
    other = session.scalar(select(OutputTemplate.id).where(OutputTemplate.sha256 == sha256))
    if other is not None:
        raise DuplicateTemplateError(other)


def _write_files(
    layout: DataLayout, template: OutputTemplate, prepared: _PreparedFile, settings: Settings
) -> None:
    """Şablon PDF'ini ve sayfa önizleme görüntülerini yazar; görüntü üretilemezse dizini kaldırır
    (satır da geri alınır — yarım şablon kalmaz)."""
    directory = layout.template_dir(template.id)
    original = layout.template_original_path(template.id)
    try:
        original.parent.mkdir(parents=True, exist_ok=True)
        write_file(original, prepared.pdf)
        images, _ = render_pdf_images(
            prepared.pdf,
            dpi=settings.page_render_dpi,
            max_long_edge=settings.page_render_max_long_edge_px,
            jpeg_quality=settings.page_render_jpeg_quality,
            max_pages=prepared.page_count,
        )
        for index, image in enumerate(images):
            path = layout.template_page_image_path(template.id, index)
            path.parent.mkdir(parents=True, exist_ok=True)
            replace_file(path, image)
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    template.file_path = layout.relative(original)


def create_template(
    session: Session,
    layout: DataLayout,
    settings: Settings,
    *,
    name: str,
    description: str | None,
    content: bytes | None,
    actor: str,
) -> OutputTemplate:
    """15.1.1 — şablonu `draft` olarak ekler, dosyasını ve önizlemelerini yazar, `TEMPLATE_UPLOADED`
    olayını kullanıcı adıyla kaydeder.

    Ad ya da dosya kurala uymazsa `TemplateFormError` (hepsi birlikte); aynı sadeleşmiş adla şablon
    varsa `TemplateNameTakenError`; aynı dosya zaten şablonsa `DuplicateTemplateError`. Aynı anda
    iki istek biri kazanır (tekil dizinler).
    """
    problems = _Problems()
    clean_name, normalized, clean_description = _clean_fields(name, description, problems)
    prepared = _prepare_file(content, settings, problems)
    problems.raise_if_any()
    if prepared is None:  # sorun yazılmadan dönülmez; tip denetimi için
        raise TemplateFormError({"file": [FILE_REQUIRED]})
    _ensure_name_free(session, clean_name, normalized)
    sha256 = sha256_bytes(prepared.pdf)
    _ensure_new_file(session, sha256)
    template = OutputTemplate(
        name=clean_name,
        normalized_name=normalized,
        file_label=template_file_label(clean_name),
        description=clean_description,
        sha256=sha256,
        page_count=prepared.page_count,
        status=OutputTemplateStatus.DRAFT.value,
        uploaded_by=actor,
    )
    try:
        with session.begin_nested():
            session.add(template)
    except IntegrityError:
        # Yarışı kaybeden istek: hangi tekil dizine takıldığı yeniden okunarak söylenir.
        _ensure_new_file(session, sha256)
        raise TemplateNameTakenError(clean_name, archived=False) from None
    try:
        _write_files(layout, template, prepared, settings)
    except RenderError:
        raise TemplateFormError({"file": [FILE_UNREADABLE]}) from None
    session.flush()
    record_event(
        session,
        EventType.TEMPLATE_UPLOADED,
        actor=actor,
        data={
            "template_id": template.id,
            "page_count": template.page_count,
            "sha256": sha256,
            "source_format": prepared.source_kind.value,
            "wrapped": prepared.source_kind in _IMAGE_KINDS,
        },
    )
    return template


def set_template_archived(
    session: Session, template_id: int, archived: bool, *, actor: str
) -> bool:
    """15.1.4 — şablonu arşivler ya da geri alır (tek adım, §D61); durum değiştiyse `True` ve olay.

    Arşivdeki şablon profilde seçilemez, üretilmiş belgeler yerinde kalır. Geri alınan şablon onaylı
    bir harita sürümü varsa `ready`'ye, yoksa `draft`'a döner.
    """
    template = get_template(session, template_id)
    if (template.status == OutputTemplateStatus.ARCHIVED.value) == archived:
        return False
    if archived:
        template.status = OutputTemplateStatus.ARCHIVED.value
        template.archived_at = utcnow()
        template.archived_by = actor
    else:
        approved = any(item.approved_at is not None for item in template.maps)
        template.status = (
            OutputTemplateStatus.READY.value if approved else OutputTemplateStatus.DRAFT.value
        )
        template.archived_at = None
        template.archived_by = None
    session.flush()
    record_event(
        session,
        EventType.TEMPLATE_ARCHIVED if archived else EventType.TEMPLATE_RESTORED,
        actor=actor,
        data={"template_id": template.id, "status": template.status},
    )
    return True
