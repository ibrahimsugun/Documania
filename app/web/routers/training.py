"""Eğitim modu sekmesi (PRD 11.9.1, 10.1.1 menü satırı; PLAN.md §C86 "Sekme").

Eğitim modu yalnız bilinen belgelerin (katalog + hazır önerilen türler) örneklerini besler: bu
sekmeden yüklenen dosya hiçbir çalışan, kişi eşleştirmesi, kuyruk öğesi, yükleme partisi ya da çıktı
belgesi oluşturmaz (`app.training`).

- **Yükleme (`POST /training`).** Çoklu dosya (PDF/JPEG/PNG) ve isteğe bağlı "Beklenen tür"
  (bilinen türlerden biri; mekanik tanımanın ipucu). Ad yükleme sayfasının kuralıyla doğrulanır
  (`app.web.routers.uploads._validated_name`); biri geçmezse ya da beklenen tür bilinmiyorsa hiçbir
  şey yazılmaz (400). Her dosya sınırın bir baytı ötesine kadar okunur (devasa dosya belleğe
  tümüyle alınmaz); sınırı aşan, boş, bozuk ya da desteklenmeyen dosya öğesi `failed` olur ("Hatalı"
  süzgeci). Mekanik tanıma istek içinde çalışır (`stage_and_recognize`); tanınmayan öğe
  `ai_pending` kalır ve yapay zekâ incelemesini işçinin boş-zaman işi yapar (11.9.3).
- **Sonuçlar (`GET /training`, `GET /training/items`).** Son çalıştırmalar ve öğe tablosu (dosya,
  beklenen tür, sonuç türü, yöntem, durum, not, etiket); süzgeçler: AI kararı, Yerleştirilemedi,
  Çelişki, Mekanik, Hatalı. "AI kararı" etiketli örneğin satırında ⚠ ikonu ve "Elle kontrol
  gerekli" açıklaması durur. Kararı sistemde bekleyen (`queued`, `ai_pending`) öğe varken sonuç
  bölümü HTMX ile yoklanır (`/training/items`). Sağlayıcı ayarsızsa sayfa bunu söyler: öğeler
  `ai_pending` bekler.
- **Türe yerleştir (`POST /training/items/{id}/place`).** `unplaced` ya da `conflict` öğede İK bir
  bilinen tür seçer; öğe o türe `method=manual` ile yerleşir, etiket `verified`, olay İK'nın
  kullanıcı adıyla (`place_example`). Aynı içerik o türde ya da başka türde zaten örnekse
  yerleştirmenin kuralı geçerlidir (`skipped`, `conflict`).
- **Bilinen belgeler (`GET /training/known`, `/training/known/{slug}`).** Bütün bilinen türler,
  örnek sayıları ve etiketli ("AI kararı", doğrulanmış) örnek sayıları; tür ayrıntısında örnek
  listesi, kaydı (yöntem, etiket, not) ve görüntüsü. Katalog dışı türün örneği
  `/document-types/{slug}/examples/...`'ten açılmadığı (orada yalnız katalog türleri var) için
  örnek dosyası `/training/known/{slug}/examples/{name}`'den verilir: tür bilinen türse ve ad türün
  örnek listesinde varsa (`example_path`); yol istekteki addan kurulmaz. Yanıt `nosniff`'tir.
- **Etiket kararı (11.9.4; PLAN.md §C86 "Etiket kararı", §D58).** Kaydı olan örnekte İK üç karardan
  birini verir (`app.training.decisions`): **Doğrula** (`POST /training/examples/verify`; tek ya da
  toplu seçim, tek adım) "AI kararı" etiketini `verified` yapar; **Başka türe taşı**
  (`POST /training/examples/{id}/move…`) ve **Örneklerden çıkar**
  (`POST /training/examples/{id}/remove…`) iki aşamalı onaylıdır: `…/confirm` birinci onay metnini
  gösterir (hiçbir şey değişmez), `…/prepare` ikinci metni ve tek kullanımlık belirteci verir
  (`app.web.confirm`; `Operation.TRAINING_MOVE`, `TRAINING_REMOVE`), asıl istek belirteçle gelir.
  Belirteç örneğe, onun türüne ve adına ve (taşımada) hedef türe bağlıdır: örnek bu arada
  değiştiyse belirteç geçmez. Onay metinleri §D58'den birebirdir ve burada durur (REANALYZE
  emsali); işlemler K16'nın dışındadır, PRD §20.6 değişmez. Kaydı olmayan örnek (eğitimden önce
  konmuş, tür sayfasından el ile yüklenmiş) listelenir ama karar almaz.
- **Harita yükle (11.9.5; PLAN.md §C87, §D58).** `POST /training/maps` CSV haritasını okur ve
  önizlemesini gösterir: satır, dosya, atlanan (gerekçe sayılarıyla), zaten kayıtlı, mekanik hazır
  ve yapay zekâ gerekebilecek sayıları (`app.training.map_import`); önizleme hiçbir şey yazmaz.
  Harita sonraki adımlara sayfada taşınır (sıkıştırılmış, gizli alan): sunucu arada hiçbir şey
  saklamaz. "Toplu taramayı başlat" iki aşamalıdır: `…/confirm` birinci onay metnini gösterir,
  `…/prepare` ikinci metni (yapay zekâya gönderilebilecek dosyaların üst sınırı) ve haritaya bağlı
  belirteci verir (`Operation.TRAINING_MAP`), `…/start` belirteçle çalıştırmayı (`kind=map`) ve
  dosya başına öğeyi açar, `TRAINING_MAP_STARTED`'ı yazar ve haritayı
  `_egitim/haritalar/<run>.csv`'ye saklar. Belirteç haritanın adına, içeriğine ve iki sayıya
  bağlıdır: harita ya da sayılar bu arada değiştiyse geçmez. Taramayı işçi parça parça yürütür
  (`app.training.map_scan`); ilerleme sonuç bölümünün yoklamasıyla görünür. Haritanın "İnceleme
  gerekli" öğesi de "Türe yerleştir"i bekler; kopyası olmayan (yerindeki) öğe yerindeki dosyadan
  yerleşir.
- **Temizlik (11.9.6; PLAN.md §C92-c, §D61-b).** "Türe yerleştir"i bekleyen öğe (`unplaced`,
  `conflict`, `review`) `POST /training/items/{id}/dismiss` ile isteğe bağlı notla (en çok 200,
  `<input>`) tek adımda yoksayılır, `…/restore` ile `unplaced`'e döner (`app.training.cleanup`).
  Öğe tablosu yoksayılanları varsayılan olarak göstermez; `?show=dismissed` yalnız onları gösterir.
  Çalıştırma `POST /training/runs/{id}/archive` ile arşivlenir, `…/restore` ile geri alınır (ikisi
  tek adım): arşivli çalıştırma listeden kalkar, öğeleri tablodan ve üst sayaçlardan (dosya sayısı,
  bekleyen) düşer; `?archived=1` arşivli çalıştırmaları ve öğelerini gösterir. Seçili çalıştırma
  (`?run=`) arşivli olsa da öğelerini gösterir. Öğeler, örnekler ve `example_files` değişmez;
  işlemler K16'nın dışındadır (§D58), olaylar kullanıcı adıyla yazılır.

Sekme belge içeriğini değiştirmez (10.9.1, K11, K17): yalnız kopyalar, kaydeder ve gösterir. Ekranda
kişisel değer yalnız dosya adındadır (CONVENTIONS §6); notlar ve dökümler kişisel değer taşımaz.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.ai.provider import ProviderConfigError, create_provider
from app.config import Settings, get_settings
from app.db.models import (
    ExampleFileRecord,
    ExampleLabel,
    ExampleMethod,
    TrainingItem,
    TrainingItemStatus,
    TrainingMethod,
    TrainingRun,
    TrainingRunKind,
    TrainingRunStatus,
)
from app.db.session import get_session
from app.i18n import N_, gettext
from app.storage import ContentMismatchError, DataLayout
from app.storage.examples import example_path, list_examples
from app.training import (
    DISMISSABLE_STATUSES,
    PENDING_STATUSES,
    CleanupError,
    CleanupNoteError,
    ExampleDecisionError,
    ItemNotPlaceableError,
    KnownType,
    KnownTypes,
    MapError,
    MapPlan,
    MapPreview,
    UnknownTypeError,
    archive_run,
    check_move,
    check_remove,
    create_run,
    dismiss_item,
    item_source_path,
    load_example_inventory,
    load_known_types,
    move_example,
    parse_map,
    place_example,
    plan_map,
    preview_map,
    remove_example,
    restore_item,
    restore_run,
    stage_and_recognize,
    start_map_scan,
    verify_examples,
)
from app.training.map_import import SKIP_LABELS, map_too_large
from app.web.auth import PanelUser, require_panel_user
from app.web.confirm import (
    CONFIRMATION_REFUSED,
    ConfirmationRefusedError,
    Operation,
    confirm_operation,
    issue_confirmation,
)
from app.web.routers.uploads import _validated_name, get_layout
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(tags=["training"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]
DbSession = Annotated[Session, Depends(get_session)]
Layout = Annotated[DataLayout, Depends(get_layout)]
AppSettings = Annotated[Settings, Depends(get_settings)]

TRAINING_PATH = "/training"
ITEMS_PATH = "/training/items"
KNOWN_PATH = "/training/known"
EXAMPLES_PATH = "/training/examples"
MAPS_PATH = "/training/maps"
RUNS_PATH = "/training/runs"
RUN_LIMIT = 20
ITEM_LIMIT = 200

NO_FILE_MESSAGE = N_("Yüklenecek dosya seçilmedi.")
UNKNOWN_HINT_MESSAGE = N_("Beklenen tür bilinen türlerden biri değil; listeden seçin.")
UNKNOWN_TYPE_MESSAGE = N_("Seçilen tür bilinen türlerden biri değil; listeden seçin.")
ITEM_NOT_FOUND = N_("Eğitim öğesi bulunamadı.")
NOT_MANUALLY_PLACEABLE = N_(
    "Bu öğe elle yerleştirilemez: yalnız Yerleştirilemedi, Çelişki ya da İnceleme gerekli "
    "durumundaki öğe türe yerleştirilir."
)
FILE_MISSING = N_("Öğenin eğitim kopyası okunamadı; yerleştirilmedi.")
TYPE_NOT_FOUND = N_("Bilinen tür bulunamadı.")
EXAMPLE_NOT_FOUND = N_("Örnek bulunamadı.")
MANUAL_CHECK_TEXT = N_("Elle kontrol gerekli")
REMOVED_LABEL_TEXT = N_("Örneklerden çıkarıldı")
EXAMPLE_RECORD_NOT_FOUND = N_("Eğitim örneği bulunamadı.")
MOVE_FAILED = N_("Örnek dosyası taşınamadı; hiçbir şey değişmedi.")
NO_MAP_MESSAGE = N_("Yüklenecek harita seçilmedi.")
MAP_NOT_CSV = N_("Harita .csv uzantılı bir CSV dosyası olmalı.")
MAP_DATA_INVALID = N_("Harita verisi okunamadı; haritayı yeniden yükleyin.")
MAP_EMPTY = N_("Haritada taranacak dosya yok; tarama başlatılmadı.")
MAP_SAVE_FAILED = N_("Harita saklanamadı; tarama başlatılmadı.")
RUN_NOT_FOUND = N_("Eğitim çalıştırması bulunamadı.")

# Etiket kararının iki aşamalı onay metinleri (11.9.4) — PLAN.md §D58'den BİREBİR; §20.6'nın
# dışındadır (K16 dışı, REANALYZE emsali). `tests/web/test_training_decisions.py` §D58 ile
# karşılaştırır. Yer tutucular çalışma zamanında doldurulur (`_fill`).
FILE_PLACEHOLDER = "<Dosya>"
OLD_TYPE_PLACEHOLDER = "<Eski tür>"
NEW_TYPE_PLACEHOLDER = "<Yeni tür>"
TYPE_PLACEHOLDER = "<Tür>"
MOVE_FIRST_CONFIRMATION = N_(
    "<Dosya> örneğini <Eski tür> türünden <Yeni tür> türüne taşımak üzeresiniz. Emin misiniz?"
)
MOVE_SECOND_CONFIRMATION = N_(
    "Örnek artık <Yeni tür> türünün örneklerinde durur ve o türün açıklama üretimini etkiler. "
    "Son kararınız mı?"
)
REMOVE_FIRST_CONFIRMATION = N_(
    "<Dosya> örneğini <Tür> örneklerinden çıkarmak üzeresiniz. Emin misiniz?"
)
REMOVE_SECOND_CONFIRMATION = N_(
    "Dosya silinmez, eğitim arşivine taşınır ve bu türün açıklama üretimine artık girmez. "
    "Son kararınız mı?"
)
# Toplu taramanın iki aşamalı onay metinleri (11.9.5) — PLAN.md §D58'den BİREBİR. `<K>` yapay
# zekâya gönderilebilecek dosyaların üst sınırıdır (önizlemenin "yapay zekâ gerekebilecek" sayısı).
MAP_PLACEHOLDER = "<Harita>"
FILES_PLACEHOLDER = "<N>"
AI_FILES_PLACEHOLDER = "<K>"
MAP_FIRST_CONFIRMATION = N_("<Harita> haritasındaki <N> dosyayı taramak üzeresiniz. Emin misiniz?")
MAP_SECOND_CONFIRMATION = N_("En çok <K> dosya yapay zekâya gönderilebilir. Son kararınız mı?")

MANUALLY_PLACEABLE = frozenset(
    {TrainingItemStatus.UNPLACED, TrainingItemStatus.CONFLICT, TrainingItemStatus.REVIEW}
)
"""İK'nın "Türe yerleştir"ini bekleyen durumlar (11.9.1; haritanın `review`'u 11.9.5). Kararı
sistemde bekleyen öğe (`queued`, `ai_pending`) elle yerleştirilmez: işçinin taramasıyla ve
incelemesiyle yarışmasın."""

STATUS_LABELS: dict[str, str] = {
    TrainingItemStatus.QUEUED: N_("Sırada"),
    TrainingItemStatus.PLACED: N_("Yerleşti"),
    TrainingItemStatus.AI_PENDING: N_("Yapay zekâ incelemesi bekliyor"),
    TrainingItemStatus.SKIPPED: N_("Zaten örnek"),
    TrainingItemStatus.FAILED: N_("Hatalı"),
    TrainingItemStatus.UNPLACED: N_("Yerleştirilemedi"),
    TrainingItemStatus.CONFLICT: N_("Çelişki"),
    TrainingItemStatus.REVIEW: N_("İnceleme gerekli"),
    TrainingItemStatus.DISMISSED: N_("Yoksayıldı"),
}
# Çalıştırmanın sonuç sayaçlarında durumun adı (varsayılan: durum etiketinin küçük harfi); 11.9.6
# yoksayılanları "yoksayılan" diye sayar.
COUNT_LABELS: dict[str, str] = {TrainingItemStatus.DISMISSED: N_("yoksayılan")}
SHOW_DISMISSED = "dismissed"
METHOD_LABELS: dict[str, str] = {
    TrainingMethod.MECHANICAL: N_("Mekanik"),
    TrainingMethod.AI: N_("Yapay zekâ"),
    TrainingMethod.MANUAL: N_("İK (elle)"),
    ExampleMethod.LEGACY: N_("Eğitimden önce"),
}
LABEL_TEXTS: dict[str, str] = {
    ExampleLabel.AI_DECISION: N_("AI kararı"),
    ExampleLabel.VERIFIED: N_("Doğrulandı"),
}
RUN_KIND_LABELS: dict[str, str] = {
    TrainingRunKind.UPLOAD: N_("Yükleme"),
    TrainingRunKind.MAP: N_("Harita"),
}
RUN_STATUS_LABELS: dict[str, str] = {
    TrainingRunStatus.RUNNING: N_("Sürüyor"),
    TrainingRunStatus.DONE: N_("Bitti"),
}

# Süzgeç anahtarı → etiket (sıra ekrandaki sıradır; boş anahtar "Tümü").
ITEM_FILTERS: tuple[tuple[str, str], ...] = (
    ("", N_("Tümü")),
    ("ai", N_("AI kararı")),
    ("unplaced", N_("Yerleştirilemedi")),
    ("conflict", N_("Çelişki")),
    ("review", N_("İnceleme gerekli")),
    ("mechanical", N_("Mekanik")),
    ("failed", N_("Hatalı")),
)
FILTER_KEYS = frozenset(key for key, _ in ITEM_FILTERS)

# Bilinen belgeler görünümünün süzgeci.
KNOWN_FILTERS: tuple[tuple[str, str], ...] = (
    ("", N_("Tümü")),
    ("examples", N_("Örneği olanlar")),
    ("ai", N_("AI kararı olanlar")),
)
KNOWN_FILTER_KEYS = frozenset(key for key, _ in KNOWN_FILTERS)

NOTICES: dict[str, str] = {
    "uploaded": N_(
        "Yükleme alındı ve mekanik tanıma bitti. Mekanik tanınmayan dosyaları işçi yapay zekâyla "
        "inceler; sonuçlar bu tabloda güncellenir."
    ),
    "placed": N_("Öğe seçilen türe yerleşti; örnek doğrulanmış olarak kaydedildi."),
    "skipped": N_("Öğe yerleşmedi: aynı içerik bu türde zaten örnek."),
    "conflict": N_("Öğe yerleşmedi: aynı içerik başka bir türde örnek. Notu inceleyin."),
    "verified": N_('Seçilen "AI kararı" örnekleri doğrulandı; elle kontrol ikonu kalktı.'),
    "verify_none": N_('Doğrulanacak "AI kararı" örneği seçilmedi; hiçbir şey değişmedi.'),
    "moved": N_("Örnek bu türe taşındı ve doğrulanmış olarak kaydedildi."),
    "removed": N_("Örnek örneklerden çıkarıldı: dosya silinmedi, eğitim arşivine taşındı."),
    "map_started": N_(
        "Toplu tarama başladı. İşçi haritadaki dosyaları birer birer tarar; ilerleme bu tabloda "
        "güncellenir."
    ),
    "dismissed": N_(
        "Öğe yoksayıldı: listeden kalktı, dosyası yerinde duruyor. Yoksayılanlar görünümünden geri "
        "alabilirsiniz."
    ),
    "restored": N_('Öğenin yoksayılması geri alındı; öğe "Yerleştirilemedi" listesinde bekliyor.'),
    "run_archived": N_(
        "Çalıştırma arşivlendi: listeden ve sayaçlardan kalktı; öğeleri ve örnekleri değişmedi."
    ),
    "run_restored": N_("Çalıştırma arşivden geri alındı."),
}

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")


def get_training_provider_problem(settings: AppSettings) -> str | None:
    """Yapay zekâ sağlayıcısı kurulamıyorsa nedeni (sekmede bilgi notu); kurulabiliyorsa `None`.
    Sekme sağlayıcıyı çağırmaz; inceleme işçinindir."""
    try:
        create_provider(settings)
    except ProviderConfigError as exc:
        return str(exc)
    return None


ProviderProblem = Annotated[str | None, Depends(get_training_provider_problem)]


@dataclass(frozen=True, slots=True)
class TypeRef:
    """Ekranda bir tür: slug, bilinen türse adı ve ayrıntı bağlantısı."""

    slug: str
    name: str | None
    url: str | None


@dataclass(frozen=True, slots=True)
class RunRow:
    id: int
    kind: str
    created_at: str
    created_by: str
    status: str
    status_label: str
    counts: str
    url: str
    selected: bool
    map_name: str | None = None
    total: int = 0
    processed: int = 0  # kararı sistemde beklemeyen (`queued`, `ai_pending` dışı) öğe
    archived: bool = False

    @property
    def running(self) -> bool:
        return self.status == TrainingRunStatus.RUNNING


@dataclass(frozen=True, slots=True)
class ItemRow:
    id: int
    run_id: int
    name: str
    hint: TypeRef | None
    result: TypeRef | None
    method: str | None
    status: str
    status_label: str
    note: str | None
    label: str | None
    label_text: str | None
    manual_check: bool
    placeable: bool
    example_id: int | None = None
    removed: bool = False
    dismissable: bool = False
    dismissed: bool = False


@dataclass(frozen=True, slots=True)
class ResultsView:
    runs: list[RunRow]
    items: list[ItemRow]
    total: int
    run_id: int | None
    filter: str
    filters: list[tuple[str, str, str, bool]]  # (anahtar, etiket, url, seçili)
    poll: bool
    poll_url: str
    pending: int
    all_runs_url: str
    current_url: str = TRAINING_PATH
    verifiable: int = 0
    show: str = ""
    archived: bool = False
    dismissed: int = 0  # kapsamdaki yoksayılan öğe (görünüm bağlantısının sayısı)
    dismissed_url: str = TRAINING_PATH
    archive_toggle_url: str = TRAINING_PATH


@dataclass(frozen=True, slots=True)
class KnownRow:
    slug: str
    name: str
    source: str
    in_catalog: bool
    country: str | None
    examples: int
    ai_decision: int
    verified: int
    url: str


@dataclass(frozen=True, slots=True)
class ExampleRow:
    name: str
    size_label: str
    url: str
    is_image: bool
    method: str | None
    label: str | None
    label_text: str | None
    manual_check: bool
    note: str | None
    created_at: str | None
    record_id: int | None = None


# --- yardımcılar ------------------------------------------------------------------------------


def _format_ts(moment: datetime) -> str:
    return f"{moment:%Y-%m-%d %H:%M} UTC"


def _size_label(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _known_url(slug: str) -> str:
    return f"{KNOWN_PATH}/{quote(slug)}"


def _type_ref(known: KnownTypes, slug: str | None) -> TypeRef | None:
    if not slug:
        return None
    found = known.get(slug)
    if found is None:
        return TypeRef(slug, None, None)
    return TypeRef(slug, found.name, _known_url(slug))


def _results_url(
    path: str,
    run_id: int | None,
    item_filter: str,
    *,
    show: str = "",
    archived: bool = False,
) -> str:
    pairs = (("run", run_id), ("filter", item_filter), ("show", show), ("archived", int(archived)))
    query = {key: value for key, value in pairs if value}
    return f"{path}?{urlencode(query)}" if query else path


def _counts_text(counts: dict[str, int]) -> str:
    """Çalıştırmanın sonuç sayaçları isteğin dilinde (durum adı küçük harfle)."""
    parts = [
        f"{counts[status]} {gettext(COUNT_LABELS.get(status, STATUS_LABELS[status])).lower()}"
        for status in TrainingItemStatus
        if counts.get(status)
    ]
    return " · ".join(parts) or "—"


def _filtered(statement: Select[tuple[TrainingItem]], item_filter: str) -> Select:
    if item_filter == "ai":
        ai_items = select(ExampleFileRecord.training_item_id).where(
            ExampleFileRecord.label == ExampleLabel.AI_DECISION.value,
            ExampleFileRecord.training_item_id.is_not(None),
            ExampleFileRecord.removed_at.is_(None),
        )
        return statement.where(TrainingItem.id.in_(ai_items))
    if item_filter == "mechanical":
        return statement.where(TrainingItem.method == TrainingMethod.MECHANICAL.value)
    if item_filter in ("unplaced", "conflict", "review", "failed"):
        return statement.where(TrainingItem.status == item_filter)
    return statement


def _examples_of(session: Session, item_ids: Iterable[int]) -> dict[int, ExampleFileRecord]:
    """Öğenin yerleştirdiği örneğin kaydı (öğe yerleşmediyse kayıt yoktur); örneklerden çıkarılmış
    kayıt da döner — satır "Örneklerden çıkarıldı" gösterir."""
    ids = list(item_ids)
    if not ids:
        return {}
    records = session.scalars(
        select(ExampleFileRecord).where(ExampleFileRecord.training_item_id.in_(ids))
    )
    return {record.training_item_id: record for record in records if record.training_item_id}


def _item_row(item: TrainingItem, known: KnownTypes, example: ExampleFileRecord | None) -> ItemRow:
    removed = example is not None and example.removed_at is not None
    label = example.label if example is not None and not removed else None
    return ItemRow(
        id=item.id,
        run_id=item.run_id,
        name=item.original_name,
        hint=_type_ref(known, item.hint_slug),
        result=_type_ref(known, item.result_slug),
        method=METHOD_LABELS.get(item.method) if item.method else None,
        status=item.status,
        status_label=STATUS_LABELS.get(item.status, item.status),
        note=item.note,
        label=label,
        label_text=REMOVED_LABEL_TEXT if removed else LABEL_TEXTS.get(label) if label else None,
        manual_check=label == ExampleLabel.AI_DECISION,
        placeable=item.status in MANUALLY_PLACEABLE,
        example_id=example.id if example is not None else None,
        removed=removed,
        dismissable=item.status in DISMISSABLE_STATUSES,
        dismissed=item.status == TrainingItemStatus.DISMISSED,
    )


def _run_row(
    run: TrainingRun, *, run_id: int | None, item_filter: str, archived: bool = False
) -> RunRow:
    counts = run.counts_json or {}
    total = sum(counts.values())
    pending = sum(counts.get(status.value, 0) for status in PENDING_STATUSES)
    return RunRow(
        id=run.id,
        kind=RUN_KIND_LABELS.get(run.kind, run.kind),
        created_at=_format_ts(run.created_at),
        created_by=run.created_by,
        status=run.status,
        status_label=RUN_STATUS_LABELS.get(run.status, run.status),
        counts=_counts_text(counts),
        url=_results_url(TRAINING_PATH, run.id, item_filter, archived=archived),
        selected=run.id == run_id,
        map_name=run.map_name,
        total=total,
        processed=total - pending,
        archived=run.archived_at is not None,
    )


def _count(session: Session, statement: Select) -> int:
    return session.scalar(select(func.count()).select_from(statement.subquery())) or 0


def build_results_view(
    session: Session,
    known: KnownTypes,
    *,
    run_id: int | None,
    item_filter: str,
    show: str = "",
    archived: bool = False,
) -> ResultsView:
    """Son çalıştırmalar ve (seçili çalıştırmanın ya da hepsinin) öğeleri, en yeni üstte.

    11.9.6: çalıştırma listesi ve — çalıştırma seçili değilse — öğe kapsamı arşivli çalıştırmaları
    dışlar (`archived` yalnız arşivlileri gösterir); seçili çalıştırma arşivli de olsa öğelerini
    gösterir. Yoksayılan öğe varsayılan olarak gösterilmez, `show="dismissed"` yalnız onları
    gösterir (süzgeç o görünümde uygulanmaz). Üst sayaçlar (dosya, bekleyen) aynı kapsamdan
    sayılır."""
    in_archive = TrainingRun.archived_at.is_not(None)
    run_scope = select(TrainingRun).where(in_archive if archived else ~in_archive)
    runs = session.scalars(run_scope.order_by(TrainingRun.id.desc()).limit(RUN_LIMIT))
    run_rows = [
        _run_row(run, run_id=run_id, item_filter=item_filter, archived=archived) for run in runs
    ]

    scope = select(TrainingItem)
    if run_id is not None:
        scope = scope.where(TrainingItem.run_id == run_id)
    else:
        scope = scope.where(TrainingItem.run_id.in_(run_scope.with_only_columns(TrainingRun.id)))
    is_dismissed = TrainingItem.status == TrainingItemStatus.DISMISSED.value
    showing_dismissed = show == SHOW_DISMISSED
    show = SHOW_DISMISSED if showing_dismissed else ""
    if showing_dismissed:
        item_filter = ""
        filtered = scope.where(is_dismissed)
    else:
        filtered = _filtered(scope.where(~is_dismissed), item_filter)
    total = _count(session, filtered)
    items = list(session.scalars(filtered.order_by(TrainingItem.id.desc()).limit(ITEM_LIMIT)))
    examples = _examples_of(session, (item.id for item in items))
    pending = _count(
        session, scope.where(TrainingItem.status.in_([s.value for s in PENDING_STATUSES]))
    )
    dismissed = total if showing_dismissed else _count(session, scope.where(is_dismissed))

    rows = [_item_row(item, known, examples.get(item.id)) for item in items]

    def url(path: str, run: int | None, key: str, view: str = show) -> str:
        return _results_url(path, run, key, show=view, archived=archived)

    return ResultsView(
        runs=run_rows,
        items=rows,
        total=total,
        run_id=run_id,
        filter=item_filter,
        filters=[
            (key, label, url(TRAINING_PATH, run_id, key, ""), key == item_filter and not show)
            for key, label in ITEM_FILTERS
        ],
        poll=pending > 0,
        poll_url=url(ITEMS_PATH, run_id, item_filter),
        pending=pending,
        all_runs_url=url(TRAINING_PATH, None, item_filter),
        current_url=url(TRAINING_PATH, run_id, item_filter),
        verifiable=sum(1 for row in rows if row.manual_check),
        show=show,
        archived=archived,
        dismissed=dismissed,
        dismissed_url=url(TRAINING_PATH, run_id, "", SHOW_DISMISSED),
        archive_toggle_url=_results_url(TRAINING_PATH, None, "", archived=not archived),
    )


def _training_page(
    request: Request,
    user: PanelUser,
    session: Session,
    *,
    run_id: int | None,
    item_filter: str,
    provider_problem: str | None,
    status_code: int = 200,
    errors: list[str] | None = None,
    notice: str | None = None,
    hint_slug: str | None = None,
    show: str = "",
    archived: bool = False,
) -> HTMLResponse:
    known = load_known_types(session)
    results = build_results_view(
        session, known, run_id=run_id, item_filter=item_filter, show=show, archived=archived
    )
    # SQLite'ta okuma da yazma kilidini tutar (`app.db.session`): çizmeden önce bırakılır.
    session.rollback()
    entry = MENU_BY_KEY["training"]
    return render_page(
        request,
        "training.html",
        user=user,
        active=entry.key,
        status_code=status_code,
        entry=entry,
        tab="upload",
        known_types=list(known),
        results=results,
        provider_problem=provider_problem,
        errors=errors or [],
        notice=NOTICES.get(notice or ""),
        hint_slug=hint_slug,
        manual_check_text=MANUAL_CHECK_TEXT,
    )


def _run_param(run: str | None) -> int | None:
    if run is None or not run.strip():
        return None
    try:
        value = int(run)
    except ValueError:
        return None
    return value if value > 0 else None


def _filter_param(value: str | None) -> str:
    return value if value in FILTER_KEYS else ""


def _show_param(value: str | None) -> str:
    return SHOW_DISMISSED if value == SHOW_DISMISSED else ""


def _archived_param(value: str | None) -> bool:
    return value == "1"


# --- yükleme ve sonuçlar ----------------------------------------------------------------------


@router.get(TRAINING_PATH, response_class=HTMLResponse)
def training_page(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    provider_problem: ProviderProblem,
    run: str | None = None,
    filter: str | None = None,
    notice: str | None = None,
    show: str | None = None,
    archived: str | None = None,
) -> HTMLResponse:
    return _training_page(
        request,
        user,
        session,
        run_id=_run_param(run),
        item_filter=_filter_param(filter),
        provider_problem=provider_problem,
        notice=notice,
        show=_show_param(show),
        archived=_archived_param(archived),
    )


@router.get(ITEMS_PATH, response_class=HTMLResponse)
def training_items(
    request: Request,
    session: DbSession,
    run: str | None = None,
    filter: str | None = None,
    show: str | None = None,
    archived: str | None = None,
) -> HTMLResponse:
    """Sonuç bölümü (HTMX yoklamasının hedefi): kararı sistemde bekleyen öğe varken yenilenir.
    Yoksayılan öğe varsayılan olarak gösterilmez (`?show=dismissed` yalnız onları gösterir), arşivli
    çalıştırmalar `?archived=1` ile görünür (11.9.6)."""
    known = load_known_types(session)
    results = build_results_view(
        session,
        known,
        run_id=_run_param(run),
        item_filter=_filter_param(filter),
        show=_show_param(show),
        archived=_archived_param(archived),
    )
    session.rollback()
    return render_page(
        request,
        "training_results.html",
        user=None,
        results=results,
        manual_check_text=MANUAL_CHECK_TEXT,
    )


@router.post(TRAINING_PATH, response_class=HTMLResponse)
async def submit_training(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    settings: AppSettings,
    provider_problem: ProviderProblem,
) -> Response:
    """11.9.1 — eğitim yüklemesi: bir `training_runs` satırı (`upload`) ve dosya başına bir öğe.
    Mekanik tanıma burada biter; yapay zekâ adımı işçiye kalır. Ad ya da beklenen tür geçersizse
    hiçbir şey yazılmaz (400)."""
    limit = settings.max_upload_file_size_bytes
    # Form elle okunur: tarayıcı dosya seçilmemişken adı boş tek bir parça gönderir (bkz.
    # `submit_upload`). Her dosya sınırın bir baytı ötesine kadar okunur: devasa dosya belleğe
    # tümüyle alınmaz, sınır aşımı `check_example`'da yine yakalanır.
    async with request.form() as form:
        chosen = [
            (file.filename, await file.read(limit + 1))
            for file in form.getlist("files")
            if isinstance(file, StarletteUploadFile) and file.filename
        ]
        submitted_hint = form.get("hint_slug")
    hint_slug = (submitted_hint.strip() or None) if isinstance(submitted_hint, str) else None

    errors: list[str] = []
    if not chosen:
        errors.append(NO_FILE_MESSAGE)
    for name, _content in chosen:
        try:
            _validated_name(name)
        except HTTPException as exc:
            errors.append(exc.detail)
    known = load_known_types(session)
    if hint_slug is not None and hint_slug not in known:
        errors.append(UNKNOWN_HINT_MESSAGE)
        hint_slug = None
    if errors:
        session.rollback()
        return _training_page(
            request,
            user,
            session,
            run_id=None,
            item_filter="",
            provider_problem=provider_problem,
            status_code=status.HTTP_400_BAD_REQUEST,
            errors=errors,
            hint_slug=hint_slug,
        )

    inventory = load_example_inventory(layout)
    run = create_run(session, kind=TrainingRunKind.UPLOAD, created_by=user.username)
    for name, content in chosen:
        stage_and_recognize(
            session,
            layout,
            known,
            run,
            name,
            content,
            max_bytes=limit,
            inventory=inventory,
            hint_slug=hint_slug,
        )
    session.commit()
    return RedirectResponse(
        f"{TRAINING_PATH}?{urlencode({'run': run.id, 'notice': 'uploaded'})}",
        status.HTTP_303_SEE_OTHER,
    )


@router.post(f"{ITEMS_PATH}/{{item_id}}/place", response_class=HTMLResponse)
def place_item(
    item_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    provider_problem: ProviderProblem,
    slug: Annotated[str, Form()] = "",
) -> Response:
    """11.9.1 "Türe yerleştir" — `unplaced`, `conflict` ya da (harita, 11.9.5) `review` öğe İK'nın
    seçtiği bilinen türe yerleşir: `method=manual`, etiket `verified`, olay kullanıcı adıyla.
    Yerleştirme yalnız kopyalar ve kaydeder (K11); yerindeki harita öğesi aynı türe seçilirse
    kopyasız kaydolur."""
    item = session.get(TrainingItem, item_id)
    if item is None:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, ITEM_NOT_FOUND)
    run_id = item.run_id

    def refused(status_code: int, message: str) -> HTMLResponse:
        session.rollback()
        return _training_page(
            request,
            user,
            session,
            run_id=run_id,
            item_filter="",
            provider_problem=provider_problem,
            status_code=status_code,
            errors=[message],
        )

    if item.status not in MANUALLY_PLACEABLE:
        return refused(status.HTTP_409_CONFLICT, NOT_MANUALLY_PLACEABLE)
    known = load_known_types(session)
    chosen = slug.strip()
    if chosen not in known:
        return refused(status.HTTP_422_UNPROCESSABLE_CONTENT, UNKNOWN_TYPE_MESSAGE)
    note = f"Elle yerleştirildi → `{chosen}`"
    if item.note:
        note = f"{note}; önceki not: {item.note}"
    # Haritanın yerindeki öğesinin eğitim kopyası yoktur: dosya türün örnek klasöründen gelir.
    source = item_source_path(layout, item)
    if source is None:
        return refused(status.HTTP_409_CONFLICT, FILE_MISSING)
    try:
        placement = place_example(
            session,
            layout,
            known,
            item,
            chosen,
            method=TrainingMethod.MANUAL,
            note=note,
            actor=user.username,
            source=source,
        )
    except (ItemNotPlaceableError, ContentMismatchError, OSError):
        return refused(status.HTTP_409_CONFLICT, FILE_MISSING)
    session.commit()
    query = urlencode({"run": run_id, "notice": placement.status.value})
    return RedirectResponse(f"{TRAINING_PATH}?{query}#item-{item_id}", status.HTTP_303_SEE_OTHER)


# --- temizlik: öğeyi yoksay, çalıştırmayı arşivle (11.9.6) --------------------------------------


def _cleanup_refused(
    request: Request,
    user: PanelUser,
    session: Session,
    provider_problem: str | None,
    *,
    status_code: int,
    message: str,
    run_id: int | None = None,
    show: str = "",
    archived: bool = False,
) -> HTMLResponse:
    """Temizlik reddi → sekme hata kutusuyla; hiçbir şey yazılmadı."""
    session.rollback()
    return _training_page(
        request,
        user,
        session,
        run_id=run_id,
        item_filter="",
        provider_problem=provider_problem,
        status_code=status_code,
        errors=[message],
        show=show,
        archived=archived,
    )


def _item_or_404(session: Session, item_id: int) -> TrainingItem:
    item = session.get(TrainingItem, item_id)
    if item is None:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, ITEM_NOT_FOUND)
    return item


@router.post(f"{ITEMS_PATH}/{{item_id}}/dismiss", response_class=HTMLResponse)
def dismiss_training_item(
    item_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    provider_problem: ProviderProblem,
    note: Annotated[str, Form()] = "",
    next: Annotated[str | None, Form()] = None,
) -> Response:
    """11.9.6 "Yoksay" — `unplaced`, `conflict` ya da `review` öğe tek adımda `dismissed` olur
    (§D61-b); not (isteğe bağlı, en çok 200) öğenin notuna eklenir, `TRAINING_ITEM_DISMISSED`
    kullanıcı adıyla. Dosya yerinde kalır. Başka durumdaki öğe 409, uzun not 422."""
    item = _item_or_404(session, item_id)
    try:
        dismiss_item(session, item, actor=user.username, note=note)
    except (CleanupError, CleanupNoteError) as exc:
        code = (
            status.HTTP_422_UNPROCESSABLE_CONTENT
            if isinstance(exc, CleanupNoteError)
            else status.HTTP_409_CONFLICT
        )
        return _cleanup_refused(
            request, user, session, provider_problem, status_code=code, message=_reason(exc)
        )
    session.commit()
    return RedirectResponse(_with_notice(_safe_next(next), "dismissed"), status.HTTP_303_SEE_OTHER)


@router.post(f"{ITEMS_PATH}/{{item_id}}/restore", response_class=HTMLResponse)
def restore_training_item(
    item_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    provider_problem: ProviderProblem,
    next: Annotated[str | None, Form()] = None,
) -> Response:
    """11.9.6 — yoksaymayı geri alır: `dismissed` öğe `unplaced` olur ("Türe yerleştir"i yeniden
    bekler), `TRAINING_ITEM_RESTORED` kullanıcı adıyla. Yoksayılmamış öğe 409."""
    item = _item_or_404(session, item_id)
    try:
        restore_item(session, item, actor=user.username)
    except CleanupError as exc:
        return _cleanup_refused(
            request,
            user,
            session,
            provider_problem,
            status_code=status.HTTP_409_CONFLICT,
            message=_reason(exc),
            show=SHOW_DISMISSED,
        )
    session.commit()
    return RedirectResponse(_with_notice(_safe_next(next), "restored"), status.HTTP_303_SEE_OTHER)


def _run_action(
    run_id: int,
    request: Request,
    user: PanelUser,
    session: Session,
    provider_problem: str | None,
    *,
    archive: bool,
) -> Response:
    run = session.get(TrainingRun, run_id)
    if run is None:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, RUN_NOT_FOUND)
    try:
        if archive:
            archive_run(session, run, actor=user.username)
        else:
            restore_run(session, run, actor=user.username)
    except CleanupError as exc:
        return _cleanup_refused(
            request,
            user,
            session,
            provider_problem,
            status_code=status.HTTP_409_CONFLICT,
            message=_reason(exc),
            archived=not archive,
        )
    session.commit()
    # Arşivlenen çalıştırma varsayılan listeden kalkar: dönüş arşivsiz liste; geri alınan
    # çalıştırma yeniden listededir.
    notice = "run_archived" if archive else "run_restored"
    return RedirectResponse(f"{TRAINING_PATH}?notice={notice}", status.HTTP_303_SEE_OTHER)


@router.post(f"{RUNS_PATH}/{{run_id}}/archive", response_class=HTMLResponse)
def archive_training_run(
    run_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    provider_problem: ProviderProblem,
) -> Response:
    """11.9.6 — çalıştırmayı tek adımda arşivler (`archived_at`): listeden ve üst sayaçlardan
    kalkar, öğeleri ve örnekleri değişmez; `TRAINING_RUN_ARCHIVED` kullanıcı adıyla. Zaten arşivli
    çalıştırma 409."""
    return _run_action(run_id, request, user, session, provider_problem, archive=True)


@router.post(f"{RUNS_PATH}/{{run_id}}/restore", response_class=HTMLResponse)
def restore_training_run(
    run_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    provider_problem: ProviderProblem,
) -> Response:
    """11.9.6 — arşivli çalıştırmayı tek adımda geri alır; `TRAINING_RUN_ARCHIVED`
    (`restored: true`). Arşivde olmayan çalıştırma 409."""
    return _run_action(run_id, request, user, session, provider_problem, archive=False)


# --- bilinen belgeler -------------------------------------------------------------------------


def _label_counts(session: Session) -> dict[tuple[str, str], int]:
    rows = session.execute(
        select(ExampleFileRecord.type_slug, ExampleFileRecord.label, func.count())
        .where(ExampleFileRecord.label.is_not(None), ExampleFileRecord.removed_at.is_(None))
        .group_by(ExampleFileRecord.type_slug, ExampleFileRecord.label)
    ).tuples()
    return {(slug, label): count for slug, label, count in rows if label is not None}


def _source_text(known: KnownType) -> str:
    return N_("Katalog") if known.in_catalog else N_("Önerilen")


def _reason(exc: BaseException) -> str:
    """Çekirdeğin hata metni: ilk argüman (`Translatable` ise gösterimde çevrilir), yoksa metni."""
    return exc.args[0] if exc.args and isinstance(exc.args[0], str) else str(exc)


@router.get(KNOWN_PATH, response_class=HTMLResponse)
def known_documents(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    show: str | None = None,
) -> HTMLResponse:
    """Bilinen belgeler: katalog + hazır önerilen türler, örnek sayısı ve etiketli örnek sayısı."""
    known = load_known_types(session)
    counts = _label_counts(session)
    session.rollback()
    selected = show if show in KNOWN_FILTER_KEYS else ""
    rows = []
    for known_type in known:
        row = KnownRow(
            slug=known_type.slug,
            name=known_type.name,
            source=_source_text(known_type),
            in_catalog=known_type.in_catalog,
            country=known_type.country_iso3 or known_type.country_iso2,
            examples=len(list_examples(layout, known_type.slug)),
            ai_decision=counts.get((known_type.slug, ExampleLabel.AI_DECISION.value), 0),
            verified=counts.get((known_type.slug, ExampleLabel.VERIFIED.value), 0),
            url=_known_url(known_type.slug),
        )
        if (selected == "examples" and not row.examples) or (
            selected == "ai" and not row.ai_decision
        ):
            continue
        rows.append(row)
    entry = MENU_BY_KEY["training"]
    return render_page(
        request,
        "training_known.html",
        user=user,
        active=entry.key,
        entry=entry,
        tab="known",
        rows=rows,
        total=len(known),
        catalog_count=sum(1 for known_type in known if known_type.in_catalog),
        filters=[
            (key, label, f"{KNOWN_PATH}?show={key}" if key else KNOWN_PATH, key == selected)
            for key, label in KNOWN_FILTERS
        ],
        manual_check_text=MANUAL_CHECK_TEXT,
    )


def _known_type(session: Session, slug: str) -> KnownType:
    """Bilinen tür; değilse 404. Okuma SQLite'ta yazma kilidini tutar: işlem hemen bırakılır."""
    try:
        found = load_known_types(session).get(slug)
    finally:
        session.rollback()
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND)
    return found


