"""Mekanik tanıma — eğitim öğesinin türünü yapay zekâ çağırmadan tanıma (PRD 11.9.2, PLAN.md §C86
"Mekanik tanıma").

Kontroller sırayla yapılır, ilk kesin sonuç kazanır:

1. **Örnek olabilir mi** (`check_example`: PDF/JPEG/PNG, okunabilir, boyut sınırı). Staging'de
   yapılır (`app.training.placement.stage_file`); geçmeyen öğe `failed` olur ve buraya gelmez.
2. **SHA-256.** İçerik `example_files` dizininde ya da örnek envanterinin
   (`KnownDocuments/_ornek_envanteri.csv`, harici toplayıcının ürünü, git dışı) `role=example`
   satırlarında tek bir bilinen türe kayıtlıysa o tür. Envanter yoksa adım yalnız dizinle yapılır.
   İçerik birden çok türe kayıtlıysa tanıma mekanik değildir.
3. **İpucu** (harita satırının ya da "Beklenen tür"ün slug'ı) bilinen türse yapı kuralları:
   katalog türünde dosya türü `expected_file_types`'ta ve PDF'in sayfa sayısı beklenen aralıkta (ön
   ve arka yüzlü türde aralık kabul edilen düzenlerden türer, 11.1.2); önerilen türde yalnız dosya
   türü (PDF/JPEG/PNG — staging'den geçen her dosya). Bilinmeyen slug ipucu sayılmaz. İpucuyla
   gelen SHA-256 (harita satırı) dosyanınkine eşit olmalıdır; tutmuyorsa tanıma mekanik değildir.
4. **PDF metin katmanında MRZ.** Metin katmanı bellekte okunur (`extract_pdf_content_text`; OCR
   yok, görüntü render edilmez — K11, K12). Satırlar boşluksuzlaştırılır; yalnız `A-Z`, `0-9`, `<`
   taşıyan 30, 36 ya da 44 karakterlik satırlar MRZ adayıdır; aynı uzunlukta ardışık adaylardan
   biçimin satır sayısı kadarı (TD1 3, TD2/TD3 2) `parse_mrz`'e verilir. Kontrol hanelerinin hepsi
   tutan MRZ'nin belge kodu (`P` → pasaport, `I`/`A`/`C` → kimlik_karti, `IR`/`R` → oturum_izni,
   `V` → vize) ve veren ülkesi (ISO3) tek bir bilinen türe inerse (`KnownTypes.match_kind`) o tür.
   Tanınan türün yapı kuralları (3) burada da uygulanır.

**Çelişki.** İpucu (3) ile SHA-256 kaydı (2) ya da geçerli bir MRZ (4) çelişirse tanıma mekanik
değildir. Geçerli MRZ ipucunu yalnız (ülke, belge türü) çifti ipucu türününkiyle aynıysa doğrular.

**Sonuç.** Tanınan öğe `place_example(..., method=mechanical)` ile yerleşir (etiketsiz; aynı içerik
aynı türde örnekse `skipped`); not Türkçedir: "Mekanik: <dayanak> → `<slug>`; <kontroller>".
Tanınmayan öğe `ai_pending` olur (yapay zekâ yolu, tm 117) ve notu gerekçeyi söyler. Kontrollerin
dökümü `training_items.checks_json`'a yazılır.

**Kişisel değer yok** (CONVENTIONS §6). MRZ'den yalnız biçim, belge kodu, veren ülke ve tutmayan
hanelerin adları tutulur; ad, numara ve tarihler bellekte kalır, not, döküm ve olaya yazılmaz.
Envanterden yalnız `slug`, `role` ve `sha256` sütunları okunur.

Modül yapay zekâ sağlayıcısı çağırmaz. Fonksiyonlar işlemi commit etmez.
"""

from __future__ import annotations

import csv
import enum
import io
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.schema import FileType, PageRange, Sides, layout_pages
from app.db.models import (
    ExampleFileRecord,
    TrainingItem,
    TrainingItemStatus,
    TrainingMethod,
    TrainingRun,
)
from app.matching.mrz import MrzFormat, parse_mrz
from app.pipeline.render import RenderError, extract_pdf_content_text
from app.storage import DataLayout, FileKind
from app.training.known_types import KnownType, KnownTypes
from app.training.placement import (
    ItemNotPlaceableError,
    Placement,
    place_example,
    refresh_run,
    stage_file,
)

