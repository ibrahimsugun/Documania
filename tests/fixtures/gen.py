"""Sentetik test belgeleri üretir (CONVENTIONS §6, PRD 09.3.1) — gerçek kimlik belgesi kullanılmaz.

İki katman vardır:

- **Fiziksel yapı** (dosyanın başı): boş sayfa, geometrik desen, Word/Excel imzası. Boyut/sayfa
  sınırı, gruplama, render gibi yalnız dosyanın yapısına bakan testler içindir.
- **Kimlikli sentetik belgeler** (`# --- 09.3.1` bölümü): kurgusal kişiler için pasaport, ehliyet,
  oturma izni, çalışma izni, vesikalık ve katalog dışı belge sayfaları. Her `SyntheticPage` iki
  şeyi birlikte taşır: sayfaya yazılanı (görünür metin, MRZ, fotoğraf) ve analizcinin o sayfa için
  döndüreceği kayıtlı yanıtı (§8.4). İkisi aynı değerlerden üretildiği için birbirini tutar;
  kabul senaryoları dosyayı `make_document_pdf_bytes`/`make_page_image_bytes` ile, sağlayıcıyı
  `recorded_provider` ile kurar (yapay zekâ canlı çağrılmaz). Vesikalık sayfası ayrıca fotoğraf
  kontrolünün (11.7.1) kayıtlı yanıtını taşır; sağlayıcı onu sayfanın analizinin hemen ardından
  verir.

MRZ (§20.1) burada ayrıştırıcıdan (`app.matching.mrz`) **bağımsız** yazılır: kontrol hanesi
§20.1.4, bileşik hane §20.1.5, alan konumları §20.1.3. Üreteç alanları anlamlarıyla birleştirir,
ayrıştırıcı konumlardan okur; iki taraf aynı haneyi bulmalıdır (`tests/fixtures/test_gen.py`).

Kişiler, numaralar ve adresler kurgusaldır (`ORNEKOVA TEST`, `00 0000001` …). Görünür metin ve MRZ
yalnız test fikstürüdür; ürün kodu belge içeriği üretmez, değiştirmez (K11, K17). Aynı girdi aynı
baytları verir (PDF kimliği ve tarihi yazılmaz) — tekrar yükleme (S2) SHA-256 ile tespit edilir.
"""

from __future__ import annotations

import itertools
import json
import re
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import pymupdf
from PIL import Image, ImageDraw
from pypdf import PdfWriter

from app.ai.recording_provider import RecordingProvider
from app.catalog import CatalogEntry, load_seed_catalog
from app.catalog.photo_rules import RESOLUTION_RULE, enabled_photo_rules

A4 = (595.0, 842.0)


def make_pdf_bytes(page_count: int = 1) -> bytes:
    """`page_count` boş sayfalık gerçek (pypdf ile okunabilir) bir PDF döner."""
    return make_sized_pdf_bytes([A4] * page_count)


