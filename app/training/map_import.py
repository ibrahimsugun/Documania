"""Harita yükle — CSV haritasının okunması, yollarının çözümü, önizlemesi ve toplu taramanın
başlatılması (PRD 11.9.5, PLAN.md §C87).

Harita, eğitim modunun toplu taramasının girdisidir: her satır bir türü (`slug`) ve bir dosyayı ya
da klasörü gösterir. Örnek biçimler harici toplayıcının `_ornek_envanteri.csv`'si (dosya satırları:
`slug`, `role`, `dest`, `source_collection_path`, `sha256`, …) ve `_onerilen_turler.csv`'si (tür
satırları: `slug`, `ornek_klasoru`) ya da yalnız `slug` + `path` sütunlu bir CSV'dir.

- **Okuma (`parse_map`).** `utf-8-sig`; ayraç `,` ya da `;` (başlık satırında çok olan); başlık
  adları büyük/küçük harf duyarsız; bayt ve satır sınırı (`TRAINING_MAP_MAX_BYTES`,
  `TRAINING_MAP_MAX_ROWS`). Yalnız `slug`, `role`, `sha256` ve yol sütunları okunur; kişisel içerik
  taşıyabilecek sütunlar (`personal_values_transcribed`, `note`, `author`) ve öteki sütunlar
  okunmaz. Uzak adres (`source`) kullanılmaz. Satır numarası elektronik tablodaki gibidir (başlık 1.
  satır; boş satır da sayılır).
- **Yol seçimi ve çözümü (`plan_map`).** Satırın yolu şu sırayla ilk dolu sütundur: `dest` →
  `output_relative_path` → `ornek_klasoru` (klasördeki PDF/JPEG/PNG dosyaları, özyinelemesiz) →
  `source_collection_path` (yalnız `TRAINING_COLLECTION_DIR` ayarlıysa, o kökün altında) → `path`.
  Öteki sütunlar `DATA_DIR` altında çözülür. Yol güvenliği `app.storage.map_paths`'tadır (yalnız
  göreli; kökte kalır). `role=reference` ("referans — örnek değil"), yolsuz, koleksiyon kökü
  ayarsız, güvensiz yollu ve dosyası bulunmayan satır gerekçesiyle atlanır. Dosya türün örnek
  klasöründe (`KnownDocuments/examples/<slug>/`) listeleniyorsa **yerindedir**: kopyalanmaz, yerinde
  kaydedilir.
- **Tür.** Haritanın `slug`'ı bilinen türse ipucudur; bilinmeyen slug ipucu sayılmaz (mekanik yalnız
  SHA-256 ve MRZ ile tanır). Yerindeki dosyanın türü klasörünündür.
- **Önizleme (`preview_map`, yazma yok).** Satır, dosya, atlanan (gerekçe sayılarıyla), zaten
  kayıtlı (SHA-256 + tür ya da yerindeki dosyanın kaydı), mekanik hazır ve yapay zekâ gerekebilecek
  sayıları. Türü belli dosya (haritanın bilinen türü ya da yerindeki dosyanın klasörü) ve SHA-256'sı
  tek bir bilinen türde kayıtlı dosya yapay zekâya gitmez (toplu taramada mekanik tanıma geçmezse ya
  da haritanın SHA-256'sı tutmazsa öğe "İnceleme gerekli" olur, `app.training.map_scan`); yalnız
  türü belirsiz kalan dosya yapay zekâya gidebilir. Bu yüzden "yapay zekâ gerekebilecek" sayısı
  yapay zekâya gönderilebilecek dosyaların üst sınırıdır (onay metni, §D58).
- **Başlatma (`start_map_scan`).** Çağıran iki aşamalı onayı tüketip çalıştırmayı (`kind=map`) açmış
  olur; burada dosya başına `queued` bir öğe açılır (harita satırı, yol, ipucu; haritanın SHA-256'sı
  ve kökü `checks_json["map"]`'te), olay `TRAINING_MAP_STARTED` yazılır ve harita yüklendiği haliyle
  `KnownDocuments/_egitim/haritalar/<run>.csv`'ye saklanır. Mekanik ve yapay zekâ adımları işçidedir
  (`app.training.map_scan`), parça parça.

Harita yazılmaz (harici aracın ürünüdür); kaynak dosyalar yalnız okunur (K10, K11). Olay dosya adı
ve yol taşımaz (CONVENTIONS §6). Fonksiyonlar işlemi commit etmez.
"""

