"""Çıktıya hazırla — PRD 15.2.1, 15.2.2 (PLAN.md §D123 a, d, f).

**Üretilen belge** İK'nın hazır şablonunun **kopyasına** yalnız çalışan profilindeki değerlerin
yazılmasıyla oluşur (K11/K17 istisnası, insan kararı 2026-10-23). Çalışan belgesi değildir:
`documents` tablosuna, belge listesine, paket hesabına (14.2.2), eşleştirmeye ve bota (12.3)
girmez; satırı `generated_documents`'tadır.

- **Harita.** Üretim onay almış en yüksek harita sürümünü (`approve.approved_map`) değiştirmeden
  uygular; yapay zekâya bir şey sorulmaz (K9/R10). Yalnız `text`/`date` kutularına yazılır;
  imza, kaşe, logo, fotoğraf ve çerçeve kutularına ve "boş bırak" (`unassigned`) kutusuna hiçbir
  şey yazılmaz. Sabit metne dokunulmaz.
- **Değerler (`profile_values`).** Latin ad, soyad ve diğer isimler olduğu gibi (05.2.2);
  `full_name` = ad + soyad; tarihler `GG.AA.YYYY`; uyruk ülkenin İngilizce CLDR adı (10.10.6:
  üretilen içerik İngilizce; ülke olmayan MRZ kodu İngilizce açıklamasıyla); pasaport numarası
  `employee_identifiers`'tan (`records.passport_number`); adres, telefon, e-posta güncel ve
  kaldırılmamış iletişim kaydından; `today` sunucunun günü. Profilde boş olan alan boş kalır,
  uydurulmaz: adı `missing_fields`'a girer.
- **Yazım (`fill_template`).** Kutu sayfanın görünen hâline göre normalizedir (önizleme görüntüsü
  döndürmeyi uygular); döndürülmüş sayfada kutu `derotation_matrix` ile sayfa koordinatına çevrilir
  ve metin sayfayla aynı açıda yazılır. PyMuPDF'in yerleşik Nimbus Sans'ı (`Font("helv")`) Latin,
  genişletilmiş Latin ve Kiril harflerini taşır; sayfaya gömülü yazı tipi olarak eklenir. Metin
  haritanın yazı boyutuyla kutuya yazılır; sığmazsa boyut `FONT_STEP` adımlarla `MIN_FONT_SIZE`'a
  dek küçülür; yine sığmazsa **kesilmeden** en küçük boyutla kutunun başından tek parça yazılır
  (kutudan taşar) ve adı `truncated_fields`'a girer.
- **Dosya.** Şablonun orijinali yalnız okunur (R2: SHA-256 değişmez); kopya bellekte doldurulup
  `Employees/<klasör>/Uretilen/<Ad_Soyad>-<Sablon-Etiketi>[-n].pdf` adına yayınlanır (K8;
  `n` şablon başına sıradır, ilki eksiz). Satır yazılamazsa yayınlanan dosya geri alınır.
- **Kayıt.** `generated_documents` satırı yalnız alan **adlarını** taşır; olay
  `OUTPUT_GENERATED` (`template_id`, `map_version`, `generated_document_id`, `filled_fields`,
  `missing_fields`, `truncated_fields`) kullanıcı adıyla — değer hiçbir olaya ve loga yazılmaz.

Yeniden üretimin öncekini eski sürüm yapması, arşiv ve yaşam döngüsü 15.2.3'tür (tm 186). Hiçbir
fonksiyon commit etmez.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import cache

import pymupdf
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.schemas import FILLABLE_KINDS, TemplateField
from app.countries import lookup, non_country_label
from app.db.models import (
    ContactKind,
    Employee,
    EmployeeContact,
    EmployeeStatus,
    GeneratedDocument,
    GeneratedDocumentStatus,
    OutputTemplate,
    OutputTemplateStatus,
)
from app.events import EventType, record_event
from app.matching.records import ACTIVE_CONTACT, passport_number
from app.output_templates.approve import approved_map, field_map_of
from app.output_templates.labels import UNASSIGNED
from app.storage import DataLayout
from app.storage.atomic import write_sequenced
from app.storage.naming import document_stem

OUTPUT_EXTENSION = "pdf"
# Üretilen içeriğin dili (10.10.6): uyruk ülkenin İngilizce adıyla yazılır.
CONTENT_LANGUAGE = "en"
DATE_FORMAT = "%d.%m.%Y"
# Sığmayan metin bu boyuta dek küçülür; haritanın boyutu bundan küçükse o boyutta kalır.
MIN_FONT_SIZE = 6.0
FONT_STEP = 0.5
# Sayfaya eklenen yazı tipinin kaynak adı (PDF `/Font` sözlüğündeki ad).
FONT_RESOURCE = "DocumaniaSans"


class GenerationError(ValueError):
    """Çıktı hazırlanamadı."""


class EmployeeNotEligibleError(GenerationError):
    """Çalışan etkin değil: pasif, birleştirilmiş ya da silinmiş çalışana çıktı hazırlanmaz."""


class TemplateNotReadyError(GenerationError):
    """Şablon hazır değil: taslak, arşivde ya da onaylı haritası yok."""


class TemplateFileMissingError(GenerationError):
    """Şablonun dosyası diskte yok."""


@dataclass(frozen=True, slots=True)
class FilledPdf:
    """Doldurulmuş kopya ve alan adları (sıralı, tekrarsız)."""

    content: bytes
    filled: tuple[str, ...]
    missing: tuple[str, ...]
    truncated: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Generation:
    """Çıktıya hazırlamanın sonucu."""

    document: GeneratedDocument
    filled: tuple[str, ...]
    missing: tuple[str, ...]
    truncated: tuple[str, ...]


# --- değerler ------------------------------------------------------------------------------------


def format_date(value: date) -> str:
    """`GG.AA.YYYY` (§D123 d)."""
    return value.strftime(DATE_FORMAT)


def nationality_name(code: str | None) -> str | None:
    """Uyruk kodunun İngilizce adı: ülke CLDR adıyla (`SRB` → "Serbia"), ülke olmayan MRZ kodu
    İngilizce açıklamasıyla (`XXA` → "Stateless"); tanınmayan kod olduğu gibi."""
    if not code:
        return None
    country = lookup(code)
    if country is not None:
        return country.name(CONTENT_LANGUAGE)
    return non_country_label(code, CONTENT_LANGUAGE) or code


def _current_contacts(session: Session, employee_id: str) -> dict[str, str]:
    """Tür başına güncel, kaldırılmamış iletişim değeri (en son eklenen)."""
    rows = session.scalars(
        select(EmployeeContact)
        .where(
            EmployeeContact.employee_id == employee_id,
            EmployeeContact.is_current.is_(True),
            ACTIVE_CONTACT,
        )
        .order_by(EmployeeContact.id.desc())
    )
    contacts: dict[str, str] = {}
    for row in rows:
        contacts.setdefault(row.kind, row.value)
    return contacts


def profile_values(session: Session, employee: Employee, *, today: date) -> dict[str, str | None]:
    """§8.7 `source` adından çalışanın yazılacak değerine (modül açıklaması); boş alan `None`."""
    contacts = _current_contacts(session, employee.id)
    full_name = " ".join(part for part in (employee.given_names, employee.surname) if part)
    return {
        "given_names": employee.given_names or None,
        "surname": employee.surname or None,
        "full_name": full_name or None,
        "other_names": employee.other_names or None,
        "original_script_name": employee.original_script_name or None,
        "date_of_birth": format_date(employee.date_of_birth) if employee.date_of_birth else None,
        "place_of_birth": employee.place_of_birth or None,
        "mother_name": employee.mother_name or None,
        "father_name": employee.father_name or None,
        "personal_number": employee.personal_number or None,
        "passport_number": passport_number(session, employee.id),
        "nationality": nationality_name(employee.nationality),
        "address": contacts.get(ContactKind.ADDRESS.value),
        "phone": contacts.get(ContactKind.PHONE.value),
        "email": contacts.get(ContactKind.EMAIL.value),
        "today": format_date(today),
    }


# --- PDF -----------------------------------------------------------------------------------------


@cache
def _font_buffer() -> bytes:
    # MuPDF'in yerleşik Helvetica karşılığı (Nimbus Sans): Latin, genişletilmiş Latin, Kiril.
    return pymupdf.Font("helv").buffer


def _write_box(page: pymupdf.Page, item: TemplateField, value: str) -> bool:
    """Değeri kutuya yazar; sığdıysa `True`, en küçük boyutta da sığmayıp taşarak yazıldıysa
    `False`."""
    shown = page.rect
    x0, y0, x1, y1 = item.box
    box = pymupdf.Rect(x0 * shown.width, y0 * shown.height, x1 * shown.width, y1 * shown.height)
    target = box * page.derotation_matrix
    size = float(item.font_size or MIN_FONT_SIZE)
    smallest = min(size, MIN_FONT_SIZE)
    while True:
        spare = page.insert_textbox(
            target, value, fontname=FONT_RESOURCE, fontsize=size, rotate=page.rotation
        )
        if spare >= 0:
            return True
        if size <= smallest:
            break
        size = max(smallest, size - FONT_STEP)
    # Kesilmez: en küçük boyutla kutunun başından yazılır, taşan kısım kutunun dışına çıkar.
    origin = pymupdf.Point(box.x0, box.y0 + smallest) * page.derotation_matrix
    page.insert_text(origin, value, fontname=FONT_RESOURCE, fontsize=smallest, rotate=page.rotation)
    return False


def _add(names: list[str], name: str) -> None:
    if name not in names:
        names.append(name)


def fill_template(
    pdf: bytes, fields: Sequence[TemplateField], values: Mapping[str, str | None]
) -> FilledPdf:
    """Şablonun PDF baytlarından doldurulmuş **kopyayı** üretir (modül açıklaması); verilen baytlar
    değişmez."""
    filled: list[str] = []
    missing: list[str] = []
    truncated: list[str] = []
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        fonted: set[int] = set()
        for item in fields:
            if item.kind not in FILLABLE_KINDS or item.source in (None, UNASSIGNED):
                continue
            value = (values.get(item.source) or "").strip()
            if not value:
                _add(missing, item.source)
                continue
            page = document[item.page]
            if item.page not in fonted:
                page.insert_font(fontname=FONT_RESOURCE, fontbuffer=_font_buffer())
                fonted.add(item.page)
            if not _write_box(page, item, value):
                _add(truncated, item.source)
            _add(filled, item.source)
        content = document.tobytes(garbage=3, deflate=True)
    return FilledPdf(content, tuple(filled), tuple(missing), tuple(truncated))


# --- üretim --------------------------------------------------------------------------------------


def _next_sequence_no(session: Session, employee_id: str, template_id: int) -> int:
    previous = session.scalar(
        select(func.max(GeneratedDocument.sequence_no)).where(
            GeneratedDocument.employee_id == employee_id,
            GeneratedDocument.template_id == template_id,
        )
    )
    return (previous or 0) + 1


def generate_document(
    session: Session,
    layout: DataLayout,
    template: OutputTemplate,
    employee: Employee,
    *,
    actor: str,
    today: date | None = None,
) -> Generation:
    """15.2.1 — şablonun kopyasını çalışanın profil değerleriyle doldurur, `Uretilen/`'e yazar,
    `generated_documents` satırını ve `OUTPUT_GENERATED` olayını ekler (tek adım, §D61).

    Çalışan etkin değilse `EmployeeNotEligibleError`; şablon hazır değilse ya da onaylı haritası
    yoksa `TemplateNotReadyError`; şablon dosyası yoksa `TemplateFileMissingError`.
    """
    if employee.status != EmployeeStatus.ACTIVE.value:
        raise EmployeeNotEligibleError(employee.id)
    row = approved_map(template)
    if template.status != OutputTemplateStatus.READY.value or row is None:
        raise TemplateNotReadyError(template.id)
    try:
        source = layout.resolve(template.file_path or "")
    except ValueError:
        raise TemplateFileMissingError(template.id) from None
    if not source.is_file():
        raise TemplateFileMissingError(template.id)

    field_map = field_map_of(row, page_count=template.page_count)
    values = profile_values(session, employee, today=today or date.today())
    filled = fill_template(source.read_bytes(), field_map.fields, values)

    directory = layout.generated_dir(employee.folder_name)
    directory.mkdir(parents=True, exist_ok=True)
    stored = write_sequenced(
        directory,
        document_stem(employee.given_names, employee.surname, template.file_label),
        OUTPUT_EXTENSION,
        filled.content,
        preferred_sequence_no=_next_sequence_no(session, employee.id, template.id),
    )
    try:
        document = GeneratedDocument(
            employee_id=employee.id,
            template_id=template.id,
            map_id=row.id,
            path=layout.relative(stored.path),
            sequence_no=stored.sequence_no,
            status=GeneratedDocumentStatus.ACTIVE.value,
            filled_fields_json=list(filled.filled),
            missing_fields_json=list(filled.missing),
            generated_by=actor,
        )
        session.add(document)
        session.flush()
        record_event(
            session,
            EventType.OUTPUT_GENERATED,
            employee_id=employee.id,
            actor=actor,
            data={
                "template_id": template.id,
                "map_version": row.version,
                "generated_document_id": document.id,
                "filled_fields": list(filled.filled),
                "missing_fields": list(filled.missing),
                "truncated_fields": list(filled.truncated),
            },
        )
    except BaseException:
        stored.path.unlink(missing_ok=True)
        raise
    return Generation(document, filled.filled, filled.missing, filled.truncated)


# --- okuma ---------------------------------------------------------------------------------------


def ready_templates(session: Session) -> list[OutputTemplate]:
    """Profilde seçilebilen şablonlar: `ready` olanlar, ada göre (arşivdeki seçilemez, 15.1.4)."""
    return list(
        session.scalars(
            select(OutputTemplate)
            .where(OutputTemplate.status == OutputTemplateStatus.READY.value)
            .order_by(OutputTemplate.name, OutputTemplate.id)
        )
    )


def employee_outputs(session: Session, employee_id: str) -> list[GeneratedDocument]:
    """Çalışanın üretilen belgeleri, en yenisi başta; kalıcı silinenler (`deleted`) dışında."""
    return list(
        session.scalars(
            select(GeneratedDocument)
            .where(
                GeneratedDocument.employee_id == employee_id,
                GeneratedDocument.status != GeneratedDocumentStatus.DELETED.value,
            )
            .order_by(GeneratedDocument.generated_at.desc(), GeneratedDocument.id.desc())
        )
    )