@router.get(f"{KNOWN_PATH}/{{slug}}", response_class=HTMLResponse)
def known_document(
    slug: str,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    notice: str | None = None,
) -> HTMLResponse:
    """Bilinen türün örnekleri: dosya, kaydı (yöntem, etiket, not) ve görüntüsü; "AI kararı"
    etiketli örnekte elle kontrol ikonu ve etiket kararı (doğrula, başka türe taşı, örneklerden
    çıkar; 11.9.4)."""
    known = load_known_types(session)
    known_type = known.get(slug)
    if known_type is None:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND)
    records = {
        record.name: record
        for record in session.scalars(
            select(ExampleFileRecord).where(
                ExampleFileRecord.type_slug == slug, ExampleFileRecord.removed_at.is_(None)
            )
        )
    }
    session.rollback()
    examples = []
    for example in list_examples(layout, slug):
        record = records.get(example.name)
        label = record.label if record is not None else None
        examples.append(
            ExampleRow(
                name=example.name,
                size_label=_size_label(example.size),
                url=f"{_known_url(slug)}/examples/{quote(example.name)}",
                is_image=example.name.casefold().endswith(_IMAGE_SUFFIXES),
                method=METHOD_LABELS.get(record.method) if record is not None else None,
                label=label,
                label_text=LABEL_TEXTS.get(label) if label else None,
                manual_check=label == ExampleLabel.AI_DECISION,
                note=record.note if record is not None else None,
                created_at=_format_ts(record.created_at) if record is not None else None,
                record_id=record.id if record is not None else None,
            )
        )
    entry = MENU_BY_KEY["training"]
    return render_page(
        request,
        "training_type.html",
        user=user,
        active=entry.key,
        entry=entry,
        tab="known",
        known_type=known_type,
        known_types=list(known),
        source=_source_text(known_type),
        examples=examples,
        ai_decision=sum(1 for example in examples if example.manual_check),
        manual_check_text=MANUAL_CHECK_TEXT,
        notice=NOTICES.get(notice or ""),
        type_url=_known_url(slug),
    )