from __future__ import annotations

import csv
import enum
import io
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ExampleFileRecord, TrainingItem, TrainingItemStatus, TrainingRun
from app.events import EventType, record_event
from app.i18n import N_, Translatable
from app.storage import DataLayout, write_unique
from app.storage.examples import ExampleLocator, listed_example_slug
from app.storage.map_paths import (
    ReferenceResolver,
    UnsafePathError,
    list_map_folder,
    normalize_reference,
    resolve_reference,
)
from app.training.known_types import KnownTypes
from app.training.mechanical import ExampleInventory
from app.training.placement import refresh_run

MAP_ENCODING = "utf-8-sig"
SLUG_COLUMN = "slug"
ROLE_COLUMN = "role"
SHA256_COLUMN = "sha256"
DEST_COLUMN = "dest"
OUTPUT_COLUMN = "output_relative_path"
FOLDER_COLUMN = "ornek_klasoru"
COLLECTION_COLUMN = "source_collection_path"
PATH_COLUMN = "path"
PATH_COLUMNS = (DEST_COLUMN, OUTPUT_COLUMN, FOLDER_COLUMN, COLLECTION_COLUMN, PATH_COLUMN)
"""Yol sütunları, öncelik sırasıyla: satırın yolu ilk dolu (kullanılabilir) sütundur."""
READ_COLUMNS = (SLUG_COLUMN, ROLE_COLUMN, SHA256_COLUMN, *PATH_COLUMNS)
"""Haritadan okunan sütunların tamamı; ötekiler (kişisel içerik taşıyabilecek
`personal_values_transcribed`, `note`, `author` dahil) okunmaz."""
REFERENCE_ROLE = "reference"
MAP_CHECK_KEY = "map"
"""`training_items.checks_json`'da harita satırının girdisinin anahtarı."""

FIRST_DATA_ROW = 2
SLUG_MAX_LENGTH = 64  # `training_items.hint_slug`
NAME_MAX_LENGTH = 255  # `training_items.original_name`
SAMPLE_LIMIT = 50

NO_PATH_COLUMN = N_(
    "Haritada yol sütunu yok: dest, output_relative_path, ornek_klasoru, "
    "source_collection_path ya da path gerekir."
)
NO_ROWS = N_("Haritada satır yok.")
NOT_UTF8 = N_("Harita UTF-8 metin değil; CSV'yi UTF-8 olarak kaydedin.")


def map_too_large(max_bytes: int) -> Translatable:
    """Bayt sınırını aşan haritanın mesajı (yüklemede ve gizli alanın açılmasında aynı)."""
    return Translatable(
        N_("Harita {limit} MB sınırını aşıyor."), limit=f"{max_bytes / (1024 * 1024):.0f}"
    )


class MapError(ValueError):
    """Harita bütünüyle reddedildi (okunamadı ya da sınırı aşıyor); mesaj kullanıcıya gösterilir,
    hiçbir şey yapılmaz."""


class MapRoot(enum.StrEnum):
    """Harita yolunun kökü: `DATA_DIR` ya da isteğe bağlı koleksiyon kökü."""

    DATA = "data"
    COLLECTION = "collection"


class SkipReason(enum.StrEnum):
    """Taramaya girmeyen harita satırının gerekçesi."""

    REFERENCE = "reference"
    NO_PATH = "no_path"
    NO_COLLECTION = "no_collection"
    UNSAFE_PATH = "unsafe_path"
    MISSING = "missing"
    EMPTY_FOLDER = "empty_folder"