def make_sized_pdf_bytes(
    sizes: Sequence[tuple[float, float]],
    *,
    rotate: int = 0,
    password: str | None = None,
) -> bytes:
    """Her sayfası `sizes`'taki (genişlik, yükseklik) nokta boyutunda boş PDF döner.

    `rotate` her sayfaya PDF `/Rotate` değeri olarak yazılır; `password` verilirse PDF
    kullanıcı parolasıyla şifrelenir.
    """
    writer = PdfWriter()
    for width, height in sizes:
        page = writer.add_blank_page(width=width, height=height)
        if rotate:
            page.rotate(rotate)
    if password is not None:
        writer.encrypt(password)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_text_pdf_bytes(pages: Sequence[str | None], size: tuple[float, float] = A4) -> bytes:
    """Sayfa başına verilen metni gömer; `None` sayfa metinsiz kalır (taranmış sayfa)."""
    document = pymupdf.open()
    for text in pages:
        page = document.new_page(width=size[0], height=size[1])
        if text is not None:
            page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def make_half_filled_image_bytes(
    fmt: str = "JPEG", size: tuple[int, int] = (200, 100), *, orientation: int | None = None
) -> bytes:
    """Sol yarısı siyah, sağ yarısı beyaz `fmt` (JPEG/PNG) görüntü.

    `orientation` verilirse EXIF `Orientation` etiketi (0x0112) olarak gömülür — render testleri
    bununla analiz kopyasının yönelimi fiziksel olarak uyguladığını doğrular.
    """
    width, height = size
    image = Image.new("RGB", (width, height), "white")
    ImageDraw.Draw(image).rectangle([0, 0, width // 2 - 1, height - 1], fill="black")
    save_kwargs: dict[str, object] = {}
    if orientation is not None:
        exif = image.getexif()
        exif[0x0112] = orientation
        save_kwargs["exif"] = exif
    buffer = BytesIO()
    image.save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


def make_half_filled_pdf_bytes(width: float = A4[0], height: float = A4[1]) -> bytes:
    """Tek sayfalı PDF: sol yarı siyah dolgulu, sağ yarının üst şeridinde ince çizgiler.

    Render testleri görüntünün kırpılmadığını/döndürülmediğini piksel konumundan doğrular;
    çizgiler JPEG kalitesinin dosya boyuna etkisini görünür kılar.
    """
    document = pymupdf.open()
    page = document.new_page(width=width, height=height)
    page.draw_rect(pymupdf.Rect(0, 0, width / 2, height), color=(0, 0, 0), fill=(0, 0, 0))
    y = 0.0
    while y < height * 0.1:
        page.draw_line(pymupdf.Point(width / 2, y), pymupdf.Point(width, y), width=0.5)
        y += 3
    content = document.tobytes()
    document.close()
    return content


def _zip_with(*entries: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for entry in entries:
            archive.writestr(entry, "sentetik icerik")
    return buffer.getvalue()


def make_docx_bytes() -> bytes:
    """Word (OOXML) içerik imzasını taşıyan en küçük ZIP (K2 — analiz edilmez)."""
    return _zip_with("[Content_Types].xml", "word/document.xml")


def make_xlsx_bytes() -> bytes:
    """Excel (OOXML) içerik imzasını taşıyan en küçük ZIP (K2 — analiz edilmez)."""
    return _zip_with("[Content_Types].xml", "xl/workbook.xml")


def make_legacy_doc_bytes() -> bytes:
    """Eski ikili Word (CFBF/OLE) içerik imzası (K2 — analiz edilmez)."""
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32 + "WordDocument".encode("utf-16-le")


def make_legacy_xls_bytes() -> bytes:
    """Eski ikili Excel (CFBF/OLE) içerik imzası (K2 — analiz edilmez)."""
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32 + "Workbook".encode("utf-16-le")


# --- 09.3.1 kimlikli sentetik belgeler ---------------------------------------------------------

MrzFormatName = Literal["TD1", "TD2", "TD3"]
MRZ_FILLER = "<"
_MRZ_WEIGHTS = (7, 3, 1)
_MRZ_CHARACTERS = re.compile(r"[A-Z0-9<]*")
# §20.2.1 belge numarası ayraçları; MRZ'ye ayraçsız yazılır (`00 0000001` → `000000001`).
_NUMBER_SEPARATORS = re.compile(r"[\s./-]+")
# İsim kelime ayracı: boşluk, tire, kesme işareti MRZ'de tek `<` olur (§20.1.2).
_NAME_SEPARATORS = re.compile(r"[\s'-]+")
_NAME_WORD = re.compile(r"[A-Z]+")
# §20.1.3: (satır sayısı, satır uzunluğu, isim alanı genişliği).
_MRZ_SHAPES: dict[str, tuple[int, int, int]] = {
    "TD1": (3, 30, 30),
    "TD2": (2, 36, 31),
    "TD3": (2, 44, 39),
}


def mrz_check_digit(characters: str) -> str:
    """§20.1.4 kontrol hanesi: `0-9` değeri, `A-Z` 10–35, `<` 0; ağırlık 7, 3, 1; toplam mod 10."""
    total = 0
    for index, char in enumerate(characters):
        if "0" <= char <= "9":
            value = ord(char) - ord("0")
        elif "A" <= char <= "Z":
            value = ord(char) - ord("A") + 10
        elif char == MRZ_FILLER:
            value = 0
        else:
            raise ValueError("MRZ karakteri A-Z, 0-9 veya < olmalı")
        total += value * _MRZ_WEIGHTS[index % 3]
    return str(total % 10)


def _mrz_padded(value: str, width: int) -> str:
    if len(value) > width or not _MRZ_CHARACTERS.fullmatch(value):
        raise ValueError(f"MRZ alanı en çok {width} karakter A-Z, 0-9, < olmalı")
    return value + MRZ_FILLER * (width - len(value))


def _mrz_checked(value: str, width: int) -> str:
    padded = _mrz_padded(value, width)
    return padded + mrz_check_digit(padded)


def _mrz_words(text: str) -> str:
    words = [word for word in _NAME_SEPARATORS.split(text.upper()) if word]
    if not words or not all(_NAME_WORD.fullmatch(word) for word in words):
        raise ValueError("MRZ isim alanı Latin harflerle yazılmış en az bir kelime olmalı")
    return MRZ_FILLER.join(words)


def mrz_name(surname: str, given_names: str | None = None) -> str:
    """İsim alanının dolgusuz içeriği (§20.1.2): kelimeler `<`, soyad ile ad arası `<<`."""
    primary = _mrz_words(surname)
    return primary if not given_names else primary + MRZ_FILLER * 2 + _mrz_words(given_names)


def mrz_document_number(number: str) -> str:
    """Görünen belge numarasının MRZ yazımı: §20.2.1 ayraçları silinir, büyük harf."""
    return _NUMBER_SEPARATORS.sub("", number).upper()


def mrz_date(value: date) -> str:
    """`YYMMDD` (§20.1.6)."""
    return value.strftime("%y%m%d")


def make_mrz_lines(
    fmt: MrzFormatName,
    *,
    document_code: str,
    issuing_state: str,
    surname: str,
    given_names: str | None,
    document_number: str,
    nationality: str,
    date_of_birth: date,
    sex: str,
    expiry_date: date,
    optional_data: str = "",
    optional_data_2: str = "",
) -> tuple[str, ...]:
    """Kontrol haneleri geçerli MRZ satırları (§20.1.3–§20.1.5).

    Alanlar anlamlarıyla birleştirilir: her alan hanesiyle birlikte yazılır, bileşik hane
    kapsanan alanların (haneleriyle birlikte) bitişik birleşiminden hesaplanır — TD3/TD2: belge
    no, doğum, son geçerlilik, isteğe bağlı veri; TD1: satır 1'deki belge no ve isteğe bağlı veri,
    doğum, son geçerlilik, satır 2'deki isteğe bağlı veri. Cinsiyet, uyruk ve isim bileşik haneye
    girmez. `optional_data_2` yalnız TD1'in ikinci satırındaki isteğe bağlı veridir. Sığmayan
    alan kesilmez, `ValueError` olur — sentetik veri alanına sığacak kadar kısa seçilir.
    """
    line_count, width, name_width = _MRZ_SHAPES[fmt]
    if sex not in ("M", "F", MRZ_FILLER):
        raise ValueError("cinsiyet M, F veya < olmalı")
    if fmt != "TD1" and optional_data_2:
        raise ValueError("ikinci isteğe bağlı veri yalnız TD1'de var")
    head = _mrz_padded(document_code, 2) + _mrz_padded(issuing_state, 3)
    name = _mrz_padded(mrz_name(surname, given_names), name_width)
    number = _mrz_checked(mrz_document_number(document_number), 9)
    birth = _mrz_checked(mrz_date(date_of_birth), 6)
    expiry = _mrz_checked(mrz_date(expiry_date), 6)
    state = _mrz_padded(nationality, 3)
    if fmt == "TD3":
        optional = _mrz_checked(optional_data, 14)
        covered = number + birth + expiry + optional
        lines = [head + name, number + state + birth + sex + expiry + optional]
    elif fmt == "TD2":
        optional = _mrz_padded(optional_data, 7)
        covered = number + birth + expiry + optional
        lines = [head + name, number + state + birth + sex + expiry + optional]
    else:
        first, second = _mrz_padded(optional_data, 15), _mrz_padded(optional_data_2, 11)
        covered = number + first + birth + expiry + second
        lines = [head + number + first, birth + sex + expiry + state + second, name]
    lines[1] += mrz_check_digit(covered)
    assert len(lines) == line_count and all(len(line) == width for line in lines)
    return tuple(lines)


@dataclass(frozen=True, slots=True)
class SyntheticPerson:
    """Kurgusal kişi. `surname`/`given_names` belgedeki Latin yazımdır (MRZ'ye de bu girer)."""

    surname: str
    given_names: str
    date_of_birth: date | None = None
    nationality: str | None = None
    sex: str = MRZ_FILLER
    original_script_name: str | None = None
    other_names: str | None = None


# Kayıtlı yanıtlardaki (`tests/fixtures/ai/recordings/`) kurgusal kişilerle aynı değerler.
PERSON_ORNEKOVA = SyntheticPerson(
    "ORNEKOVA", "TEST", date(1990, 1, 1), "RUS", "F", original_script_name="Орнекова Тест"
)
PERSON_TESTOVA_SHCHELKINA = SyntheticPerson(
    "TESTOVA-SHCHELKINA",
    "IULIA",
    date(1992, 3, 15),
    "RUS",
    "F",
    original_script_name="Тестова-Щёлкина Юлья",
)
PERSON_SIDOROV = SyntheticPerson("SIDOROV", "IVAN", date(1985, 5, 5), "RUS", "M")
PERSON_PRUEBA = SyntheticPerson("PRUEBA", "ANA", date(1995, 3, 15))

CATALOG = load_seed_catalog()
# Sayfada yazılı olabilecek kişi/belge alanları, sayfadaki sırasıyla; adlar §8.4 ile aynı.
PAGE_FIELDS = (
    "surname",
    "given_names",
    "date_of_birth",
    "nationality",
    "document_number",
    "expiry_date",
)
_FIELD_LABELS = {
    "surname": "Surname",
    "given_names": "Given names",
    "date_of_birth": "Date of birth",
    "nationality": "Nationality",
    "document_number": "Document No.",
    "expiry_date": "Date of expiry",
}
DRIVING_LICENSE_BACK_NOTES = (
    "Arka yüzde yalnız ehliyet sınıfları tablosu var; zorunlu alanlar ön yüzde."
)
RESIDENCE_CARD_ADDRESS = "Belgrade, Test Street 1"
_document_keys = itertools.count(1)


@dataclass(frozen=True, slots=True)
class SyntheticPage:
    """Sentetik bir belgenin tek sayfası: sayfaya yazılan ve analizcinin okuduğu (§8.4).

    `lines` (etiket, değer) çiftleridir; değeri `None` olan satır sayfada bulanık bir leke olarak
    çizilir (okunamayan alan). `photo` doluysa sayfa yalnız o görüntüdür (tam sayfa, tek gömülü
    görüntü — 02.5.1). `reading` kayıtlı yanıttır (JSON; `page_index` ve
    `continues_previous_page` dosyadaki yerine göre `analysis` ile yazılır); `None` ise sayfa
    boştur ve analize gitmez (02.4.1). Aynı belgenin sayfaları aynı `document_key`'i taşır,
    `part` belgedeki sırasıdır. `photo_check` fotoğraf kontrolünün (11.7.1) kayıtlı yanıtıdır
    (JSON); doluysa sağlayıcı onu bu sayfanın analizinden hemen sonra verir (`batch_responses`).
    `portrait` vesikalığın (boyut, kişi sayısı) tanımıdır: görüntü dosyası hâli aynı tanımdan
    istenen biçimde üretilir (`make_page_image_bytes`).
    """

    title: str = ""
    lines: tuple[tuple[str, str | None], ...] = ()
    extra_lines: tuple[str, ...] = ()
    mrz_lines: tuple[str, ...] = ()
    mrz_legible: bool = True
    photo: bytes | None = None
    reading: str | None = None
    document_key: int | None = None
    part: int = 0
    photo_check: str | None = None
    portrait: tuple[tuple[int, int], int] | None = None

    @property
    def is_blank(self) -> bool:
        return self.reading is None

    def with_photo_check(self, response: Mapping[str, Any] | None) -> SyntheticPage:
        """Fotoğraf kontrolünün kayıtlı yanıtı değişmiş kopya; `None` kontrol isteği beklemez."""
        return replace(self, photo_check=None if response is None else _dump_reading(response))

    def analysis(
        self, page_index: int = 0, *, continues_previous_page: bool = False
    ) -> dict[str, Any]:
        """Bu sayfanın kayıtlı yanıtı (§8.4), her çağrıda yeni bir sözlük."""
        if self.reading is None:
            raise ValueError("boş sayfa analize gitmez (02.4.1); kayıtlı yanıtı yok")
        data: dict[str, Any] = json.loads(self.reading)
        data["page_index"] = page_index
        data["continues_previous_page"] = continues_previous_page
        return data

    def with_notes(self, notes: str | None) -> SyntheticPage:
        """Analizcinin notu değişmiş kopya (sayfaya yazılan değişmez)."""
        data = self.analysis()
        data["notes"] = notes
        return replace(self, reading=_dump_reading(data))


def _dump_reading(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _page_text(value: str | date) -> str:
    return value.strftime("%d.%m.%Y") if isinstance(value, date) else value


def _reading_text(value: str | date) -> str:
    return value.isoformat() if isinstance(value, date) else value


def _required_fields(slug: str | None, required_fields: Sequence[str] | None) -> tuple[str, ...]:
    if required_fields is not None:
        return tuple(required_fields)
    if slug is None:
        return ()
    entry = CATALOG.get(slug)
    if entry is None:
        raise ValueError(f"'{slug}' tohum katalogda yok; required_fields verilmeli")
    return tuple(entry.required_fields)


def document_page(
    document_type_slug: str | None,
    *,
    title: str,
    person: SyntheticPerson | None = None,
    document_number: str | None = None,
    expiry_date: date | None = None,
    shows: Iterable[str] = (),
    blurred: Iterable[str] = (),
    side: str = "single",
    language: str | None = None,
    script: str | None = None,
    candidate_type_name: str | None = None,
    address: str | None = None,
    mrz_lines: Sequence[str] | None = None,
    mrz_legible: bool = True,
    extra_lines: Sequence[str] = (),
    notes: str | None = None,
    required_fields: Sequence[str] | None = None,
) -> SyntheticPage:
    """Kişi/belge alanları yazılı tek sayfa ve onun kayıtlı yanıtı.

    `shows` sayfada yazılı alanlardır (`PAGE_FIELDS`); `blurred` bunlardan okunamayanlardır —
    sayfada leke olarak çizilir, yanıtta değeri `null`, okuması `legible: false`'tur (K1).
    Yazılı olmayan alan da yanıtta okunamamış görünür: türün zorunlu alanı o yüzde yoksa
    analizci onu okuyamaz (ön/arka yüzlü kart). `fields` türün zorunlu alanlarıdır (tohum
    kataloğundan; `required_fields` ile değiştirilebilir). Orijinal yazım soyadla, ek isimler
    verilen adlarla birlikte okunur. `mrz_legible=False` MRZ'yi lekeler, yanıtta `mrz_lines` null.
    """
    shown = set(shows)
    unknown = shown - set(PAGE_FIELDS)
    if unknown:
        raise ValueError(f"bilinmeyen sayfa alanı: {sorted(unknown)}")
    smudged = set(blurred)
    if not smudged <= shown:
        raise ValueError("bulanık alan sayfada yazılı olmalı")
    values: dict[str, str | date | None] = {
        "surname": None if person is None else person.surname,
        "given_names": None if person is None else person.given_names,
        "date_of_birth": None if person is None else person.date_of_birth,
        "nationality": None if person is None else person.nationality,
        "document_number": document_number,
        "expiry_date": expiry_date,
    }
    lines: list[tuple[str, str | None]] = []
    for name in PAGE_FIELDS:
        if name not in shown:
            continue
        value = values[name]
        if value is None:
            raise ValueError(f"{name} sayfada yazılı ama değeri yok")
        lines.append((_FIELD_LABELS[name], None if name in smudged else _page_text(value)))
        if person is not None and name == "surname" and person.original_script_name:
            lines.append(("Name", None if name in smudged else person.original_script_name))
        if person is not None and name == "given_names" and person.other_names:
            lines.append(("Other names", None if name in smudged else person.other_names))
    if address is not None:
        lines.append(("Address", address))

    def read(name: str) -> str | None:
        value = values.get(name)
        if name not in shown or name in smudged or value is None:
            return None
        return _reading_text(value)

    other_names = person.other_names if person is not None and read("given_names") else None
    original = person.original_script_name if person is not None and read("surname") else None
    reading = {
        "page_index": 0,
        "is_blank": False,
        "is_readable": True,
        "language": language,
        "script": script,
        "document_type_slug": document_type_slug,
        "candidate_type_name": candidate_type_name,
        "side": side,
        "continues_previous_page": False,
        "person": {
            "surname": read("surname"),
            "given_names": read("given_names"),
            "other_names": other_names,
            "original_script_name": original,
            "date_of_birth": read("date_of_birth"),
            "nationality": read("nationality"),
            "document_number": read("document_number"),
            "mrz_lines": list(mrz_lines) if mrz_lines and mrz_legible else None,
            "contact": {"phone": None, "email": None, "address": address},
        },
        "fields": {
            name: {"value": read(name), "legible": read(name) is not None}
            for name in _required_fields(document_type_slug, required_fields)
        },
        "notes": notes,
    }
    return SyntheticPage(
        title=title,
        lines=tuple(lines),
        extra_lines=tuple(extra_lines),
        mrz_lines=tuple(mrz_lines or ()),
        mrz_legible=mrz_legible,
        reading=_dump_reading(reading),
    )


def same_document(*pages: SyntheticPage) -> tuple[SyntheticPage, ...]:
    """Sayfaları tek belgenin sırayla parçaları yapar (ön/arka yüz)."""
    key = next(_document_keys)
    return tuple(replace(page, document_key=key, part=part) for part, page in enumerate(pages))


# Pasaport türü → (veren devlet, dil, alfabe, görünür başlık).
_PASSPORTS: dict[str, tuple[str, str, str, str]] = {
    "russian_passport": ("RUS", "ru", "cyrillic", "ПАСПОРТ / PASSPORT"),
    "serbian_passport": ("SRB", "sr", "cyrillic", "ПАСОШ / PASOŠ / PASSPORT"),
    "turkish_passport": ("TUR", "tr", "latin", "PASAPORT / PASSPORT"),
}


def passport_page(
    person: SyntheticPerson,
    *,
    document_number: str,
    expiry_date: date,
    slug: str = "russian_passport",
    blurred: Iterable[str] = (),
    mrz_legible: bool = True,
    mrz_lines: Sequence[str] | None = None,
    notes: str | None = None,
) -> SyntheticPage:
    """Tek sayfalı pasaport kimlik sayfası; altta kontrol haneleri geçerli TD3 MRZ.

    MRZ görünen değerlerden üretilir, bu yüzden görünen metinle çelişmez (05.3.3). `mrz_lines`
    verilirse (bozuk hane denemesi gibi) o satırlar olduğu gibi yazılır.
    """
    issuing_state, language, script, title = _PASSPORTS[slug]
    if person.date_of_birth is None or person.nationality is None:
        raise ValueError("pasaport kişisi doğum tarihi ve uyruk taşımalı")
    if mrz_lines is None:
        mrz_lines = make_mrz_lines(
            "TD3",
            document_code="P",
            issuing_state=issuing_state,
            surname=person.surname,
            given_names=person.given_names,
            document_number=document_number,
            nationality=person.nationality,
            date_of_birth=person.date_of_birth,
            sex=person.sex,
            expiry_date=expiry_date,
        )
    return document_page(
        slug,
        title=title,
        person=person,
        document_number=document_number,
        expiry_date=expiry_date,
        shows=PAGE_FIELDS,
        blurred=blurred,
        language=language,
        script=script,
        mrz_lines=mrz_lines,
        mrz_legible=mrz_legible,
        notes=notes,
    )


def driving_license_pages(
    person: SyntheticPerson,
    *,
    document_number: str,
    expiry_date: date,
    blurred: Iterable[str] = (),
    back_notes: str | None = DRIVING_LICENSE_BACK_NOTES,
) -> tuple[SyntheticPage, SyntheticPage]:
    """Sırbistan ehliyeti: ön yüzde zorunlu alanların hepsi, arka yüzde yalnız sınıf tablosu."""
    title = "VOZAČKA DOZVOLA / DRIVING LICENCE"
    front = document_page(
        "serbian_driving_license",
        title=title,
        person=person,
        document_number=document_number,
        expiry_date=expiry_date,
        shows=("surname", "given_names", "date_of_birth", "document_number", "expiry_date"),
        blurred=blurred,
        side="front",
        language="sr",
        script="latin",
    )
    back = document_page(
        "serbian_driving_license",
        title=title,
        side="back",
        language="sr",
        script="latin",
        extra_lines=("Kategorije / Categories: AM, B",),
        notes=back_notes,
    )
    front, back = same_document(front, back)
    return front, back


MULTIPLE_DOCUMENTS_NOTE = "Sayfada birden fazla belge var: iki ayrı sürücü belgesi."


def driving_license_combined_page(
    person: SyntheticPerson,
    *,
    document_number: str,
    expiry_date: date,
    blurred: Iterable[str] = (),
) -> SyntheticPage:
    """Sırbistan ehliyetinin iki yüzü tek sayfada (04.1.2, `front_and_back`): üstte ön yüzün
    alanları, altta arka yüzün sınıf tablosu. Analizci iki yüzü birlikte okur."""
    return document_page(
        "serbian_driving_license",
        title="VOZAČKA DOZVOLA / DRIVING LICENCE",
        person=person,
        document_number=document_number,
        expiry_date=expiry_date,
        shows=("surname", "given_names", "date_of_birth", "document_number", "expiry_date"),
        blurred=blurred,
        side="front_and_back",
        language="sr",
        script="latin",
        extra_lines=("Kategorije / Categories: AM, B",),
    )


def two_driving_licenses_page(
    first: SyntheticPerson, second: SyntheticPerson, *, numbers: tuple[str, str]
) -> SyntheticPage:
    """Aynı sayfada iki farklı kişinin ehliyeti: analizci türü tanır ama yüzü `unknown` okur,
    kişiyi ve alanları seçmez, notuna "birden fazla belge" yazar (04.1.2, §8.4)."""
    lines = [
        f"{person.surname} {person.given_names} · Document No. {number}"
        for person, number in zip((first, second), numbers, strict=True)
    ]
    return document_page(
        "serbian_driving_license",
        title="VOZAČKA DOZVOLA / DRIVING LICENCE (2)",
        side="unknown",
        language="sr",
        script="latin",
        extra_lines=lines,
        notes=MULTIPLE_DOCUMENTS_NOTE,
    )


def residence_card_pages(
    person: SyntheticPerson,
    *,
    document_number: str,
    expiry_date: date,
    address: str = RESIDENCE_CARD_ADDRESS,
    with_mrz: bool = False,
    blurred: Iterable[str] = (),
) -> tuple[SyntheticPage, SyntheticPage]:
    """Sırbistan oturma izni: ön yüzde kimlik, arka yüzde son geçerlilik ve adres.

    `with_mrz` arka yüze kontrol haneleri geçerli TD1 MRZ (belge kodu `IR`, veren devlet `SRB`)
    ekler; MRZ'yi okuyan analizci onu arka yüzün yanıtına da yazar.
    """
    title = "DOZVOLA ZA BORAVAK / RESIDENCE PERMIT"
    front = document_page(
        "serbian_residence_card",
        title=title,
        person=person,
        document_number=document_number,
        shows=("surname", "given_names", "date_of_birth", "nationality", "document_number"),
        blurred=blurred,
        side="front",
        language="sr",
        script="latin",
    )
    mrz_lines: tuple[str, ...] | None = None
    if with_mrz:
        # Ön yüz doğum tarihini ve uyruğu yazar; değeri olmayan kişi yukarıda reddedildi.
        assert person.date_of_birth is not None and person.nationality is not None
        mrz_lines = make_mrz_lines(
            "TD1",
            document_code="IR",
            issuing_state="SRB",
            surname=person.surname,
            given_names=person.given_names,
            document_number=document_number,
            nationality=person.nationality,
            date_of_birth=person.date_of_birth,
            sex=person.sex,
            expiry_date=expiry_date,
        )
    back = document_page(
        "serbian_residence_card",
        title=title,
        expiry_date=expiry_date,
        shows=("expiry_date",),
        side="back",
        language="sr",
        script="latin",
        address=address,
        mrz_lines=mrz_lines,
    )
    front, back = same_document(front, back)
    return front, back


def work_permit_page(
    person: SyntheticPerson,
    *,
    document_number: str,
    expiry_date: date,
    blurred: Iterable[str] = (),
) -> SyntheticPage:
    """Tek sayfalı çalışma izni: ad, soyad, uyruk, izin numarası, son geçerlilik."""
    return document_page(
        "work_permit",
        title="RADNA DOZVOLA / WORK PERMIT",
        person=person,
        document_number=document_number,
        expiry_date=expiry_date,
        shows=("surname", "given_names", "nationality", "document_number", "expiry_date"),
        blurred=blurred,
        language="sr",
        script="latin",
    )


# S19 (05.6.2, §20.2.4): numarasız tür — zorunlu alanları ad, soyad, doğum tarihi. Tohum katalogda
# yoktur; testler `employment_contract_entry()` ile kataloğa ekler.
EMPLOYMENT_CONTRACT = "employment_contract"
EMPLOYMENT_CONTRACT_FIELDS = ("surname", "given_names", "date_of_birth")


def employment_contract_entry(**changes: Any) -> CatalogEntry:
    """S19'un numarasız türü; çalışma izninin kaydından türetilir (tek sayfa, PDF)."""
    permit = CATALOG.get("work_permit")
    assert permit is not None
    return permit.model_copy(
        update={
            "slug": EMPLOYMENT_CONTRACT,
            "name": "Employment Contract",
            "file_label": "Employment Contract",
            "description": "İşverenle imzalanmış iş sözleşmesi.",
            "required_fields": EMPLOYMENT_CONTRACT_FIELDS,
            "prompt_description": "İş sözleşmesi; çalışanın soyadı, adı ve doğum tarihi yazılıdır.",
            **changes,
        }
    )


def employment_contract_page(
    person: SyntheticPerson, *, blurred: Iterable[str] = ()
) -> SyntheticPage:
    """Tek sayfalı iş sözleşmesi: ad, soyad, doğum tarihi; belge numarası ve MRZ yok (S19)."""
    return document_page(
        EMPLOYMENT_CONTRACT,
        title="UGOVOR O RADU / EMPLOYMENT CONTRACT",
        person=person,
        shows=("surname", "given_names", "date_of_birth"),
        blurred=blurred,
        language="sr",
        script="latin",
        required_fields=EMPLOYMENT_CONTRACT_FIELDS,
    )


def unknown_document_page(
    person: SyntheticPerson,
    *,
    candidate_type_name: str,
    title: str,
    document_number: str | None = None,
    language: str = "es",
    script: str = "latin",
    notes: str | None = None,
) -> SyntheticPage:
    """Katalogda olmayan tür (ör. Peru diploması): slug `null`, aday tür adı dolu, `fields` boş."""
    shows = ["surname", "given_names"]
    if person.date_of_birth is not None:
        shows.append("date_of_birth")
    if document_number is not None:
        shows.append("document_number")
    return document_page(
        None,
        title=title,
        person=person,
        document_number=document_number,
        shows=shows,
        language=language,
        script=script,
        candidate_type_name=candidate_type_name,
        notes=notes,
    )


# Vesikalığın varsayılan boyutu: tohum kataloğunun asgari çözünürlüğünü (400×400, 11.6.1) karşılar.
PORTRAIT_SIZE = (480, 600)

# Tohum kataloğunda (`photo_rules: null`, varsayılan kurallar) yapay zekâya sorulan fotoğraf
# kuralları (11.7.1): açık kurallar, katalog sırasıyla; asgari çözünürlük sorulmaz, ölçülür.
ASKED_PHOTO_RULES = tuple(
    rule.id for rule in enabled_photo_rules(None) if rule.id != RESOLUTION_RULE
)
_PHOTO_NOTES = {
    "face_visible": "Yüz görünmüyor.",
    "single_person": "Fotoğrafta iki kişi var.",
    "neutral_expression": "Yüz ifadesi nötr değil.",
    "plain_background": "Arka plan sade değil.",
    "no_sunglasses": "Güneş gözlüğü var.",
    "no_head_covering": "Baş örtüsü var.",
}


def make_portrait_image_bytes(
    fmt: str = "JPEG", size: tuple[int, int] = PORTRAIT_SIZE, *, people: int = 1
) -> bytes:
    """Vesikalık yerine geçen siluet: düz fon üzerinde baş ve omuz elipsleri (yüz yok).

    `people` yan yana çizilen siluet sayısıdır ("iki kişi" fotoğrafı, 11.7.1).
    """
    width, height = size
    image = Image.new("RGB", size, (214, 226, 238))
    draw = ImageDraw.Draw(image)
    step = width / people
    for number in range(people):
        left, scale = number * step, step
        draw.ellipse(
            [left + scale * 0.18, height * 0.62, left + scale * 0.82, height * 1.3],
            fill=(88, 96, 110),
        )
        draw.ellipse(
            [left + scale * 0.32, height * 0.16, left + scale * 0.68, height * 0.6],
            fill=(172, 160, 148),
        )
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def photo_check_response(
    results: Mapping[str, str] | None = None, *, rules: Sequence[str] = ASKED_PHOTO_RULES
) -> dict[str, Any]:
    """Fotoğraf kontrolünün (11.7.1) kayıtlı yanıtı: sorulan her kural için bir satır, sırayla.

    `results` kural → `pass`/`fail`/`unsure`; verilmeyen kural `pass`tır. `fail` ve `unsure`
    satırı kısa bir not taşır.
    """
    given = dict(results or {})
    unknown = sorted(set(given) - set(rules))
    if unknown:
        raise ValueError(f"sorulmayan kural: {', '.join(unknown)}")
    lines = []
    for rule in rules:
        result = given.get(rule, "pass")
        note = None if result == "pass" else _PHOTO_NOTES.get(rule, "Sentetik test notu.")
        lines.append({"rule": rule, "result": result, "note": note})
    return {"rules": lines}


def profile_picture_page(
    *,
    size: tuple[int, int] = PORTRAIT_SIZE,
    people: int = 1,
    photo_check: Mapping[str, Any] | None = None,
) -> SyntheticPage:
    """Yalnız vesikalık görüntüsünden oluşan sayfa; kişi ve zorunlu alan taşımaz.

    `photo_check` fotoğraf kontrolünün kayıtlı yanıtıdır; verilmezse sorulan her kural `pass`
    (`photo_check_response()`). Kontrol isteği beklenmiyorsa `with_photo_check(None)`.
    """
    response = photo_check_response() if photo_check is None else photo_check
    return replace(
        document_page("profile_picture", title=""),
        photo=make_portrait_image_bytes(size=size, people=people),
        portrait=(size, people),
    ).with_photo_check(response)


def blank_page() -> SyntheticPage:
    """Fiziksel olarak boş sayfa: metin, görüntü ve çizim yok (02.4.1)."""
    return SyntheticPage()


def file_analyses(pages: Sequence[SyntheticPage]) -> list[dict[str, Any]]:
    """Bir dosyanın analize giden sayfalarının kayıtlı yanıtları, sayfa sırasıyla.

    Boş sayfa analize gitmez (02.4.1). `continues_previous_page` yalnız bir önceki analiz edilen
    sayfa aynı belgenin bir önceki parçasıysa doğrudur — araya başka belge girmişse değildir.
    """
    analyses: list[dict[str, Any]] = []
    previous: SyntheticPage | None = None
    for index, page in enumerate(pages):
        if page.is_blank:
            continue
        continues = (
            previous is not None
            and page.document_key is not None
            and previous.document_key == page.document_key
            and previous.part == page.part - 1
        )
        analyses.append(page.analysis(index, continues_previous_page=continues))
        previous = page
    return analyses


def batch_analyses(*files: Sequence[SyntheticPage]) -> list[dict[str, Any]]:
    """Partinin sayfa analizi yanıtları, çağrılma sırasıyla: dosya sırası, sonra sayfa.

    Analiz edilmeyen dosya (Word/Excel eki, tekrar yükleme) boş dizi olarak verilir.
    """
    return [analysis for pages in files for analysis in file_analyses(pages)]


def batch_responses(*files: Sequence[SyntheticPage]) -> list[dict[str, Any]]:
    """Sağlayıcının bütün kayıtlı yanıtları, çağrılma sırasıyla: sayfa analizleri
    (`batch_analyses`) ve fotoğraf kontrolü yanıtı olan sayfada analizin hemen ardından o yanıt
    (11.7.1)."""
    responses: list[dict[str, Any]] = []
    for pages in files:
        analyzed = [page for page in pages if not page.is_blank]
        for page, analysis in zip(analyzed, file_analyses(pages), strict=True):
            responses.append(analysis)
            if page.photo_check is not None:
                responses.append(json.loads(page.photo_check))
    return responses


def write_recordings(directory: Path, analyses: Sequence[Mapping[str, Any]]) -> Path:
    """Yanıtları `RecordingProvider`'ın okuduğu biçimde yazar: `0000.json`, `0001.json` …

    Ad sıfırla doldurulur ki ad sırası çağrı sırası olsun (`10.json` `2.json`'dan önce
    gelmesin). Dizinde kayıt varsa üzerine yazılmaz.
    """
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.glob("*.json")):
        raise FileExistsError(f"'{directory}' altında zaten kayıt var")
    for index, analysis in enumerate(analyses):
        text = json.dumps(analysis, ensure_ascii=False, indent=2) + "\n"
        (directory / f"{index:04d}.json").write_text(text, encoding="utf-8")
    return directory


def recorded_provider(directory: Path, *files: Sequence[SyntheticPage]) -> RecordingProvider:
    """Partinin kayıtlı yanıtlarını (`batch_responses`) `directory`'ye yazar ve onları okuyan
    sağlayıcıyı döner."""
    return RecordingProvider.from_directory(write_recordings(directory, batch_responses(*files)))


_MARGIN = 56.0
_LINE_HEIGHT = 20.0
_TITLE_SIZE = 16.0
_TEXT_SIZE = 11.0
_MRZ_SIZE = 10.0
_SMUDGE_WIDTH = 150.0
_SMUDGE = (0.55, 0.55, 0.55)


def _draw_page(document: pymupdf.Document, page: SyntheticPage, size: tuple[float, float]) -> None:
    pdf_page = document.new_page(width=size[0], height=size[1])
    if page.photo is not None:
        pdf_page.insert_image(pdf_page.rect, stream=page.photo, keep_proportion=False)
        return
    if page.is_blank:
        return
    sans, mono = pymupdf.Font("helv"), pymupdf.Font("cour")
    writer = pymupdf.TextWriter(pdf_page.rect)
    smudges: list[pymupdf.Rect] = []
    y = _MARGIN + _TITLE_SIZE
    if page.title:
        writer.append((_MARGIN, y), page.title, font=sans, fontsize=_TITLE_SIZE)
    y += 2 * _LINE_HEIGHT
    for label, value in page.lines:
        _, end = writer.append((_MARGIN, y), f"{label}: ", font=sans, fontsize=_TEXT_SIZE)
        if value is None:
            smudges.append(pymupdf.Rect(end.x, y - _TEXT_SIZE, end.x + _SMUDGE_WIDTH, y + 3))
        else:
            writer.append(end, value, font=sans, fontsize=_TEXT_SIZE)
        y += _LINE_HEIGHT
    for line in page.extra_lines:
        writer.append((_MARGIN, y), line, font=sans, fontsize=_TEXT_SIZE)
        y += _LINE_HEIGHT
    top = size[1] - _MARGIN - _LINE_HEIGHT * len(page.mrz_lines)
    for number, line in enumerate(page.mrz_lines, start=1):
        baseline = top + number * _LINE_HEIGHT
        if page.mrz_legible:
            writer.append((_MARGIN, baseline), line, font=mono, fontsize=_MRZ_SIZE)
        else:
            right = _MARGIN + mono.text_length(line, fontsize=_MRZ_SIZE)
            smudges.append(pymupdf.Rect(_MARGIN, baseline - _MRZ_SIZE, right, baseline + 3))
    writer.write_text(pdf_page)
    for rect in smudges:
        pdf_page.draw_rect(rect, color=None, fill=_SMUDGE)


def make_document_pdf_bytes(
    pages: Sequence[SyntheticPage], size: tuple[float, float] = A4
) -> bytes:
    """Sayfaları sırayla tek PDF'e çizer: metin katmanı gerçek metindir (02.2.1), MRZ eş aralıklı.

    Yazıtipleri alt kümelenir; PDF kimliği ve tarihi yazılmaz, aynı sayfalar aynı baytları verir.
    """
    document = pymupdf.open()
    for page in pages:
        _draw_page(document, page, size)
    document.subset_fonts()
    content = document.tobytes(garbage=3, deflate=True, no_new_id=True)
    document.close()
    return content


def make_page_image_bytes(page: SyntheticPage, fmt: str = "JPEG", *, dpi: int = 96) -> bytes:
    """Sayfanın tek görüntü dosyası hâli (telefonla çekilmiş ya da taranmış JPEG/PNG).

    Vesikalık sayfası fotoğrafın kendisidir; diğer sayfalar PDF çiziminden `dpi` ile render edilir.
    """
    if fmt not in ("JPEG", "PNG"):
        raise ValueError("görüntü biçimi JPEG veya PNG olmalı")
    if page.photo is not None:
        size, people = page.portrait or (PORTRAIT_SIZE, 1)
        return make_portrait_image_bytes(fmt, size, people=people)
    with pymupdf.open(stream=make_document_pdf_bytes([page]), filetype="pdf") as document:
        pixmap = document[0].get_pixmap(dpi=dpi)
    return pixmap.tobytes("jpeg" if fmt == "JPEG" else "png")