@router.get(f"{KNOWN_PATH}/{{slug}}/examples/{{name}}")
def known_example_file(slug: str, name: str, session: DbSession, layout: Layout) -> FileResponse:
    """Bilinen türün (katalog dışı da olabilir) örnek dosyası, yüklendiği baytlar. Tür bilinen
    türlerden değilse ya da ad türün örnek listesinde yoksa 404; yol istekteki addan kurulmaz."""
    _known_type(session, slug)
    path = example_path(layout, slug, name)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, EXAMPLE_NOT_FOUND)
    return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})


# --- etiket kararı (11.9.4) -------------------------------------------------------------------


def _safe_next(value: str | None) -> str:
    """Kararın dönüş adresi: yalnız eğitim sekmesinin kendi yolları (açık yönlendirme olmasın)."""
    if value and value.startswith(TRAINING_PATH) and "\\" not in value and "//" not in value:
        return value
    return TRAINING_PATH


def _with_notice(url: str, notice: str) -> str:
    parts = urlsplit(url)
    query = [(key, item) for key, item in parse_qsl(parts.query) if key != "notice"]
    fragment = f"#{parts.fragment}" if parts.fragment else ""
    return f"{parts.path}?{urlencode([*query, ('notice', notice)])}{fragment}"


@router.post(f"{EXAMPLES_PATH}/verify")
def verify_selected(
    user: CurrentUser,
    session: DbSession,
    example_ids: Annotated[list[int] | None, Form()] = None,
    next: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """11.9.4 "Doğrula" — seçilen (tek ya da çok) "AI kararı" örneklerinin etiketi `verified` olur;
    her biri için `TRAINING_LABEL_VERIFIED` kullanıcı adıyla yazılır. Tek adımdır (dosya işlemi
    değil, §D58 c). "AI kararı" olmayan seçim değişmeden kalır."""
    ids = sorted(set(example_ids or ()))
    records = (
        list(session.scalars(select(ExampleFileRecord).where(ExampleFileRecord.id.in_(ids))))
        if ids
        else []
    )
    verified = verify_examples(session, records, actor=user.username)
    if verified:
        session.commit()
    else:
        session.rollback()
    notice = "verified" if verified else "verify_none"
    return RedirectResponse(_with_notice(_safe_next(next), notice), status.HTTP_303_SEE_OTHER)


def _type_name(known: KnownTypes, slug: str) -> str:
    found = known.get(slug)
    return found.name if found is not None else slug


def _fill(text: str, **values: str) -> str:
    """Onay metninin yer tutucularını doldurur; doldurulmayan yer tutucu `ValueError`dır."""
    placeholders = {
        FILE_PLACEHOLDER: values.get("file"),
        OLD_TYPE_PLACEHOLDER: values.get("old_type"),
        NEW_TYPE_PLACEHOLDER: values.get("new_type"),
        TYPE_PLACEHOLDER: values.get("type"),
        MAP_PLACEHOLDER: values.get("map"),
        FILES_PLACEHOLDER: values.get("files"),
        AI_FILES_PLACEHOLDER: values.get("ai_files"),
    }
    for placeholder, value in placeholders.items():
        if placeholder in text:
            if value is None:
                raise ValueError(f"Onay metninin {placeholder} yer tutucusu doldurulmadı")
            text = text.replace(placeholder, value)
    return text


def decision_subject(example: ExampleFileRecord, target_slug: str = "") -> str:
    """Etiket kararı belirtecinin hedefi: örnek kaydı + türü, adı ve (taşımada) hedef tür (10.8.1
    belirteci). Örnek bu arada taşındıysa, çıkarıldıysa ya da hedef değiştiyse belirteç geçmez."""
    state = "\n".join((example.type_slug, example.name, target_slug))
    return f"{example.id}:{hashlib.sha256(state.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class _Decision:
    """Karar adımının bağlamı: örnek, bilinen türler, hedef tür ve metinlerin değerleri."""

    example: ExampleFileRecord
    known: KnownTypes
    target: str
    values: dict[str, str]


def _decision(
    session: Session, layout: DataLayout, example_id: int, operation: Operation, slug: str
) -> _Decision:
    """Kararın ortak denetimi (her adımda yeniden): örnek (404), hedef tür (422) ve yapılabilirlik
    (`ExampleDecisionError`, 409). Hiçbir şey yazmaz."""
    example = session.get(ExampleFileRecord, example_id)
    if example is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, EXAMPLE_RECORD_NOT_FOUND)
    known = load_known_types(session)
    values = {"file": example.name, "type": _type_name(known, example.type_slug)}
    target = ""
    if operation is Operation.TRAINING_MOVE:
        target = slug.strip()
        check_move(session, layout, known, example, target)
        values |= {"old_type": values["type"], "new_type": _type_name(known, target)}
    else:
        check_remove(layout, example)
    return _Decision(example, known, target, values)