SKIP_LABELS: dict[SkipReason, str] = {
    SkipReason.REFERENCE: N_("referans — örnek değil"),
    SkipReason.NO_PATH: N_("yol yok"),
    SkipReason.NO_COLLECTION: N_("koleksiyon kökü ayarlı değil"),
    SkipReason.UNSAFE_PATH: N_("güvensiz yol"),
    SkipReason.MISSING: N_("dosya yok"),
    SkipReason.EMPTY_FOLDER: N_("klasörde PDF, JPEG ya da PNG yok"),
}


class Outlook(enum.StrEnum):
    """Önizlemede bir dosyanın beklenen sonucu (tahmin)."""

    REGISTERED = "registered"  # aynı içerik bu türde zaten kayıtlı: atlanır
    MECHANICAL = "mechanical"  # türü belli: harita + mekanik kontrol, yapay zekâsız
    AI = "ai"  # türü belirsiz: mekanik tanınmazsa yapay zekâya gider


# --- okuma -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MapRow:
    """Haritanın okunan bir satırı. `paths` dolu yol sütunları (sütun, değer), öncelik sırasıyla."""

    number: int
    slug: str | None
    role: str | None
    sha256: str | None
    paths: tuple[tuple[str, str], ...]


def parse_map(content: bytes, *, max_bytes: int, max_rows: int) -> tuple[MapRow, ...]:
    """Haritayı okur (modül açıklaması); okunamıyor ya da sınırı aşıyorsa `MapError`. Boş satır
    atlanır ama numarası sayılır."""
    if len(content) > max_bytes:
        raise MapError(map_too_large(max_bytes))
    try:
        text = content.decode(MAP_ENCODING)
    except UnicodeDecodeError:
        raise MapError(NOT_UTF8) from None
    first_line = text.partition("\n")[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    rows: list[MapRow] = []
    try:
        header = next(reader, None)
        columns: dict[str, int] = {}
        for index, name in enumerate(header or ()):
            key = name.strip().casefold()
            if key in READ_COLUMNS:
                columns.setdefault(key, index)
        if not any(column in columns for column in PATH_COLUMNS):
            raise MapError(NO_PATH_COLUMN)
        for number, record in enumerate(reader, start=FIRST_DATA_ROW):
            if not any(cell.strip() for cell in record):
                continue
            if len(rows) >= max_rows:
                raise MapError(
                    Translatable(N_("Harita {limit} satır sınırını aşıyor."), limit=max_rows)
                )
            rows.append(_map_row(number, record, columns))
    except csv.Error:
        raise MapError(
            Translatable(N_("Harita CSV olarak okunamadı (satır {line})."), line=reader.line_num)
        ) from None
    if not rows:
        raise MapError(NO_ROWS)
    return tuple(rows)


def _map_row(number: int, record: list[str], columns: Mapping[str, int]) -> MapRow:
    def cell(column: str) -> str:
        index = columns.get(column)
        return record[index].strip() if index is not None and index < len(record) else ""

    return MapRow(
        number=number,
        slug=cell(SLUG_COLUMN) or None,
        role=cell(ROLE_COLUMN).casefold() or None,
        sha256=cell(SHA256_COLUMN).lower() or None,
        paths=tuple((column, cell(column)) for column in PATH_COLUMNS if cell(column)),
    )


# --- yol çözümü ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MapEntry:
    """Taranacak bir dosya. `reference` köke göreli POSIX yoldur, `path` çözülmüş yoludur.
    `in_place` dosya bir bilinen türün örnek klasöründe listeleniyorsa o türdür; `type_slug`
    dosyanın belli türüdür (yerindeki türü ya da haritanın bilinen türü) — yoksa tür belirsizdir."""

    row: int
    slug: str | None
    sha256: str | None
    column: str
    root: MapRoot
    reference: str
    name: str
    path: Path
    in_place: str | None
    type_slug: str | None

    @property
    def hint_slug(self) -> str | None:
        """Öğenin ipucu: haritanın slug'ı; yoksa yerindeki dosyanın türü."""
        slug = self.slug if self.slug and len(self.slug) <= SLUG_MAX_LENGTH else None
        return slug or self.in_place

    def as_check(self) -> dict[str, Any]:
        """`checks_json["map"]`: satırın girdisi (kişisel değer taşımaz)."""
        return {
            "root": self.root.value,
            "column": self.column,
            "slug": self.slug,
            "sha256": self.sha256,
            "in_place": self.in_place,
        }


@dataclass(frozen=True, slots=True)
class SkippedRow:
    """Taramaya girmeyen satır (ya da klasör satırının bir dosyası)."""

    row: int
    reason: SkipReason
    column: str | None = None
    value: str | None = None
    detail: str | None = None

    @property
    def label(self) -> str:
        text = SKIP_LABELS[self.reason]
        if not self.detail:
            return text
        return Translatable("{reason} ({detail})", reason=Translatable(text), detail=self.detail)


@dataclass(frozen=True, slots=True)
class MapPlan:
    """Haritanın çözümü: satır sayısı, taranacak dosyalar ve atlananlar."""

    rows: int
    entries: tuple[MapEntry, ...]
    skipped: tuple[SkippedRow, ...]

    def skipped_counts(self) -> dict[SkipReason, int]:
        counts = Counter(skipped.reason for skipped in self.skipped)
        return {reason: counts[reason] for reason in SkipReason if counts[reason]}


def plan_map(
    rows: Iterable[MapRow],
    layout: DataLayout,
    known: KnownTypes,
    *,
    collection_root: Path | None,
    max_files: int,
) -> MapPlan:
    """Satırların yollarını seçer ve çözer (modül açıklaması); diske yalnız bakar, yazmaz. Taranacak
    dosya sayısı `max_files`'ı aşarsa `MapError`."""
    entries: list[MapEntry] = []
    skipped: list[SkippedRow] = []
    resolvers = {MapRoot.DATA: ReferenceResolver(layout.root)}
    if collection_root is not None:
        resolvers[MapRoot.COLLECTION] = ReferenceResolver(collection_root)
    locator = ExampleLocator(layout)
    count = 0
    for row in rows:
        count += 1
        if row.role == REFERENCE_ROLE:
            skipped.append(SkippedRow(row.number, SkipReason.REFERENCE))
            continue
        chosen = _choose_path(row, collection_root)
        if isinstance(chosen, SkipReason):
            skipped.append(SkippedRow(row.number, chosen))
            continue
        column, value = chosen
        # `_choose_path` koleksiyon kökü yokken o sütunu seçmez.
        root = MapRoot.COLLECTION if column == COLLECTION_COLUMN else MapRoot.DATA
        try:
            reference = normalize_reference(value)
            path = resolvers[root](reference)
        except UnsafePathError as exc:
            skipped.append(SkippedRow(row.number, SkipReason.UNSAFE_PATH, column, value, str(exc)))
            continue
        if column != FOLDER_COLUMN:
            if not path.is_file():
                skipped.append(SkippedRow(row.number, SkipReason.MISSING, column, value))
                continue
            entries.append(_entry(row, column, root, reference, path, locator, known))
        else:
            if not path.is_dir():
                skipped.append(
                    SkippedRow(row.number, SkipReason.MISSING, column, value, "klasör yok")
                )
                continue
            files = list_map_folder(path)
            if not files:
                skipped.append(SkippedRow(row.number, SkipReason.EMPTY_FOLDER, column, value))
                continue
            for file in files:
                try:
                    file_reference = normalize_reference(f"{reference}/{file.name}")
                except UnsafePathError as exc:
                    skipped.append(
                        SkippedRow(row.number, SkipReason.UNSAFE_PATH, column, value, str(exc))
                    )
                    continue
                entries.append(_entry(row, column, root, file_reference, file, locator, known))
        if len(entries) > max_files:
            raise MapError(
                Translatable(N_("Harita {limit} dosya sınırını aşıyor."), limit=max_files)
            )
    return MapPlan(count, tuple(entries), tuple(skipped))


def _choose_path(row: MapRow, collection_root: Path | None) -> tuple[str, str] | SkipReason:
    """Satırın yol sütunu: öncelik sırasıyla ilk dolu sütun; koleksiyon sütunu yalnız kök ayarlıysa.
    Kullanılabilir sütun yoksa gerekçe."""
    collection_only = False
    for column, value in row.paths:
        if column == COLLECTION_COLUMN and collection_root is None:
            collection_only = True
            continue
        return column, value
    return SkipReason.NO_COLLECTION if collection_only else SkipReason.NO_PATH


def _entry(
    row: MapRow,
    column: str,
    root: MapRoot,
    reference: str,
    path: Path,
    locator: ExampleLocator,
    known: KnownTypes,
) -> MapEntry:
    # `path` çözülmüştür: dosya satırında `ReferenceResolver`, klasör satırında çözülmüş klasörün
    # sembolik bağ olmayan düz dosyası (`list_map_folder`).
    in_place = locator.slug_of(path) if root is MapRoot.DATA else None
    if in_place not in known:
        in_place = None
    type_slug = in_place or (row.slug if row.slug in known else None)
    return MapEntry(
        row=row.number,
        slug=row.slug,
        sha256=row.sha256,
        column=column,
        root=root,
        reference=reference,
        name=path.name[:NAME_MAX_LENGTH],
        path=path,
        in_place=in_place,
        type_slug=type_slug,
    )


# --- önizleme --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MapPreview:
    """Önizlemenin sayıları (modül açıklaması). `ai_possible` yapay zekâya gönderilebilecek dosya
    sayısının üst sınırıdır; `samples` ilk `SAMPLE_LIMIT` atlanan satırdır."""

    rows: int
    files: int
    skipped: tuple[tuple[SkipReason, int], ...]
    registered: int
    mechanical: int
    ai_possible: int
    samples: tuple[SkippedRow, ...]

    @property
    def skipped_total(self) -> int:
        return sum(count for _, count in self.skipped)

    def as_event_data(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "files": self.files,
            "skipped": {reason.value: count for reason, count in self.skipped},
            "registered": self.registered,
            "mechanical": self.mechanical,
            "ai_possible": self.ai_possible,
        }


def preview_map(
    session: Session, plan: MapPlan, known: KnownTypes, *, inventory: ExampleInventory | None
) -> MapPreview:
    """Haritanın önizlemesi (modül açıklaması); veritabanını yalnız okur, dosya okumaz."""
    outlooks = Counter(map_outlooks(session, plan, known, inventory=inventory))
    return MapPreview(
        rows=plan.rows,
        files=len(plan.entries),
        skipped=tuple(plan.skipped_counts().items()),
        registered=outlooks[Outlook.REGISTERED],
        mechanical=outlooks[Outlook.MECHANICAL],
        ai_possible=outlooks[Outlook.AI],
        samples=plan.skipped[:SAMPLE_LIMIT],
    )


def map_outlooks(
    session: Session, plan: MapPlan, known: KnownTypes, *, inventory: ExampleInventory | None
) -> list[Outlook]:
    """Her dosyanın beklenen sonucu (`plan.entries` sırasıyla). Kayıtlar etkin (örneklerden
    çıkarılmamış) örnek kayıtlarıdır; SHA-256 dizini `inventory` ile genişler."""
    names: dict[tuple[str, str], str] = {}
    types_by_sha: defaultdict[str, set[str]] = defaultdict(set)
    for slug, name, sha256 in session.execute(
        select(ExampleFileRecord.type_slug, ExampleFileRecord.name, ExampleFileRecord.sha256).where(
            ExampleFileRecord.removed_at.is_(None)
        )
    ).tuples():
        names[(slug, name)] = sha256
        if slug in known:
            types_by_sha[sha256].add(slug)
    return [_outlook(entry, known, names, types_by_sha, inventory) for entry in plan.entries]


def _outlook(
    entry: MapEntry,
    known: KnownTypes,
    names: Mapping[tuple[str, str], str],
    types_by_sha: Mapping[str, set[str]],
    inventory: ExampleInventory | None,
) -> Outlook:
    if entry.in_place is not None:
        recorded = names.get((entry.in_place, entry.name))
        if (
            recorded is not None
            and entry.sha256 in (None, recorded)
            and entry.slug in (None, entry.in_place)
        ):
            return Outlook.REGISTERED
        return Outlook.MECHANICAL
    recorded_types = types_by_sha.get(entry.sha256, set()) if entry.sha256 else set()
    if entry.type_slug is not None:
        return Outlook.REGISTERED if entry.type_slug in recorded_types else Outlook.MECHANICAL
    if len(recorded_types) == 1:
        return Outlook.REGISTERED
    if entry.sha256 is not None:
        listed = inventory.slugs(entry.sha256) if inventory is not None else frozenset()
        if len(recorded_types | {slug for slug in listed if slug in known}) == 1:
            return Outlook.MECHANICAL
    return Outlook.AI


# --- başlatma --------------------------------------------------------------------------------


def start_map_scan(
    session: Session,
    layout: DataLayout,
    run: TrainingRun,
    plan: MapPlan,
    preview: MapPreview,
    *,
    content: bytes,
    actor: str,
) -> list[TrainingItem]:
    """Onaylanmış taramayı kuyruğa koyar: `run` (`kind=map`) için dosya başına `queued` öğe,
    `TRAINING_MAP_STARTED` ve haritanın `_egitim/haritalar/<run>.csv` kopyası (en son yazılır: işlem
    daha önce düşerse dosya yazılmaz). Commit etmez; dosya yazıldıktan sonra işlem geri alınırsa
    harita kopyası kalır (silme yok) ve aynı numarayı alan sonraki çalıştırmanın haritası `-2` eki
    alır."""
    items = [
        TrainingItem(
            run=run,
            row_number=entry.row,
            original_name=entry.name,
            source_ref=entry.reference,
            hint_slug=entry.hint_slug,
            status=TrainingItemStatus.QUEUED.value,
            checks_json={MAP_CHECK_KEY: entry.as_check()},
        )
        for entry in plan.entries
    ]
    session.add_all(items)
    refresh_run(session, run)
    record_event(
        session,
        EventType.TRAINING_MAP_STARTED,
        actor=actor,
        message=f"Harita ile toplu tarama başladı: {preview.files} dosya.",
        data={"run_id": run.id} | preview.as_event_data(),
    )
    target = layout.training_map_path(run.id)
    write_unique(target.parent, target.name, content)
    return items


def item_source_path(layout: DataLayout, item: TrainingItem) -> Path | None:
    """Öğenin yerleştirilecek dosyası: eğitim kopyası (`_egitim/gelen`) ya da (kopyası olmayan
    harita öğesinde) türün örnek klasöründe hâlâ listelenen yerindeki dosya; ikisi de yoksa `None`.
    İK'nın "Türe yerleştir"i bunu kullanır."""
    if item.staged_path is not None:
        return layout.resolve(item.staged_path)
    check = (item.checks_json or {}).get(MAP_CHECK_KEY)
    if not isinstance(check, dict) or check.get("root") != MapRoot.DATA or not item.source_ref:
        return None
    try:
        path = resolve_reference(layout.root, item.source_ref)
    except UnsafePathError:
        return None
    return path if listed_example_slug(layout, path) is not None else None
