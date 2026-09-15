"""MRZ ayrıştırma, kontrol hanesi doğrulaması ve MRZ önceliği — PRD 05.3.1, 05.3.2, 05.3.3 (§20.1).

MRZ (ICAO Doc 9303 makine okunur bölgesi) görünen metinden daha güvenilirdir: kontrol haneleri
okuma hatasını sessizce geçirmez. Kişi eşleştirmesi bu yüzden önce MRZ'yi okur (K6).

**Ayrıştırma (`parse_mrz`, 05.3.1).** Biçim yalnız satır sayısı ve satır uzunluğundan belirlenir:
TD1 3 × 30, TD2 2 × 36, TD3 2 × 44; her satır aynı uzunlukta olmalıdır (§20.1.1). Hiçbirine uymayan
satırlar MRZ değildir (`None`, hata değil). Uyan satırlarda ASCII küçük harf büyüğe çevrilir;
`A-Z`, `0-9`, `<` dışında karakter kalırsa MRZ geçersizdir (`InvalidMrzError`, §20.1.2). Alanlar
§20.1.3'teki konumlardan okunur. İsim alanında ilk `<<` soyadını verilen adlardan ayırır, tek `<`
kelime ayracıdır (`VASILIEV<<DMITRY<IVANOVICH` → `VASILIEV` / `DMITRY IVANOVICH`); `<<` yoksa bütün
alan soyadıdır.

**Kontrol haneleri (05.3.2).** Tek algoritma (§20.1.4): `0-9` kendi değeri, `A-Z` 10–35, `<` 0;
ağırlıklar soldan 7, 3, 1 tekrarı; toplam mod 10. Bileşik hane §20.1.5'in bitişik olmayan
aralıklarının birleşiminden hesaplanır. Sonuç §20.1.7'dir:

- Alanın hanesi tutmuyorsa yalnız **o alan** okunamadı sayılır (`illegible_fields`, değeri `None`);
  MRZ'nin geri kalanı kullanılır. Tümüyle dolgu olan isteğe bağlı verinin hanesi `<` veya `0`dır.
- Bileşik hane tutmuyorsa alanlar kullanılır ama MRZ bütün olarak şüphelidir (`composite_valid`):
  belge numarası temiz sayılmaz (§20.2.3).
- Tarihler `YYMMDD` (§20.1.6): son geçerlilik `20YY`; doğum önce `20YY`, gelecekte kalırsa `19YY`.
  Takvimde geçerli olmayan tarih alanı okunamadı yapar, MRZ'yi geçersiz yapmaz. Aynı ölçü değeri
  biçimce kullanılamayan diğer alanlara da uygulanır: rakam taşıyan isim alanı, 1–3 harf olmayan
  uyruk, boş belge numarası (bkz. PLAN.md C25).

**MRZ önceliği (`apply_mrz_priority`, 05.3.3).** Sayfa analizinde (§8.4) MRZ'nin taşıdığı alanlar
(`surname`, `given_names`, `document_number`, `nationality`, `date_of_birth`, `expiry_date`) iki
yerde okunur: `person` ve türün `fields` okumaları. MRZ'nin kullanılabilir değeri görünen okumayla
karşılaştırılır:

- Görünen okuma MRZ'yle aynı anahtara iniyorsa olduğu gibi kalır (`00 0000001` = `000000001`):
  belge numarası §20.2.1 normalizasyonuyla, isimler `normalize_name`'le (verilen adlar, MRZ baba
  adını da yazıyorsa `given_names` + `other_names` ile), tarihler ISO biçimiyle, uyruk birebir.
- Çelişirse **MRZ kazanır**: değer iki yere de MRZ'den yazılır ve çelişen alanın adı `notes`'a
  eklenir. Bu doğrulama hatası değil, bilgi notudur.
- Görünen okuma yoksa (`null`, `legible: false`) MRZ değeri yazılır — MRZ önce okunur (K6).
- MRZ'de okunamadı sayılan alan görünen okuma okunaklı olsa bile `legible: false` olur (§20.1.7).

Notlar yalnız alan adı taşır, kişisel değer taşımaz (CONVENTIONS §6); var olan not korunur, aynı
cümle ikinci kez eklenmez. Sayfa boş ya da okunamaz diyorsa MRZ okumasına güvenilmez (C21). Modül
saf işlevdir: veritabanına ve olay loguna yazmaz.
"""