_DECISION_TEXTS: dict[Operation, tuple[str, str]] = {
    Operation.TRAINING_MOVE: (MOVE_FIRST_CONFIRMATION, MOVE_SECOND_CONFIRMATION),
    Operation.TRAINING_REMOVE: (REMOVE_FIRST_CONFIRMATION, REMOVE_SECOND_CONFIRMATION),
}
_DECISION_PATHS: dict[Operation, str] = {
    Operation.TRAINING_MOVE: "move",
    Operation.TRAINING_REMOVE: "remove",
}
_DECISION_ERRORS = (HTTPException, UnknownTypeError, ExampleDecisionError)


def _decision_page(
    request: Request,
    user: PanelUser,
    operation: Operation,
    example_id: int,
    status_code: int,
    *,
    decision: _Decision | None = None,
    back_slug: str | None = None,
    error: str | None = None,
    confirmation: str | None = None,
) -> HTMLResponse:
    """Karar adımının sayfası: birinci onay (belirteçsiz), ikinci onay (belirteçle) ya da ret."""
    first, second = _DECISION_TEXTS[operation]
    text = None
    if decision is not None:
        # İsteğin dilinde (§D92): yer tutucular (`<Dosya>`, `<Tür>`…) çeviride de aynıdır.
        text = _fill(gettext(second if confirmation else first), **decision.values)
        back_slug = decision.example.type_slug
    entry = MENU_BY_KEY["training"]
    return render_page(
        request,
        "training_decision.html",
        user=user,
        active=entry.key,
        status_code=status_code,
        entry=entry,
        operation=_DECISION_PATHS[operation],
        example_id=example_id,
        target=decision.target if decision is not None else "",
        confirm_text=text,
        confirmation=confirmation,
        error=error,
        back_url=_known_url(back_slug) if back_slug else KNOWN_PATH,
    )


