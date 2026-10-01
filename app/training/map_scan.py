"""Toplu taramanın işçi adımı — harita öğesinin mekanik taraması (PRD 11.9.5, PLAN.md §C87).

`app.training.map_import.start_map_scan` dosya başına `queued` bir öğe açar; işçinin boş-zaman işi
(`TrainingMapJob`, `app.worker.idle`) öğeleri **birer birer** tarar: yükleme işi her zaman önce
gelir ve büyük bir harita işçiyi uzun kilitlemez. Birim üç adımdır (`run_idle_unit`): öğenin
girdisini oku, dosyayı veritabanı oturumu açık değilken oku (`load_map_file`: yol yeniden, güvenle
çözülür), sonucu yaz (`scan_map_item`). Yapay zekâ çağrılmaz; mekanik tanınmayan ve türü belirsiz
öğe `ai_pending` olur ve onu eğitim sınıflandırması (11.9.3, `app.training.classification`) inceler.

`scan_map_item` sırasıyla:

1. **Dosya.** Bulunamayan, güvensiz yollu ya da örnek olamayan (`check_content`: PDF/JPEG/PNG,
   okunabilir, boyut sınırı) dosyanın öğesi `failed` ("Hatalı") olur.
2. **Yerindeki dosya.** Dosya bir bilinen türün örnek klasöründe listeleniyorsa türü o
   klasörünkidir; haritanın slug'ı başka bir türse öğe `review` olur (çelişki İK'nındır).
3. **Haritanın SHA-256'sı** dosyanınkiyle tutmuyorsa öğe `review` olur — yapay zekâya gitmez, not
   "haritadaki SHA-256 dosyayla tutmuyor".
4. **Zaten kayıtlı.** Aynı içerik dosyanın belli türünde etkin bir örnekse öğe `skipped` olur
   (yeniden tarama); kopya yazılmaz.
5. **Mekanik tanıma** (`app.training.mechanical.recognize`; ipucu haritanın slug'ı ya da yerindeki
   dosyanın türü). Tanınan öğe `method=mechanical`, etiketsiz yerleşir: yerindeki dosya
   kopyalanmadan kaydedilir, öteki dosya önce `_egitim/gelen/<run>/<item>.<ext>`'e kopyalanır (K10,
   K11; kaynak dosya değişmez). Tanınmazsa: türü belli öğe `review` olur ("harita + mekanik kontrol
   yeter", insan kararı; yapay zekâya gitmez), türü belirsiz öğe `ai_pending` olur.

Böylece yapay zekâya yalnız önizlemede "yapay zekâ gerekebilecek" sayılan öğeler gidebilir (onay
metnindeki üst sınır, §D58). Yerindeki öğe yapay zekâya hiç gitmez: kopyası yoktur.

Deneme sınırında (`WORKER_MAX_ATTEMPTS`) hata veren ya da işleyicisi yarıda kalan öğe `failed` olur.
Not ve olaylar dosya adı ve kişisel değer taşımaz (CONVENTIONS §6). Çalışan verisine dokunulmaz.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.ai.provider import AnalysisProvider
from app.config import Settings
from app.db.models import (
    ExampleFileRecord,
    TrainingItem,
    TrainingItemStatus,
    TrainingMethod,
    TrainingRun,
    TrainingRunKind,
)
from app.storage import DataLayout
from app.storage.examples import listed_example_slug
from app.storage.map_paths import UnsafePathError, resolve_reference
from app.training.known_types import KnownTypes, load_known_types
from app.training.map_import import (
    MAP_CHECK_KEY,
    SKIP_LABELS,
    SLUG_MAX_LENGTH,
    MapRoot,
    SkipReason,
)
from app.training.mechanical import (
    ExampleInventory,
    hint_label,
    load_example_inventory,
    recognize,
)
from app.training.placement import (
    ItemNotPlaceableError,
    check_content,
    fail_item,
    leave_unplaced,
    place_example,
    refresh_run,
    write_staged_copy,
)
from app.worker.idle import IdleContext, IdleTable, run_idle_unit

JOB_NAME = "egitim-haritasi"
SHA_MISMATCH = "haritadaki SHA-256 dosyayla tutmuyor"
NOT_TO_AI = "türü haritadan belli olduğu için yapay zekâya gönderilmedi"
ERROR_NOTE = "Harita taraması yapılamadı ({error}); denemeler tükendi"
ABANDONED_NOTE = "Harita taraması yarıda kaldı; denemeler tükendi"


# --- girdi ve dosya --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MapScanSource:
    """Taranacak öğenin oturumdan bağımsız girdisi: kök, köke göreli yol ve dosya sınırı."""

    item_id: int
    root: MapRoot | None
    reference: str | None


@dataclass(frozen=True, slots=True)
class MapFile:
    """Okunan dosya: çözülmüş yolu ve içeriği (sınırın bir baytı ötesine kadar) ya da okunamamanın
    Türkçe gerekçesi (`problem`)."""

    path: Path | None
    content: bytes | None = field(default=None, repr=False)
    problem: str | None = None


def read_map_source(item: TrainingItem) -> MapScanSource:
    check = (item.checks_json or {}).get(MAP_CHECK_KEY)
    root = check.get("root") if isinstance(check, dict) else None
    return MapScanSource(
        item_id=item.id,
        root=MapRoot(root) if root in tuple(MapRoot) else None,
        reference=item.source_ref,
    )


def load_map_file(source: MapScanSource, *, layout: DataLayout, settings: Settings) -> MapFile:
    """Öğenin dosyasını okur: yol kökün altında yeniden, güvenle çözülür (harita yüklendikten sonra
    bağ değişmiş olabilir); en çok `max_upload_file_size_bytes + 1` bayt okunur. Veritabanına
    dokunmaz."""
    if source.root is None or not source.reference:
        return MapFile(None, problem="haritadaki yol kaydı yok")
    base = layout.root if source.root is MapRoot.DATA else settings.training_collection_dir
    if base is None:
        return MapFile(None, problem=SKIP_LABELS[SkipReason.NO_COLLECTION])
    try:
        path = resolve_reference(base, source.reference)
    except UnsafePathError as exc:
        return MapFile(None, problem=f"{SKIP_LABELS[SkipReason.UNSAFE_PATH]} ({exc})")
    if not path.is_file():
        return MapFile(path, problem=SKIP_LABELS[SkipReason.MISSING])
    try:
        with path.open("rb") as handle:
            content = handle.read(settings.max_upload_file_size_bytes + 1)
    except OSError:
        return MapFile(path, problem="dosya okunamadı")
    return MapFile(path, content)


# --- tarama ----------------------------------------------------------------------------------


def scan_map_item(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    item: TrainingItem,
    loaded: MapFile,
    *,
    inventory: ExampleInventory | None,
    max_bytes: int,
) -> TrainingItemStatus:
    """`queued` harita öğesini tarar (modül açıklaması) ve öğenin yeni durumunu döner; commit
    etmez. Öğe `queued` değilse `ItemNotPlaceableError`."""
    if item.status != TrainingItemStatus.QUEUED:
        raise ItemNotPlaceableError(f"Öğe {item.id} taranmayı beklemiyor: {item.status}")
    row = f"harita satırı {item.row_number}"
    if loaded.problem is not None or loaded.path is None or loaded.content is None:
        fail_item(session, item, note=f"Taranamadı ({row}): {loaded.problem or 'dosya yok'}")
        return TrainingItemStatus.FAILED
    path, content = loaded.path, loaded.content
    if not check_content(item, item.original_name, content, max_bytes=max_bytes):
        refresh_run(session, item.run)
        return TrainingItemStatus.FAILED

    check = dict((item.checks_json or {}).get(MAP_CHECK_KEY) or {})
    map_slug, map_sha256 = check.get("slug"), check.get("sha256")
    root = check.get("root")
    in_place = listed_example_slug(layout, path) if root == MapRoot.DATA else None
    if in_place not in known:
        in_place = None
    check["in_place"] = in_place
    item.checks_json = {MAP_CHECK_KEY: check}
    # Dosyanın belli türü: yerindeki dosyanın klasörü ya da haritanın bilinen türü. Bilinmeyen slug
    # ipucu olarak görünür ama tür sayılmaz (mekanik onu yok sayar).
    type_slug = in_place or (map_slug if map_slug in known else None)
    map_hint = map_slug if map_slug and len(map_slug) <= SLUG_MAX_LENGTH else None

    if in_place is not None and map_slug and map_slug != in_place:
        item.hint_slug = map_hint
        note = (
            f"İnceleme gerekli ({row}): haritadaki tür `{map_slug}`, dosya `{in_place}` örnek "
            "klasöründe"
        )
        return _review(session, item, note, in_place)
    item.hint_slug = type_slug or map_hint
    if map_sha256 is not None and map_sha256 != item.sha256:
        return _review(session, item, f"İnceleme gerekli ({row}): {SHA_MISMATCH}", type_slug)
    if type_slug is not None and _registered(session, item.sha256, type_slug):
        note = f"Mekanik: {hint_label(item)} → `{type_slug}`; SHA-256 örnek kaydında"
        placement = place_example(
            session,
            layout,
            known,
            item,
            type_slug,
            method=TrainingMethod.MECHANICAL,
            note=note,
            source=path,
        )
        return placement.status

    if in_place is None:
        write_staged_copy(layout, item, content)
    recognition = recognize(
        session, known, item, content, inventory=inventory, hint_sha256=map_sha256
    )
    item.checks_json = {MAP_CHECK_KEY: check, **recognition.checks}
    if recognition.slug is None:
        if type_slug is not None:
            return _review(session, item, f"{recognition.note}; {NOT_TO_AI}", type_slug)
        item.status = TrainingItemStatus.AI_PENDING.value
        item.note = recognition.note
        refresh_run(session, item.run)
        return TrainingItemStatus.AI_PENDING
    if in_place is not None and recognition.slug != in_place:  # ipucu yerindeki tür: olmamalı
        return _review(session, item, f"{recognition.note}; {NOT_TO_AI}", in_place)
    placement = place_example(
        session,
        layout,
        known,
        item,
        recognition.slug,
        method=TrainingMethod.MECHANICAL,
        note=recognition.note,
        source=path if in_place is not None else None,
    )
    return placement.status


def _review(
    session: Session, item: TrainingItem, note: str, slug: str | None
) -> TrainingItemStatus:
    leave_unplaced(
        session,
        item,
        TrainingItemStatus.REVIEW,
        note=note,
        method=TrainingMethod.MECHANICAL,
        slug=slug,
    )
    return TrainingItemStatus.REVIEW


def _registered(session: Session, sha256: str | None, slug: str) -> bool:
    return sha256 is not None and (
        session.scalar(
            select(ExampleFileRecord.id)
            .where(
                ExampleFileRecord.sha256 == sha256,
                ExampleFileRecord.type_slug == slug,
                ExampleFileRecord.removed_at.is_(None),
            )
            .limit(1)
        )
        is not None
    )


# --- boş-zaman işi ---------------------------------------------------------------------------


def _abandoned(session: Session, item: TrainingItem) -> None:
    """İşleyicisi yarıda kalmış ve denemesi tükenmiş öğe (`IdleTable.abandoned`): durum `failed`'ı
    çerçeve yazdı; not ve çalıştırma sayaçları burada."""
    fail_item(session, item, note=ABANDONED_NOTE)


TRAINING_MAP_ITEMS = IdleTable(
    TrainingItem,
    pending=lambda: and_(
        TrainingItem.status == TrainingItemStatus.QUEUED.value,
        TrainingItem.run_id.in_(
            select(TrainingRun.id).where(TrainingRun.kind == TrainingRunKind.MAP.value)
        ),
    ),
    failed={"status": TrainingItemStatus.FAILED.value},
    abandoned=_abandoned,
)
"""Taranmayı bekleyen (`queued`) harita öğeleri; deneme tükenince `failed`."""


class _InventoryCache:
    """Örnek envanterini dosya değişmedikçe yeniden okumaz (her öğede 1–2 MB'lık CSV okunmasın)."""

    def __init__(self) -> None:
        self._key: tuple[int, int] | None = None
        self._inventory: ExampleInventory | None = None

    def load(self, layout: DataLayout) -> ExampleInventory | None:
        try:
            stat = layout.example_inventory_path.stat()
        except FileNotFoundError:
            self._key, self._inventory = None, None
            return None
        key = (stat.st_mtime_ns, stat.st_size)
        if key != self._key:
            self._inventory = load_example_inventory(layout)
            self._key = key
        return self._inventory


class TrainingMapJob:
    """İşçinin boş-zaman işi: sıradaki `queued` harita öğesini tarar (`IdleJob`). Sağlayıcıyı
    çağırmaz."""

    name = JOB_NAME

    def __init__(self) -> None:
        self._inventory = _InventoryCache()

    def run_one(self, context: IdleContext) -> bool:
        layout, settings = context.layout, context.settings

        def read(session: Session, item: TrainingItem) -> MapScanSource:
            return read_map_source(item)

        def call(provider: AnalysisProvider, source: MapScanSource) -> MapFile:
            return load_map_file(source, layout=layout, settings=settings)

        def write(session: Session, item: TrainingItem, loaded: MapFile) -> None:
            scan_map_item(
                session,
                layout,
                load_known_types(session),
                item,
                loaded,
                inventory=self._inventory.load(layout),
                max_bytes=settings.max_upload_file_size_bytes,
            )

        def failed(session: Session, item: TrainingItem, final: bool) -> None:
            if not final:
                return  # öğe `queued` kalır ve yeniden denenir
            # Çerçeve bu kancayı hatanın `except` bloğunda çağırır; yalnız türü yazılır.
            active = sys.exception()
            error = type(active).__name__ if active is not None else "Exception"
            fail_item(session, item, note=ERROR_NOTE.format(error=error))

        return run_idle_unit(
            context,
            TRAINING_MAP_ITEMS,
            name=self.name,
            read=read,
            call=call,
            write=write,
            failed=failed,
        )