from __future__ import annotations

import enum
import re
import string
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.ai.schemas import PageAnalysis
from app.matching.names import EmptyNameError, normalize_name

FILLER = "<"
OPTIONAL_DATA = "optional_data"
COMPOSITE = "composite"

# MRZ'nin taşıdığı sayfa alanları; §8.4 `person` ve katalog `required_fields` adlarıyla aynı.
MRZ_FIELDS = (
    "surname",
    "given_names",
    "document_number",
    "nationality",
    "date_of_birth",
    "expiry_date",
)
_PERSON_FIELDS = frozenset(MRZ_FIELDS) - {"expiry_date"}

_ALLOWED = re.compile(r"[A-Z0-9<]+")
_UPPERCASE = str.maketrans(string.ascii_lowercase, string.ascii_uppercase)
_WEIGHTS = (7, 3, 1)
_YYMMDD = re.compile(r"[0-9]{6}")
_NATIONALITY = re.compile(r"[A-Z]{1,3}")
# §20.2.1 belge numarası normalizasyonu: boşluk, tire, nokta, eğik çizgi silinir.
_NUMBER_SEPARATORS = re.compile(r"[\s./-]+")

_UNRECOGNIZED_NOTE = "MRZ satırları TD1, TD2 veya TD3 biçimine uymuyor; MRZ yok sayıldı."
_INVALID_NOTE = "MRZ satırlarında izin verilmeyen karakter var; MRZ geçersiz sayıldı."
_COMPOSITE_NOTE = "MRZ bileşik kontrol hanesi tutmuyor; MRZ bütün olarak şüpheli."


class MrzFormat(enum.StrEnum):
    """ICAO Doc 9303 MRZ biçimi (§20.1.1)."""

    TD1 = "TD1"
    TD2 = "TD2"
    TD3 = "TD3"


class InvalidMrzError(ValueError):
    """Biçimi tanınan MRZ'de izin verilmeyen karakter kaldı (§20.1.2); mesajda değer yok."""


class MrzStatus(enum.StrEnum):
    """Sayfanın MRZ okumasının `apply_mrz_priority`'deki durumu."""

    ABSENT = "absent"  # sayfada MRZ satırı yok
    UNRECOGNIZED = "unrecognized"  # satırlar hiçbir biçime uymuyor, MRZ yok sayıldı (§20.1.1)
    INVALID = "invalid"  # izin verilmeyen karakter, MRZ kullanılmadı (§20.1.2)
    UNTRUSTED = "untrusted"  # sayfa kendini boş/okunamaz veriyor, MRZ kullanılmadı
    READ = "read"  # MRZ ayrıştırıldı ve öncelik uygulandı


@dataclass(frozen=True, slots=True)
class _Span:
    line: int  # 1 tabanlı satır
    start: int  # 1 tabanlı konum, dahil
    end: int  # dahil

    def read(self, lines: Sequence[str]) -> str:
        return lines[self.line - 1][self.start - 1 : self.end]


def _at(line: int, start: int, end: int | None = None) -> _Span:
    return _Span(line, start, start if end is None else end)


@dataclass(frozen=True, slots=True)
class _Layout:
    document_code: _Span
    issuing_state: _Span
    name: _Span
    document_number: _Span
    document_number_check: _Span
    nationality: _Span
    date_of_birth: _Span
    date_of_birth_check: _Span
    sex: _Span
    expiry_date: _Span
    expiry_date_check: _Span
    optional_data: tuple[_Span, ...]
    optional_data_check: _Span | None
    composite: tuple[_Span, ...]
    composite_check: _Span