MRZ_DOC_KINDS: Mapping[str, str] = MappingProxyType(
    {
        "P": "pasaport",
        "I": "kimlik_karti",
        "A": "kimlik_karti",
        "C": "kimlik_karti",
        "ID": "kimlik_karti",
        "IR": "oturum_izni",
        "R": "oturum_izni",
        "V": "vize",
    }
)
"""MRZ belge kodu → önerilen tür kaydının `kaynak_tur`'u (§C86). ICAO Doc 9303'te ilk harf belge
sınıfıdır, ikinci harf veren devletin takdiridir: `P` ve `V` ile başlayan her kod pasaport ve
vizedir; `I`/`A`/`C` ile başlayıp listede olmayan iki harfli kod (ör. oturum izni taşıyan `AR`)
belirsizdir ve eşlenmez."""

MRZ_STATE_CODES: Mapping[str, str] = MappingProxyType({"D": "DEU", "RKS": "XKX"})
"""MRZ'de ISO 3166-1 alpha-3 olmayan veren devlet kodları → önerilen tür kaydının ülke kodu:
Almanya ICAO Doc 9303'te `D`, Kosova `RKS` yazar."""

INVENTORY_EXAMPLE_ROLE = "example"
_INVENTORY_COLUMNS = ("slug", "role", "sha256")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MRZ_LINE = re.compile(r"[A-Z0-9<]+")
_MRZ_LINE_COUNTS = MappingProxyType({30: 3, 36: 2, 44: 2})
_FILE_LABELS = MappingProxyType({"pdf": "PDF", "jpeg": "JPEG", "png": "PNG"})


class MrzSearchStatus(enum.StrEnum):
    """Metin katmanındaki MRZ aramasının sonucu (`checks_json["mrz"]["status"]`)."""

    NOT_PDF = "not_pdf"  # görüntü dosyası: metin katmanı yok, OCR yapılmaz
    UNREADABLE = "unreadable"  # PDF metin katmanı okunamadı
    NO_TEXT = "no_text"  # PDF'in hiçbir sayfasında metin katmanı yok
    ABSENT = "absent"  # metin katmanında MRZ satırı yok
    FAILED_CHECKS = "failed_checks"  # MRZ var, kontrol haneleri tutmuyor
    AMBIGUOUS = "ambiguous"  # geçerli MRZ'ler farklı (kod, ülke) veriyor
    UNMAPPED_CODE = "unmapped_code"  # belge kodu bir belge türüne eşlenmiyor
    NO_TYPE = "no_type"  # (ülke, tür) tek bir bilinen türe inmiyor
    MATCHED = "matched"  # tek bir bilinen türe indi


class RecognitionBasis(enum.StrEnum):
    """Mekanik tanımanın dayanağı (`checks_json["result"]["basis"]`)."""

    SHA256_INDEX = "sha256_index"
    SHA256_INVENTORY = "sha256_inventory"
    HINT = "hint"
    MRZ = "mrz"


@dataclass(frozen=True, slots=True)
class ExampleInventory:
    """Örnek envanterinin `role=example` satırları: SHA-256 → slug'lar. Yalnız tür ve içerik
    özeti taşır; kaynak, yazar ve not sütunları okunmaz."""

    slugs_by_sha256: Mapping[str, frozenset[str]]

    def slugs(self, sha256: str) -> frozenset[str]:
        return self.slugs_by_sha256.get(sha256.lower(), frozenset())