def _refused_decision(
    request: Request,
    user: PanelUser,
    session: Session,
    operation: Operation,
    example_id: int,
    exc: Exception,
) -> HTMLResponse:
    """Karar adımının reddi → hata sayfası; hiçbir şey yazılmadı."""
    session.rollback()
    example = session.get(ExampleFileRecord, example_id)
    back_slug = example.type_slug if example is not None else None
    session.rollback()
    if isinstance(exc, HTTPException):
        code, message = exc.status_code, exc.detail
    elif isinstance(exc, UnknownTypeError):
        code, message = status.HTTP_422_UNPROCESSABLE_CONTENT, UNKNOWN_TYPE_MESSAGE
    elif isinstance(exc, ConfirmationRefusedError):
        code, message = status.HTTP_400_BAD_REQUEST, CONFIRMATION_REFUSED
    elif isinstance(exc, ExampleDecisionError):
        code, message = status.HTTP_409_CONFLICT, _reason(exc)
    else:  # dosya taşınamadı (`OSError`, `ContentMismatchError`)
        code, message = status.HTTP_409_CONFLICT, MOVE_FAILED
    return _decision_page(
        request, user, operation, example_id, code, back_slug=back_slug, error=message
    )


def _first_step(
    request: Request,
    user: PanelUser,
    session: Session,
    layout: DataLayout,
    operation: Operation,
    example_id: int,
    slug: str,
) -> HTMLResponse:
    try:
        decision = _decision(session, layout, example_id, operation, slug)
    except _DECISION_ERRORS as exc:
        return _refused_decision(request, user, session, operation, example_id, exc)
    response = _decision_page(
        request, user, operation, example_id, status.HTTP_200_OK, decision=decision
    )
    session.rollback()
    return response