# §20.1.3 alan yerleşimi ve §20.1.5 bileşik hane aralıkları, tablodaki konumlarla birebir.
_LAYOUTS = {
    MrzFormat.TD1: _Layout(
        document_code=_at(1, 1, 2),
        issuing_state=_at(1, 3, 5),
        document_number=_at(1, 6, 14),
        document_number_check=_at(1, 15),
        date_of_birth=_at(2, 1, 6),
        date_of_birth_check=_at(2, 7),
        sex=_at(2, 8),
        expiry_date=_at(2, 9, 14),
        expiry_date_check=_at(2, 15),
        nationality=_at(2, 16, 18),
        optional_data=(_at(1, 16, 30), _at(2, 19, 29)),
        optional_data_check=None,
        composite=(_at(1, 6, 30), _at(2, 1, 7), _at(2, 9, 15), _at(2, 19, 29)),
        composite_check=_at(2, 30),
        name=_at(3, 1, 30),
    ),
    MrzFormat.TD2: _Layout(
        document_code=_at(1, 1, 2),
        issuing_state=_at(1, 3, 5),
        name=_at(1, 6, 36),
        document_number=_at(2, 1, 9),
        document_number_check=_at(2, 10),
        nationality=_at(2, 11, 13),
        date_of_birth=_at(2, 14, 19),
        date_of_birth_check=_at(2, 20),
        sex=_at(2, 21),
        expiry_date=_at(2, 22, 27),
        expiry_date_check=_at(2, 28),
        optional_data=(_at(2, 29, 35),),
        optional_data_check=None,
        composite=(_at(2, 1, 10), _at(2, 14, 20), _at(2, 22, 35)),
        composite_check=_at(2, 36),
    ),
    MrzFormat.TD3: _Layout(
        document_code=_at(1, 1, 2),
        issuing_state=_at(1, 3, 5),
        name=_at(1, 6, 44),
        document_number=_at(2, 1, 9),
        document_number_check=_at(2, 10),
        nationality=_at(2, 11, 13),
        date_of_birth=_at(2, 14, 19),
        date_of_birth_check=_at(2, 20),
        sex=_at(2, 21),
        expiry_date=_at(2, 22, 27),
        expiry_date_check=_at(2, 28),
        optional_data=(_at(2, 29, 42),),
        optional_data_check=_at(2, 43),
        composite=(_at(2, 1, 10), _at(2, 14, 20), _at(2, 22, 43)),
        composite_check=_at(2, 44),
    ),
}
_SHAPES = {(3, 30): MrzFormat.TD1, (2, 36): MrzFormat.TD2, (2, 44): MrzFormat.TD3}


@dataclass(frozen=True, slots=True)
class Mrz:
    """Ayrıştırılmış MRZ (05.3.1, 05.3.2).

    Değerlerden dolgu (`<`) atılmıştır. Okunamadı sayılan alanın (`illegible_fields`: hanesi
    tutmayan ya da değeri biçimce kullanılamayan) değeri `None`'dır; boş isim parçası da `None`'dır
    ama okunamadı sayılmaz. `failed_checks` hanesi tutmayanları MRZ sırasıyla taşır:
    `document_number`, `date_of_birth`, `expiry_date`, `optional_data`, `composite`.
    """

    format: MrzFormat
    document_code: str
    issuing_state: str
    surname: str | None
    given_names: str | None
    document_number: str | None
    nationality: str | None
    date_of_birth: date | None
    sex: str | None
    expiry_date: date | None
    optional_data: tuple[str, ...] | None
    failed_checks: tuple[str, ...]
    illegible_fields: tuple[str, ...]

    @property
    def composite_valid(self) -> bool:
        """Bileşik hane tutuyor; tutmuyorsa MRZ bütün olarak şüphelidir (§20.1.7)."""
        return COMPOSITE not in self.failed_checks