def parse_example_inventory(text: str) -> ExampleInventory:
    """Envanter metnini okur (`utf-8-sig`; ayraç `,` ya da `;`; başlık adları büyük/küçük harf
    duyarsız). `role` sütunu `example` olmayan, slug'ı boş ya da SHA-256'sı biçimsiz satır atlanır;
    `slug`, `role` ya da `sha256` sütunu yoksa envanter boştur."""
    text = text.removeprefix("﻿")
    first_line = text.partition("\n")[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    header = [name.strip().casefold() for name in next(reader, [])]
    if any(column not in header for column in _INVENTORY_COLUMNS):
        return ExampleInventory(MappingProxyType({}))
    slug_at, role_at, sha_at = (header.index(column) for column in _INVENTORY_COLUMNS)
    found: defaultdict[str, set[str]] = defaultdict(set)
    for row in reader:
        if len(row) <= max(slug_at, role_at, sha_at):
            continue
        slug, role = row[slug_at].strip(), row[role_at].strip().casefold()
        sha256 = row[sha_at].strip().lower()
        if role == INVENTORY_EXAMPLE_ROLE and slug and _SHA256.fullmatch(sha256):
            found[sha256].add(slug)
    return ExampleInventory(
        MappingProxyType({sha256: frozenset(slugs) for sha256, slugs in found.items()})
    )


def load_example_inventory(layout: DataLayout) -> ExampleInventory | None:
    """`KnownDocuments/_ornek_envanteri.csv`; dosya yoksa `None` (SHA-256 adımı yalnız dizinle)."""
    path = layout.example_inventory_path
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None
    return parse_example_inventory(text)


@dataclass(frozen=True, slots=True)
class MrzReading:
    """Metin katmanında bulunan bir MRZ'nin kişisel değer taşımayan özeti. `page` 1 tabanlıdır;
    `issuing_state` MRZ'de yazıldığı gibidir."""

    page: int
    format: MrzFormat
    document_code: str
    issuing_state: str
    failed_checks: tuple[str, ...]

    @property
    def valid(self) -> bool:
        """Kontrol hanelerinin hepsi (bileşik dahil) tutuyor."""
        return not self.failed_checks

    @property
    def doc_kind(self) -> str | None:
        return mrz_doc_kind(self.document_code)

    @property
    def country_iso3(self) -> str:
        return MRZ_STATE_CODES.get(self.issuing_state, self.issuing_state)

    def describe(self) -> str:
        return f"{self.format}, {self.document_code or '<'}, {self.issuing_state or '<'}"

    def as_check(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "format": self.format.value,
            "document_code": self.document_code,
            "issuing_state": self.issuing_state,
            "failed_checks": list(self.failed_checks),
        }


def mrz_doc_kind(document_code: str) -> str | None:
    """MRZ belge kodunun `kaynak_tur`'u (`MRZ_DOC_KINDS`); eşlenmiyorsa `None`."""
    if document_code in MRZ_DOC_KINDS:
        return MRZ_DOC_KINDS[document_code]
    if document_code[:1] in ("P", "V"):
        return MRZ_DOC_KINDS[document_code[:1]]
    return None


def find_mrz_readings(texts: Sequence[str | None]) -> list[MrzReading]:
    """Sayfa metin katmanlarındaki MRZ'ler (sayfa ve satır sırasıyla); metinsiz sayfa atlanır."""
    readings: list[MrzReading] = []
    for page, text in enumerate(texts, start=1):
        if text is None:
            continue
        for run in _candidate_runs(text):
            size = _MRZ_LINE_COUNTS[len(run[0])]
            for start in range(len(run) - size + 1):
                mrz = parse_mrz(run[start : start + size])
                if mrz is None:
                    continue
                readings.append(
                    MrzReading(
                        page=page,
                        format=mrz.format,
                        document_code=mrz.document_code,
                        issuing_state=mrz.issuing_state,
                        failed_checks=mrz.failed_checks,
                    )
                )
    return readings


def _candidate_runs(text: str) -> list[list[str]]:
    """Aynı uzunlukta ardışık MRZ adayı satır dizileri; boş satır ardışıklığı bozmaz."""
    runs: list[list[str]] = []
    current: list[str] = []
    for raw in text.splitlines():
        line = "".join(raw.split())
        if not line:
            continue
        if len(line) in _MRZ_LINE_COUNTS and _MRZ_LINE.fullmatch(line):
            if current and len(current[0]) != len(line):
                runs.append(current)
                current = []
            current.append(line)
            continue
        if current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


@dataclass(frozen=True, slots=True)
class MrzEvidence:
    """Dosyanın MRZ kanıtı: durum, geçerli okumaların (ülke, tür) çiftleri ve inen tür."""

    status: MrzSearchStatus
    readings: tuple[MrzReading, ...] = ()
    matched: KnownType | None = None

    @property
    def valid_readings(self) -> tuple[MrzReading, ...]:
        return tuple(reading for reading in self.readings if reading.valid)

    @property
    def pairs(self) -> frozenset[tuple[str, str | None]]:
        return frozenset((r.country_iso3, r.doc_kind) for r in self.valid_readings)

    def confirms(self, known: KnownType) -> bool:
        """Geçerli MRZ'lerin hepsi `known`'un (ülke, tür) çiftini veriyor."""
        return known.doc_kind is not None and self.pairs == {(known.country_iso3, known.doc_kind)}

    def describe(self) -> str:
        return "; ".join(reading.describe() for reading in self.valid_readings)

    def reason(self) -> str:
        """Tür vermeyen kanıtın Türkçe gerekçesi."""
        if self.status == MrzSearchStatus.NOT_PDF:
            return "görüntü dosyasında metin katmanı yok (OCR yapılmaz)"
        if self.status == MrzSearchStatus.UNREADABLE:
            return "PDF metin katmanı okunamadı"
        if self.status == MrzSearchStatus.NO_TEXT:
            return "PDF'te metin katmanı yok"
        if self.status == MrzSearchStatus.ABSENT:
            return "PDF metin katmanında MRZ yok"
        if self.status == MrzSearchStatus.FAILED_CHECKS:
            failed = sorted({name for reading in self.readings for name in reading.failed_checks})
            return f"MRZ kontrol haneleri tutmuyor ({', '.join(failed)})"
        if self.status == MrzSearchStatus.AMBIGUOUS:
            return f"MRZ'ler farklı türlere işaret ediyor ({self.describe()})"
        if self.status == MrzSearchStatus.UNMAPPED_CODE:
            return f"MRZ ({self.describe()}) belge kodu bir belge türüne eşlenmiyor"
        return f"MRZ ({self.describe()}) tek bir bilinen türe inmiyor"

    def as_check(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "slug": self.matched.slug if self.matched is not None else None,
            "readings": [reading.as_check() for reading in self.readings],
        }


def read_mrz_evidence(known: KnownTypes, file_kind: str, content: bytes) -> MrzEvidence:
    """Dosyanın PDF metin katmanındaki MRZ kanıtı (bellekte; görüntü dosyasında aranmaz)."""
    if file_kind != FileKind.PDF:
        return MrzEvidence(MrzSearchStatus.NOT_PDF)
    try:
        texts = extract_pdf_content_text(content)
    except RenderError:
        return MrzEvidence(MrzSearchStatus.UNREADABLE)
    if all(text is None for text in texts):
        return MrzEvidence(MrzSearchStatus.NO_TEXT)
    readings = tuple(find_mrz_readings(texts))
    evidence = MrzEvidence(MrzSearchStatus.ABSENT, readings)
    if not readings:
        return evidence
    pairs = evidence.pairs
    if not pairs:
        return MrzEvidence(MrzSearchStatus.FAILED_CHECKS, readings)
    if len(pairs) > 1:
        return MrzEvidence(MrzSearchStatus.AMBIGUOUS, readings)
    ((country_iso3, doc_kind),) = pairs
    if doc_kind is None:
        return MrzEvidence(MrzSearchStatus.UNMAPPED_CODE, readings)
    matched = known.match_kind(country_iso3, doc_kind)
    if matched is None:
        return MrzEvidence(MrzSearchStatus.NO_TYPE, readings)
    return MrzEvidence(MrzSearchStatus.MATCHED, readings, matched)


@dataclass(frozen=True, slots=True)
class Recognition:
    """Mekanik tanımanın sonucu. `slug` doluysa tür mekanik tanındı (`basis` dayanağıdır); boşsa
    öğe yapay zekâya gider. `note` Türkçe ve kişisel değersizdir; `checks` `checks_json`'dır."""

    slug: str | None
    basis: RecognitionBasis | None
    note: str
    checks: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MechanicalOutcome:
    """`recognize_item` sonucu: tanıma ve (tanındıysa) yerleştirme."""

    recognition: Recognition
    placement: Placement | None

    @property
    def status(self) -> TrainingItemStatus:
        if self.placement is not None:
            return self.placement.status
        return TrainingItemStatus.AI_PENDING


def recognize(
    session: Session,
    known: KnownTypes,
    item: TrainingItem,
    content: bytes,
    *,
    inventory: ExampleInventory | None,
    hint_sha256: str | None = None,
) -> Recognition:
    """Öğenin türünü mekanik kontrollerle tanır (modül açıklaması); veritabanına yazmaz.

    `content` öğenin staging'deki (ya da yerinde kaydedilecek) içeriğidir; SHA-256'sı, dosya türü
    ve sayfa sayısı öğeden okunur. `inventory` `load_example_inventory`'nin sonucudur (`None`:
    envanter yok). `hint_sha256` ipucuyla (harita satırı) gelen SHA-256'dır.
    """
    if item.sha256 is None or item.file_kind is None:
        raise ItemNotPlaceableError(f"Öğe {item.id} staging'den geçmemiş")
    file_kind, pages = item.file_kind, item.page_count or 1
    checks: dict[str, Any] = {"file": {"kind": file_kind, "pages": pages}}
    extras: list[str] = []

    hint, hint_text = None, hint_label(item)
    if item.hint_slug:
        hint = known.get(item.hint_slug)
        checks["hint"] = {
            "slug": item.hint_slug,
            "from": "map" if item.row_number is not None else "expected",
            "known": hint is not None,
        }
        if hint is None:
            extras.append(f"ipucu `{item.hint_slug}` bilinen bir tür değil")
    if hint_sha256 is not None:
        sha_holds = hint_sha256.strip().lower() == item.sha256
        checks["hint_sha256"] = sha_holds
        if not sha_holds:
            return _pending(checks, "haritadaki SHA-256 dosyayla tutmuyor", extras, item)
        extras.append("SHA-256 tuttu")

    # (2) SHA-256: örnek kaydı dizini ve envanter.
    recorded = session.scalars(
        select(ExampleFileRecord.type_slug)
        .where(ExampleFileRecord.sha256 == item.sha256, ExampleFileRecord.removed_at.is_(None))
        .distinct()
    )
    indexed = sorted(slug for slug in recorded if slug in known)
    listed = None
    if inventory is not None:
        listed = sorted(slug for slug in inventory.slugs(item.sha256) if slug in known)
    checks["sha256"] = {"index": indexed, "inventory": listed}
    sha_slugs = sorted(set(indexed) | set(listed or ()))
    if len(sha_slugs) > 1:
        names = ", ".join(f"`{slug}`" for slug in sha_slugs)
        return _pending(checks, f"SHA-256 birden çok türde kayıtlı ({names})", extras, item)
    if sha_slugs:
        (slug,) = sha_slugs
        if hint is not None and hint.slug != slug:
            reason = f"{hint_text} `{hint.slug}` SHA-256 kaydıyla (`{slug}`) çelişiyor"
            return _pending(checks, reason, extras, item)
        if slug in indexed:
            basis, basis_text = RecognitionBasis.SHA256_INDEX, "SHA-256 örnek kaydında"
        else:
            basis, basis_text = RecognitionBasis.SHA256_INVENTORY, "SHA-256 örnek envanterinde"
        return _recognized(checks, slug, basis, basis_text, [*extras, _file_text(item)])

    # (3) ipucu ve (4) PDF metin katmanında MRZ.
    evidence = read_mrz_evidence(known, file_kind, content)
    checks["mrz"] = evidence.as_check()
    if hint is not None:
        problems = _structure_problems(hint, item)
        checks["hint"]["structure"] = problems
        if problems:
            reason = f"{hint_text} `{hint.slug}` yapısına uymuyor: {'; '.join(problems)}"
            return _pending(checks, reason, extras, item)
        if evidence.valid_readings and not evidence.confirms(hint):
            reason = f"{hint_text} `{hint.slug}` MRZ ({evidence.describe()}) ile çelişiyor"
            return _pending(checks, reason, extras, item)
        if evidence.valid_readings:
            extras.append(f"MRZ ({evidence.describe()}) tuttu")
        return _recognized(
            checks, hint.slug, RecognitionBasis.HINT, hint_text, [*extras, _file_text(item, hint)]
        )
    matched = evidence.matched
    if matched is not None:
        problems = _structure_problems(matched, item)
        checks["mrz"]["structure"] = problems
        if problems:
            reason = f"MRZ `{matched.slug}` gösteriyor ama yapısına uymuyor: {'; '.join(problems)}"
            return _pending(checks, reason, extras, item)
        basis_text = f"PDF metin katmanında MRZ ({evidence.describe()})"
        return _recognized(
            checks,
            matched.slug,
            RecognitionBasis.MRZ,
            basis_text,
            [*extras, "kontrol haneleri tuttu", _file_text(item, matched)],
        )
    return _pending(checks, f"SHA-256 kayıtlı değil; {evidence.reason()}", extras, item)


def recognize_item(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    item: TrainingItem,
    *,
    inventory: ExampleInventory | None,
    hint_sha256: str | None = None,
    source: Path | None = None,
) -> MechanicalOutcome:
    """`queued` öğeyi mekanik tanır: tanınırsa `place_example(method=mechanical)` ile yerleştirir,
    tanınmazsa `ai_pending` yapar; kontrollerin dökümü `checks_json`'a yazılır. Commit etmez.

    `source` verilirse öğenin içeriği odur (haritadan çözülen, türün örnek klasöründeki dosya —
    yerinde kayıt); verilmezse `_egitim/gelen` kopyası. Öğe `queued` değilse
    `ItemNotPlaceableError`.
    """
    if item.status != TrainingItemStatus.QUEUED:
        raise ItemNotPlaceableError(f"Öğe {item.id} mekanik tanıma beklemiyor: {item.status}")
    if source is None:
        if item.staged_path is None:
            raise ItemNotPlaceableError(f"Öğe {item.id} için tanınacak dosya yok")
        source = layout.resolve(item.staged_path)
    content = source.read_bytes()
    recognition = recognize(
        session, known, item, content, inventory=inventory, hint_sha256=hint_sha256
    )
    item.checks_json = recognition.checks
    if recognition.slug is None:
        item.status = TrainingItemStatus.AI_PENDING.value
        item.note = recognition.note
        refresh_run(session, item.run)
        return MechanicalOutcome(recognition, None)
    placement = place_example(
        session,
        layout,
        known,
        item,
        recognition.slug,
        method=TrainingMethod.MECHANICAL,
        note=recognition.note,
        source=source,
    )
    return MechanicalOutcome(recognition, placement)


def stage_and_recognize(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    run: TrainingRun,
    original_name: str,
    content: bytes,
    *,
    max_bytes: int,
    inventory: ExampleInventory | None,
    hint_slug: str | None = None,
) -> TrainingItem:
    """Eğitim yüklemesinin bir dosyası: staging (`stage_file`, adım 1) ve mekanik tanıma
    (`recognize_item`). Dönen öğe `failed`, `placed`, `skipped`, `conflict` ya da `ai_pending`'dir.
    Commit etmez."""
    item = stage_file(
        session, layout, run, original_name, content, max_bytes=max_bytes, hint_slug=hint_slug
    )
    if item.status == TrainingItemStatus.QUEUED:
        recognize_item(session, layout, known, item, inventory=inventory)
    return item


def hint_label(item: TrainingItem) -> str:
    """İpucunun Türkçe adı: harita satırıysa "harita satırı N", değilse "beklenen tür"."""
    if item.row_number is not None:
        return f"harita satırı {item.row_number}"
    return "beklenen tür"


def _page_range(known: KnownType) -> PageRange | None:
    entry = known.entry
    if entry is None:
        return None
    if entry.sides is Sides.FRONT_BACK:
        return layout_pages(entry.front_back_layouts)
    return entry.expected_pages


def _structure_problems(known: KnownType, item: TrainingItem) -> list[str]:
    """Türün yapı kurallarına uymayan yanlar; önerilen türde (katalog kaydı yok) kural dosya
    türünün PDF/JPEG/PNG olmasıdır, staging'den geçen her öğe bunu sağlar."""
    entry = known.entry
    if entry is None:
        return []
    problems: list[str] = []
    allowed = entry.expected_file_types
    if FileType(item.file_kind) not in allowed:
        names = ", ".join(_FILE_LABELS.get(kind, kind.upper()) for kind in allowed)
        problems.append(f"dosya türü {_label(item)} izinli değil (izinli: {names})")
    limit = _page_range(known)
    pages = item.page_count or 1
    if item.file_kind == FileKind.PDF and limit is not None:
        if not limit.min <= pages <= limit.max:
            problems.append(f"sayfa sayısı {pages}, beklenen {_range_text(limit)}")
    return problems


def _label(item: TrainingItem) -> str:
    return _FILE_LABELS.get(item.file_kind or "", (item.file_kind or "").upper())


def _range_text(limit: PageRange) -> str:
    return f"{limit.min}–{limit.max}"


def _file_text(item: TrainingItem, known: KnownType | None = None) -> str:
    if item.file_kind != FileKind.PDF:
        return _label(item)
    text = f"PDF, {item.page_count or 1} sayfa"
    limit = _page_range(known) if known is not None else None
    if limit is not None:
        text += f" (beklenen {_range_text(limit)})"
    return text


def _recognized(
    checks: dict[str, Any],
    slug: str,
    basis: RecognitionBasis,
    basis_text: str,
    extras: Iterable[str],
) -> Recognition:
    checks["result"] = {"slug": slug, "basis": basis.value}
    note = "; ".join([f"Mekanik: {basis_text} → `{slug}`", *extras])
    return Recognition(slug, basis, note, checks)


def _pending(
    checks: dict[str, Any], reason: str, extras: Iterable[str], item: TrainingItem
) -> Recognition:
    checks["result"] = {"slug": None, "reason": reason}
    note = "; ".join([f"Mekanik tanınmadı: {reason}", *extras, _file_text(item)])
    return Recognition(None, None, note, checks)