def _prepare_step(
    request: Request,
    user: PanelUser,
    session: Session,
    layout: DataLayout,
    operation: Operation,
    example_id: int,
    slug: str,
) -> HTMLResponse:
    try:
        decision = _decision(session, layout, example_id, operation, slug)
        issued = issue_confirmation(
            session, request, user, operation, decision_subject(decision.example, decision.target)
        )
    except (*_DECISION_ERRORS, ConfirmationRefusedError) as exc:
        return _refused_decision(request, user, session, operation, example_id, exc)
    response = _decision_page(
        request,
        user,
        operation,
        example_id,
        status.HTTP_200_OK,
        decision=decision,
        confirmation=issued.token,
    )
    session.commit()
    return response


@router.post(f"{EXAMPLES_PATH}/{{example_id}}/move/confirm", response_class=HTMLResponse)
def move_first_confirmation(
    example_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    slug: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """11.9.4 "Başka türe taşı" — hedefi denetler ve §D58'in birinci onay metnini verir; hiçbir şey
    değişmez."""
    return _first_step(request, user, session, layout, Operation.TRAINING_MOVE, example_id, slug)


@router.post(f"{EXAMPLES_PATH}/{{example_id}}/move/prepare", response_class=HTMLResponse)
def prepare_move(
    example_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    slug: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """11.9.4 — birinci onaydan sonra ikinci onay metnini ve örneğe + hedefe bağlı tek kullanımlık
    belirteci verir (10.8.1)."""
    return _prepare_step(request, user, session, layout, Operation.TRAINING_MOVE, example_id, slug)


@router.post(f"{EXAMPLES_PATH}/{{example_id}}/move", response_class=HTMLResponse)
def move_selected(
    example_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    slug: Annotated[str, Form()] = "",
    confirmation: Annotated[str | None, Form()] = None,
) -> Response:
    """11.9.4 — ikinci onayın belirteciyle örneği başka türe taşır: dosya `examples/<eski>/`'den
    `examples/<yeni>/`'ye (ad doluysa `-2`), kayıt yeni türe, etiket `verified`. Belirteçsiz ya da
    geçersiz belirteçte hiçbir şey yapılmaz (400). Belirtecin tüketilmesi, `USER_CONFIRMED`,
    `TRAINING_EXAMPLE_MOVED` ve kayıt tek işlemdedir; dosya en son taşınır."""
    operation = Operation.TRAINING_MOVE
    try:
        decision = _decision(session, layout, example_id, operation, slug)
        example = decision.example
        confirm_operation(
            session,
            request,
            user,
            operation,
            decision_subject(example, decision.target),
            confirmation,
            event_target={
                "example_file_id": example.id,
                "from_slug": example.type_slug,
                "to_slug": decision.target,
            },
        )
        move_example(session, layout, decision.known, example, decision.target, actor=user.username)
    except (*_DECISION_ERRORS, ConfirmationRefusedError, ContentMismatchError, OSError) as exc:
        return _refused_decision(request, user, session, operation, example_id, exc)
    session.commit()
    return RedirectResponse(
        f"{_known_url(decision.target)}?notice=moved", status.HTTP_303_SEE_OTHER
    )


@router.post(f"{EXAMPLES_PATH}/{{example_id}}/remove/confirm", response_class=HTMLResponse)
def remove_first_confirmation(
    example_id: int, request: Request, user: CurrentUser, session: DbSession, layout: Layout
) -> HTMLResponse:
    """11.9.4 "Örneklerden çıkar" — §D58'in birinci onay metnini verir; hiçbir şey değişmez."""
    return _first_step(request, user, session, layout, Operation.TRAINING_REMOVE, example_id, "")


@router.post(f"{EXAMPLES_PATH}/{{example_id}}/remove/prepare", response_class=HTMLResponse)
def prepare_remove(
    example_id: int, request: Request, user: CurrentUser, session: DbSession, layout: Layout
) -> HTMLResponse:
    """11.9.4 — ikinci onay metnini ve örneğe bağlı tek kullanımlık belirteci verir (10.8.1)."""
    return _prepare_step(request, user, session, layout, Operation.TRAINING_REMOVE, example_id, "")


@router.post(f"{EXAMPLES_PATH}/{{example_id}}/remove", response_class=HTMLResponse)
def remove_selected(
    example_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    confirmation: Annotated[str | None, Form()] = None,
) -> Response:
    """11.9.4 — ikinci onayın belirteciyle örneği örneklerden çıkarır: dosya
    `_egitim/cikarilan/<slug>/`'a taşınır, **silinmez**; kayıt çıkarıldı olarak işaretlenir.
    Belirteçsiz ya da geçersiz belirteçte hiçbir şey yapılmaz (400)."""
    operation = Operation.TRAINING_REMOVE
    try:
        decision = _decision(session, layout, example_id, operation, "")
        example = decision.example
        slug = example.type_slug
        confirm_operation(
            session,
            request,
            user,
            operation,
            decision_subject(example),
            confirmation,
            event_target={"example_file_id": example.id, "type_slug": slug},
        )
        remove_example(session, layout, example, actor=user.username)
    except (*_DECISION_ERRORS, ConfirmationRefusedError, ContentMismatchError, OSError) as exc:
        return _refused_decision(request, user, session, operation, example_id, exc)
    session.commit()
    return RedirectResponse(f"{_known_url(slug)}?notice=removed", status.HTTP_303_SEE_OTHER)


# --- harita yükle ve toplu tarama (11.9.5) ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class MapScan:
    """Bir adımda okunan harita: adı, içeriği, çözümü ve önizlemesi."""

    name: str
    content: bytes
    plan: MapPlan
    preview: MapPreview

    @property
    def data(self) -> str:
        """Haritanın sonraki adıma sayfada taşınan biçimi (`pack_map`)."""
        return pack_map(self.content)


def pack_map(content: bytes) -> str:
    """Haritayı gizli form alanına koyar: zlib ile sıkıştırılmış, URL-güvenli base64. Sunucu
    haritayı adımlar arasında saklamaz (önizleme yazmaz)."""
    return base64.urlsafe_b64encode(zlib.compress(content, 9)).decode("ascii")


def unpack_map(value: str, *, max_bytes: int) -> bytes:
    """`pack_map`'in tersi; açılan içerik `max_bytes`'ı aşarsa (sıkıştırma bombası dahil) ya da
    veri bozuksa `MapError`."""
    try:
        packed = base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True)
        inflater = zlib.decompressobj()
        content = inflater.decompress(packed, max_bytes + 1)
    except (UnicodeEncodeError, binascii.Error, zlib.error, ValueError):
        raise MapError(MAP_DATA_INVALID) from None
    if len(content) > max_bytes or inflater.unconsumed_tail:
        raise MapError(map_too_large(max_bytes))
    if not inflater.eof or inflater.unused_data:
        raise MapError(MAP_DATA_INVALID)
    return content


def _map_name(filename: str) -> str:
    """Haritanın adı (yol parçası olmadan); `.csv` değilse `MapError`."""
    name = PurePosixPath(filename.replace("\\", "/")).name.strip()[:255]
    if not name.casefold().endswith(".csv") or name.casefold() == ".csv":
        raise MapError(MAP_NOT_CSV)
    return name


def _read_map(
    session: Session, layout: DataLayout, settings: Settings, name: str, content: bytes
) -> MapScan:
    """Haritayı okur, çözer ve önizler (yazmaz); okunamıyorsa `MapError`."""
    rows = parse_map(
        content,
        max_bytes=settings.training_map_max_bytes,
        max_rows=settings.training_map_max_rows,
    )
    known = load_known_types(session)
    plan = plan_map(
        rows,
        layout,
        known,
        collection_root=settings.training_collection_dir,
        max_files=settings.training_map_max_rows,
    )
    preview = preview_map(session, plan, known, inventory=load_example_inventory(layout))
    return MapScan(name, content, plan, preview)


def map_subject(scan: MapScan) -> str:
    """Toplu tarama belirtecinin hedefi (10.8.1): haritanın adı, içeriği, dosya sayısı ve yapay
    zekâya gönderilebilecek dosya sayısı. Harita ya da onay metnindeki sayılar değiştiyse belirteç
    geçmez."""
    digest = hashlib.sha256(
        f"{scan.name}\n{scan.preview.files}\n{scan.preview.ai_possible}\n".encode()
    )
    digest.update(scan.content)
    return f"map:{digest.hexdigest()}"


def _map_part_limit(settings: Settings) -> int:
    """Gizli alandaki haritanın en büyük boyutu: sıkıştırılamayan içerikte zlib'in küçük eki ve
    base64'ün 4/3'ü."""
    limit = settings.training_map_max_bytes
    return (limit + limit // 100 + 1024) * 4 // 3 + 4


async def _submitted_map(
    request: Request, session: Session, layout: DataLayout, settings: Settings
) -> tuple[MapScan, str | None]:
    """Onay adımlarının formundaki harita (gizli alan) ve belirteç; okunamıyorsa `MapError`."""
    async with request.form(max_part_size=_map_part_limit(settings)) as form:
        data, name, token = form.get("map_data"), form.get("map_name"), form.get("confirmation")
    if not isinstance(data, str) or not isinstance(name, str) or not data:
        raise MapError(MAP_DATA_INVALID)
    content = unpack_map(data, max_bytes=settings.training_map_max_bytes)
    scan = _read_map(session, layout, settings, _map_name(name), content)
    return scan, token if isinstance(token, str) and token else None


def _map_page(
    request: Request, user: PanelUser, scan: MapScan, *, provider_problem: str | None
) -> HTMLResponse:
    """Haritanın önizlemesi ve "Toplu taramayı başlat" düğmesi."""
    entry = MENU_BY_KEY["training"]
    preview = scan.preview
    return render_page(
        request,
        "training_map.html",
        user=user,
        active=entry.key,
        entry=entry,
        map_name=scan.name,
        map_data=scan.data,
        preview=preview,
        skipped=[(SKIP_LABELS[reason], count) for reason, count in preview.skipped],
        provider_problem=provider_problem,
    )


def _map_step_page(
    request: Request,
    user: PanelUser,
    status_code: int,
    *,
    scan: MapScan | None = None,
    confirmation: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    """Toplu taramanın onay adımı: birinci onay (belirteçsiz), ikinci onay (belirteçle) ya da
    ret."""
    text = None
    if scan is not None:
        values = {
            "map": scan.name,
            "files": str(scan.preview.files),
            "ai_files": str(scan.preview.ai_possible),
        }
        text = _fill(
            gettext(MAP_SECOND_CONFIRMATION if confirmation else MAP_FIRST_CONFIRMATION), **values
        )
    entry = MENU_BY_KEY["training"]
    return render_page(
        request,
        "training_map_step.html",
        user=user,
        active=entry.key,
        status_code=status_code,
        entry=entry,
        confirm_text=text,
        confirmation=confirmation,
        map_name=scan.name if scan is not None else "",
        map_data=scan.data if scan is not None else "",
        error=error,
    )


def _refused_map(
    request: Request, user: PanelUser, session: Session, exc: Exception
) -> HTMLResponse:
    """Onay adımının reddi → hata sayfası; hiçbir şey yazılmadı."""
    session.rollback()
    if isinstance(exc, ConfirmationRefusedError):
        code, message = status.HTTP_400_BAD_REQUEST, CONFIRMATION_REFUSED
    elif isinstance(exc, MapError):
        code, message = status.HTTP_400_BAD_REQUEST, _reason(exc)
    else:  # harita saklanamadı (`OSError`)
        code, message = status.HTTP_409_CONFLICT, MAP_SAVE_FAILED
    return _map_step_page(request, user, code, error=message)


@router.post(MAPS_PATH, response_class=HTMLResponse)
async def upload_map(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    settings: AppSettings,
    provider_problem: ProviderProblem,
) -> HTMLResponse:
    """11.9.5 "Harita yükle" — CSV haritasını okur ve önizlemesini gösterir; hiçbir şey yazmaz.
    Harita okunamıyorsa (biçim, boyut, satır sınırı) eğitim sayfası hatayla döner (400)."""
    limit = settings.training_map_max_bytes
    # Sınırın bir baytı ötesine kadar okunur: devasa harita belleğe tümüyle alınmaz.
    async with request.form() as form:
        upload = form.get("map")
        chosen = (
            (upload.filename, await upload.read(limit + 1))
            if isinstance(upload, StarletteUploadFile) and upload.filename
            else None
        )
    try:
        if chosen is None:
            raise MapError(NO_MAP_MESSAGE)
        filename, content = chosen
        scan = _read_map(session, layout, settings, _map_name(filename), content)
    except MapError as exc:
        session.rollback()
        return _training_page(
            request,
            user,
            session,
            run_id=None,
            item_filter="",
            provider_problem=provider_problem,
            status_code=status.HTTP_400_BAD_REQUEST,
            errors=[_reason(exc)],
        )
    session.rollback()
    return _map_page(request, user, scan, provider_problem=provider_problem)


@router.post(f"{MAPS_PATH}/confirm", response_class=HTMLResponse)
async def map_first_confirmation(
    request: Request, user: CurrentUser, session: DbSession, layout: Layout, settings: AppSettings
) -> HTMLResponse:
    """11.9.5 "Toplu taramayı başlat" — haritayı yeniden okur ve §D58'in birinci onay metnini verir;
    hiçbir şey değişmez."""
    try:
        scan, _token = await _submitted_map(request, session, layout, settings)
        if not scan.preview.files:
            raise MapError(MAP_EMPTY)
    except MapError as exc:
        return _refused_map(request, user, session, exc)
    session.rollback()
    return _map_step_page(request, user, status.HTTP_200_OK, scan=scan)


@router.post(f"{MAPS_PATH}/prepare", response_class=HTMLResponse)
async def prepare_map(
    request: Request, user: CurrentUser, session: DbSession, layout: Layout, settings: AppSettings
) -> HTMLResponse:
    """11.9.5 — birinci onaydan sonra ikinci onay metnini (yapay zekâya gönderilebilecek dosyaların
    üst sınırı) ve haritaya bağlı tek kullanımlık belirteci verir (10.8.1)."""
    try:
        scan, _token = await _submitted_map(request, session, layout, settings)
        if not scan.preview.files:
            raise MapError(MAP_EMPTY)
        subject = map_subject(scan)
        issued = issue_confirmation(session, request, user, Operation.TRAINING_MAP, subject)
    except (MapError, ConfirmationRefusedError) as exc:
        return _refused_map(request, user, session, exc)
    session.commit()
    return _map_step_page(request, user, status.HTTP_200_OK, scan=scan, confirmation=issued.token)


@router.post(f"{MAPS_PATH}/start", response_class=HTMLResponse)
async def start_map(
    request: Request, user: CurrentUser, session: DbSession, layout: Layout, settings: AppSettings
) -> Response:
    """11.9.5 — ikinci onayın belirteciyle toplu taramayı başlatır: çalıştırma (`kind=map`), dosya
    başına `queued` öğe, `USER_CONFIRMED` ve `TRAINING_MAP_STARTED` tek işlemdedir; harita en son
    `_egitim/haritalar/<run>.csv`'ye saklanır. Belirteçsiz ya da geçersiz belirteçte hiçbir şey
    yapılmaz (400). Taramayı işçi yürütür."""
    try:
        scan, token = await _submitted_map(request, session, layout, settings)
        if not scan.preview.files:
            raise MapError(MAP_EMPTY)
        run = create_run(
            session, kind=TrainingRunKind.MAP, created_by=user.username, map_name=scan.name
        )
        confirm_operation(
            session,
            request,
            user,
            Operation.TRAINING_MAP,
            map_subject(scan),
            token,
            event_target={
                "run_id": run.id,
                "files": scan.preview.files,
                "ai_possible": scan.preview.ai_possible,
            },
        )
        start_map_scan(
            session,
            layout,
            run,
            scan.plan,
            scan.preview,
            content=scan.content,
            actor=user.username,
        )
    except (MapError, ConfirmationRefusedError, OSError) as exc:
        return _refused_map(request, user, session, exc)
    session.commit()
    return RedirectResponse(
        f"{TRAINING_PATH}?{urlencode({'run': run.id, 'notice': 'map_started'})}",
        status.HTTP_303_SEE_OTHER,
    )