@dataclass(frozen=True, slots=True)
class MrzResolution:
    """`apply_mrz_priority` sonucu: MRZ önceliği uygulanmış sayfa analizi ve MRZ'nin durumu."""

    analysis: PageAnalysis
    status: MrzStatus
    mrz: Mrz | None = None
    conflicts: tuple[str, ...] = ()

    @property
    def allows_clean_document_number(self) -> bool:
        """§20.2.3'ün üçüncü koşulu: MRZ belge numarasının temiz sayılmasına engel değil.

        MRZ yoksa (ya da §20.1.1 gereği yok sayıldıysa) koşul atlanır. MRZ okunduysa belge
        numarasının hem kendi hanesi hem bileşik hane tutmalıdır. Geçersiz ya da güvenilmeyen MRZ
        numarayı temiz saydırmaz. Diğer iki koşul (tür, okunaklılık, uzunluk) 05.6'nındır.
        """
        if self.status in (MrzStatus.ABSENT, MrzStatus.UNRECOGNIZED):
            return True
        return (
            self.mrz is not None
            and self.mrz.document_number is not None
            and self.mrz.composite_valid
        )


def compute_check_digit(characters: str) -> int:
    """§20.1.4 kontrol hanesi: değer × 7, 3, 1 ağırlıkları, toplam mod 10."""
    return sum(_value(char) * _WEIGHTS[index % 3] for index, char in enumerate(characters)) % 10


def detect_format(lines: Sequence[str]) -> MrzFormat | None:
    """Satır sayısı ve uzunluğundan biçim (§20.1.1); uymuyorsa `None`."""
    if not lines or any(len(line) != len(lines[0]) for line in lines):
        return None
    return _SHAPES.get((len(lines), len(lines[0])))


def parse_mrz(lines: Sequence[str], *, today: date | None = None) -> Mrz | None:
    """MRZ satırlarını ayrıştırır ve kontrol hanelerini doğrular.

    Biçim tanınmıyorsa `None`; izin verilmeyen karakter varsa `InvalidMrzError`. `today`
    doğum tarihinin yüzyılını seçer (§20.1.6), verilmezse bugündür.
    """
    mrz_format = detect_format(lines)
    if mrz_format is None:
        return None
    upper = tuple(line.translate(_UPPERCASE) for line in lines)
    for number, line in enumerate(upper, start=1):
        if not _ALLOWED.fullmatch(line):
            raise InvalidMrzError(
                f"MRZ geçersiz: {number}. satırda A-Z, 0-9 ve < dışında karakter var"
            )
    return _read(mrz_format, upper, date.today() if today is None else today)


def apply_mrz_priority(analysis: PageAnalysis, *, today: date | None = None) -> MrzResolution:
    """Sayfanın MRZ'sini görünen okumalara uygular: çelişkide MRZ kazanır, çelişki nota yazılır."""
    lines = analysis.person.mrz_lines
    if lines is None:
        return MrzResolution(analysis, MrzStatus.ABSENT)
    if analysis.is_blank or not analysis.is_readable:
        return MrzResolution(analysis, MrzStatus.UNTRUSTED)
    try:
        mrz = parse_mrz(lines, today=today)
    except InvalidMrzError:
        return MrzResolution(_rebuild(analysis, notes=[_INVALID_NOTE]), MrzStatus.INVALID)
    if mrz is None:
        return MrzResolution(_rebuild(analysis, notes=[_UNRECOGNIZED_NOTE]), MrzStatus.UNRECOGNIZED)

    person = analysis.person.model_dump()
    fields = {name: reading.model_dump() for name, reading in analysis.fields.items()}
    conflicts: list[str] = []
    for name in MRZ_FIELDS:
        if name in mrz.illegible_fields:
            _write(person, fields, name, None, only_missing=False)
            continue
        value = getattr(mrz, name)
        if value is None:
            continue
        readings = _visible_readings(analysis, name)
        agrees = all(_agrees(analysis, name, reading, value) for reading in readings)
        if not agrees:
            conflicts.append(name)
        _write(person, fields, name, value, only_missing=agrees)

    resolved = _rebuild(
        analysis, person=person, fields=fields, notes=_resolution_notes(mrz, conflicts)
    )
    return MrzResolution(resolved, MrzStatus.READ, mrz, tuple(conflicts))


def _value(char: str) -> int:
    if "0" <= char <= "9":
        return ord(char) - ord("0")
    if "A" <= char <= "Z":
        return ord(char) - ord("A") + 10
    if char == FILLER:
        return 0
    raise ValueError("MRZ karakteri A-Z, 0-9 veya < olmalı")


def _check_digit_holds(characters: str, check: str) -> bool:
    return "0" <= check <= "9" and int(check) == compute_check_digit(characters)


def _read(mrz_format: MrzFormat, lines: tuple[str, ...], today: date) -> Mrz:
    layout = _LAYOUTS[mrz_format]
    failed: list[str] = []
    illegible: set[str] = set()

    def checked(name: str, span: _Span, check: _Span) -> str:
        raw = span.read(lines)
        if not _check_digit_holds(raw, check.read(lines)):
            failed.append(name)
            illegible.add(name)
        return raw

    number = checked("document_number", layout.document_number, layout.document_number_check)
    birth = checked("date_of_birth", layout.date_of_birth, layout.date_of_birth_check)
    expiry = checked("expiry_date", layout.expiry_date, layout.expiry_date_check)
    optional = tuple(span.read(lines) for span in layout.optional_data)
    if layout.optional_data_check is not None:
        check = layout.optional_data_check.read(lines)
        (raw,) = optional
        padding_only = raw == FILLER * len(raw) and check == FILLER
        if not (padding_only or _check_digit_holds(raw, check)):
            failed.append(OPTIONAL_DATA)
            illegible.add(OPTIONAL_DATA)
    composite = "".join(span.read(lines) for span in layout.composite)
    if not _check_digit_holds(composite, layout.composite_check.read(lines)):
        failed.append(COMPOSITE)

    values = {
        "document_number": number.rstrip(FILLER) or None,
        "nationality": _nationality(layout.nationality.read(lines)),
        "date_of_birth": _date(birth, today=today),
        "expiry_date": _date(expiry),
    }
    name_field = layout.name.read(lines)
    surname, given_names = _name(name_field)
    if any(char.isdigit() for char in name_field):
        illegible.update(("surname", "given_names"))
    for name, value in values.items():
        if value is None:
            illegible.add(name)

    def usable[T](name: str, value: T) -> T | None:
        return None if name in illegible else value

    sex = layout.sex.read(lines)
    return Mrz(
        format=mrz_format,
        document_code=layout.document_code.read(lines).rstrip(FILLER),
        issuing_state=layout.issuing_state.read(lines).rstrip(FILLER),
        surname=usable("surname", surname),
        given_names=usable("given_names", given_names),
        document_number=usable("document_number", values["document_number"]),
        nationality=usable("nationality", values["nationality"]),
        date_of_birth=usable("date_of_birth", values["date_of_birth"]),
        sex=sex if sex in ("M", "F") else None,
        expiry_date=usable("expiry_date", values["expiry_date"]),
        optional_data=usable(OPTIONAL_DATA, tuple(part.rstrip(FILLER) for part in optional)),
        failed_checks=tuple(failed),
        illegible_fields=tuple(name for name in (*MRZ_FIELDS, OPTIONAL_DATA) if name in illegible),
    )


def _name(field: str) -> tuple[str | None, str | None]:
    primary, _, secondary = field.rstrip(FILLER).partition(FILLER * 2)
    return _name_words(primary), _name_words(secondary)


def _name_words(part: str) -> str | None:
    return " ".join(word for word in part.split(FILLER) if word) or None


def _nationality(raw: str) -> str | None:
    code = raw.rstrip(FILLER)
    return code if _NATIONALITY.fullmatch(code) else None


def _date(raw: str, *, today: date | None = None) -> date | None:
    # `today` yalnız doğum tarihinde verilir: son geçerlilik her zaman 20YY (§20.1.6).
    if not _YYMMDD.fullmatch(raw):
        return None
    year, month, day = int(raw[:2]), int(raw[2:4]), int(raw[4:])
    try:
        value = date(2000 + year, month, day)
        if today is not None and value > today:
            value = date(1900 + year, month, day)
    except ValueError:
        return None
    return value


def _visible_readings(analysis: PageAnalysis, name: str) -> list[str | date]:
    readings: list[str | date] = []
    if name in _PERSON_FIELDS:
        value = getattr(analysis.person, name)
        if value is not None:
            readings.append(value)
    reading = analysis.fields.get(name)
    if reading is not None and reading.value is not None:
        readings.append(reading.value)
    return readings


def _agrees(analysis: PageAnalysis, name: str, reading: str | date, value: str | date) -> bool:
    text = _text(reading)
    if isinstance(value, date):
        return text == value.isoformat()
    if name == "document_number":
        return _NUMBER_SEPARATORS.sub("", text.upper()) == value
    if name == "nationality":
        return text == value
    language = analysis.language
    if _same_name((text,), value, language):
        return True
    other_names = analysis.person.other_names
    # MRZ'nin verilen adlar kısmı ayrı yazılmış baba adını/ikinci adı da taşıyabilir.
    return (
        name == "given_names"
        and other_names is not None
        and _same_name((text, other_names), value, language)
    )


def _same_name(parts: tuple[str, ...], value: str, language: str | None) -> bool:
    try:
        return normalize_name(*parts, language=language) == normalize_name(value)
    except EmptyNameError:
        return False


def _write(
    person: dict[str, object],
    fields: dict[str, dict[str, object]],
    name: str,
    value: str | date | None,
    *,
    only_missing: bool,
) -> None:
    if name in _PERSON_FIELDS and not (only_missing and person[name] is not None):
        person[name] = value
    reading = fields.get(name)
    if reading is not None and not (only_missing and reading["legible"]):
        fields[name] = {
            "value": None if value is None else _text(value),
            "legible": value is not None,
        }


def _text(value: str | date) -> str:
    return value.isoformat() if isinstance(value, date) else value


def _resolution_notes(mrz: Mrz, conflicts: Sequence[str]) -> list[str]:
    notes: list[str] = []
    checks = [name for name in mrz.failed_checks if name != COMPOSITE]
    if checks:
        notes.append(f"MRZ kontrol hanesi tutmuyor, alan okunamadı sayıldı: {', '.join(checks)}.")
    if not mrz.composite_valid:
        notes.append(_COMPOSITE_NOTE)
    malformed = [name for name in mrz.illegible_fields if name not in mrz.failed_checks]
    if malformed:
        notes.append(f"MRZ değeri geçersiz, alan okunamadı sayıldı: {', '.join(malformed)}.")
    if conflicts:
        notes.append(
            f"MRZ ile görünen metin çelişiyor, MRZ değeri kullanıldı: {', '.join(conflicts)}."
        )
    return notes


def _rebuild(
    analysis: PageAnalysis,
    *,
    person: dict[str, object] | None = None,
    fields: dict[str, dict[str, object]] | None = None,
    notes: Sequence[str],
) -> PageAnalysis:
    data = analysis.model_dump()
    if person is not None:
        data["person"] = person
    if fields is not None:
        data["fields"] = fields
    existing = analysis.notes
    added = [note for note in notes if existing is None or note not in existing]
    data["notes"] = " ".join(filter(None, (existing, *added))) or None
    # Yeniden doğrulama: MRZ'den yazılan değer de §8.4 şemasına uymak zorunda.
    return PageAnalysis.model_validate(data)
