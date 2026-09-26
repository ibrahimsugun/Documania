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

Sekme belge içeriğini değiştirmez (10.9.1, K11, K17): yalnız kopyalar, kaydeder ve gösterir. Ekranda
kişisel değer yalnız dosya adındadır (CONVENTIONS §6); notlar ve dökümler kişisel değer taşımaz.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
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
from app.storage import ContentMismatchError, DataLayout
from app.storage.examples import example_path, list_examples
from app.training import (
    PENDING_STATUSES,
    ExampleDecisionError,
    ItemNotPlaceableError,
    KnownType,
    KnownTypes,
    UnknownTypeError,
    check_move,
    check_remove,
    create_run,
    load_example_inventory,
    load_known_types,
    move_example,
    place_example,
    remove_example,
    stage_and_recognize,
    verify_examples,
)
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
RUN_LIMIT = 20
ITEM_LIMIT = 200

NO_FILE_MESSAGE = "Yüklenecek dosya seçilmedi."
UNKNOWN_HINT_MESSAGE = "Beklenen tür bilinen türlerden biri değil; listeden seçin."
UNKNOWN_TYPE_MESSAGE = "Seçilen tür bilinen türlerden biri değil; listeden seçin."
ITEM_NOT_FOUND = "Eğitim öğesi bulunamadı."
NOT_MANUALLY_PLACEABLE = (
    "Bu öğe elle yerleştirilemez: yalnız Yerleştirilemedi ya da Çelişki durumundaki öğe türe "
    "yerleştirilir."
)
FILE_MISSING = "Öğenin eğitim kopyası okunamadı; yerleştirilmedi."
TYPE_NOT_FOUND = "Bilinen tür bulunamadı."
EXAMPLE_NOT_FOUND = "Örnek bulunamadı."
MANUAL_CHECK_TEXT = "Elle kontrol gerekli"
REMOVED_LABEL_TEXT = "Örneklerden çıkarıldı"
EXAMPLE_RECORD_NOT_FOUND = "Eğitim örneği bulunamadı."
MOVE_FAILED = "Örnek dosyası taşınamadı; hiçbir şey değişmedi."

# Etiket kararının iki aşamalı onay metinleri (11.9.4) — PLAN.md §D58'den BİREBİR; §20.6'nın
# dışındadır (K16 dışı, REANALYZE emsali). `tests/web/test_training_decisions.py` §D58 ile
# karşılaştırır. Yer tutucular çalışma zamanında doldurulur (`_fill`).
FILE_PLACEHOLDER = "<Dosya>"
OLD_TYPE_PLACEHOLDER = "<Eski tür>"
NEW_TYPE_PLACEHOLDER = "<Yeni tür>"
TYPE_PLACEHOLDER = "<Tür>"
MOVE_FIRST_CONFIRMATION = (
    "<Dosya> örneğini <Eski tür> türünden <Yeni tür> türüne taşımak üzeresiniz. Emin misiniz?"
)
MOVE_SECOND_CONFIRMATION = (
    "Örnek artık <Yeni tür> türünün örneklerinde durur ve o türün açıklama üretimini etkiler. "
    "Son kararınız mı?"
)
REMOVE_FIRST_CONFIRMATION = (
    "<Dosya> örneğini <Tür> örneklerinden çıkarmak üzeresiniz. Emin misiniz?"
)
REMOVE_SECOND_CONFIRMATION = (
    "Dosya silinmez, eğitim arşivine taşınır ve bu türün açıklama üretimine artık girmez. "
    "Son kararınız mı?"
)

MANUALLY_PLACEABLE = frozenset({TrainingItemStatus.UNPLACED, TrainingItemStatus.CONFLICT})
"""İK'nın "Türe yerleştir"ini bekleyen durumlar (11.9.1). Kararı sistemde bekleyen öğe (`queued`,
`ai_pending`) elle yerleştirilmez: işçinin incelemesiyle yarışmasın."""

STATUS_LABELS: dict[str, str] = {
    TrainingItemStatus.QUEUED: "Sırada",
    TrainingItemStatus.PLACED: "Yerleşti",
    TrainingItemStatus.AI_PENDING: "Yapay zekâ incelemesi bekliyor",
    TrainingItemStatus.SKIPPED: "Zaten örnek",
    TrainingItemStatus.FAILED: "Hatalı",
    TrainingItemStatus.UNPLACED: "Yerleştirilemedi",
    TrainingItemStatus.CONFLICT: "Çelişki",
    TrainingItemStatus.REVIEW: "İnceleme gerekli",
}
METHOD_LABELS: dict[str, str] = {
    TrainingMethod.MECHANICAL: "Mekanik",
    TrainingMethod.AI: "Yapay zekâ",
    TrainingMethod.MANUAL: "İK (elle)",
    ExampleMethod.LEGACY: "Eğitimden önce",
}
LABEL_TEXTS: dict[str, str] = {
    ExampleLabel.AI_DECISION: "AI kararı",
    ExampleLabel.VERIFIED: "Doğrulandı",
}
RUN_KIND_LABELS: dict[str, str] = {
    TrainingRunKind.UPLOAD: "Yükleme",
    TrainingRunKind.MAP: "Harita",
}
RUN_STATUS_LABELS: dict[str, str] = {
    TrainingRunStatus.RUNNING: "Sürüyor",
    TrainingRunStatus.DONE: "Bitti",
}

# Süzgeç anahtarı → etiket (sıra ekrandaki sıradır; boş anahtar "Tümü").
ITEM_FILTERS: tuple[tuple[str, str], ...] = (
    ("", "Tümü"),
    ("ai", "AI kararı"),
    ("unplaced", "Yerleştirilemedi"),
    ("conflict", "Çelişki"),
    ("mechanical", "Mekanik"),
    ("failed", "Hatalı"),
)
FILTER_KEYS = frozenset(key for key, _ in ITEM_FILTERS)

# Bilinen belgeler görünümünün süzgeci.
KNOWN_FILTERS: tuple[tuple[str, str], ...] = (
    ("", "Tümü"),
    ("examples", "Örneği olanlar"),
    ("ai", "AI kararı olanlar"),
)
KNOWN_FILTER_KEYS = frozenset(key for key, _ in KNOWN_FILTERS)

NOTICES: dict[str, str] = {
    "uploaded": (
        "Yükleme alındı ve mekanik tanıma bitti. Mekanik tanınmayan dosyaları işçi yapay zekâyla "
        "inceler; sonuçlar bu tabloda güncellenir."
    ),
    "placed": "Öğe seçilen türe yerleşti; örnek doğrulanmış olarak kaydedildi.",
    "skipped": "Öğe yerleşmedi: aynı içerik bu türde zaten örnek.",
    "conflict": "Öğe yerleşmedi: aynı içerik başka bir türde örnek. Notu inceleyin.",
    "verified": 'Seçilen "AI kararı" örnekleri doğrulandı; elle kontrol ikonu kalktı.',
    "verify_none": 'Doğrulanacak "AI kararı" örneği seçilmedi; hiçbir şey değişmedi.',
    "moved": "Örnek bu türe taşındı ve doğrulanmış olarak kaydedildi.",
    "removed": "Örnek örneklerden çıkarıldı: dosya silinmedi, eğitim arşivine taşındı.",
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


def _results_url(path: str, run_id: int | None, item_filter: str) -> str:
    query = {key: value for key, value in (("run", run_id), ("filter", item_filter)) if value}
    return f"{path}?{urlencode(query)}" if query else path


def _counts_text(counts: dict[str, int]) -> str:
    parts = [
        f"{counts[status]} {STATUS_LABELS[status].lower()}"
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
    if item_filter in ("unplaced", "conflict", "failed"):
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
    )


def build_results_view(
    session: Session, known: KnownTypes, *, run_id: int | None, item_filter: str
) -> ResultsView:
    """Son çalıştırmalar ve (seçili çalıştırmanın ya da hepsinin) öğeleri, en yeni üstte."""
    runs = session.scalars(select(TrainingRun).order_by(TrainingRun.id.desc()).limit(RUN_LIMIT))
    run_rows = [
        RunRow(
            id=run.id,
            kind=RUN_KIND_LABELS.get(run.kind, run.kind),
            created_at=_format_ts(run.created_at),
            created_by=run.created_by,
            status=run.status,
            status_label=RUN_STATUS_LABELS.get(run.status, run.status),
            counts=_counts_text(run.counts_json or {}),
            url=_results_url(TRAINING_PATH, run.id, item_filter),
            selected=run.id == run_id,
        )
        for run in runs
    ]

    scope = select(TrainingItem)
    if run_id is not None:
        scope = scope.where(TrainingItem.run_id == run_id)
    filtered = _filtered(scope, item_filter)
    total = session.scalar(select(func.count()).select_from(filtered.subquery())) or 0
    items = list(session.scalars(filtered.order_by(TrainingItem.id.desc()).limit(ITEM_LIMIT)))
    examples = _examples_of(session, (item.id for item in items))
    pending_scope = scope.where(TrainingItem.status.in_([s.value for s in PENDING_STATUSES]))
    pending = session.scalar(select(func.count()).select_from(pending_scope.subquery())) or 0

    rows = [_item_row(item, known, examples.get(item.id)) for item in items]
    return ResultsView(
        runs=run_rows,
        items=rows,
        total=total,
        run_id=run_id,
        filter=item_filter,
        filters=[
            (key, label, _results_url(TRAINING_PATH, run_id, key), key == item_filter)
            for key, label in ITEM_FILTERS
        ],
        poll=pending > 0,
        poll_url=_results_url(ITEMS_PATH, run_id, item_filter),
        pending=pending,
        all_runs_url=_results_url(TRAINING_PATH, None, item_filter),
        current_url=_results_url(TRAINING_PATH, run_id, item_filter),
        verifiable=sum(1 for row in rows if row.manual_check),
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
) -> HTMLResponse:
    known = load_known_types(session)
    results = build_results_view(session, known, run_id=run_id, item_filter=item_filter)
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
) -> HTMLResponse:
    return _training_page(
        request,
        user,
        session,
        run_id=_run_param(run),
        item_filter=_filter_param(filter),
        provider_problem=provider_problem,
        notice=notice,
    )


@router.get(ITEMS_PATH, response_class=HTMLResponse)
def training_items(
    request: Request,
    session: DbSession,
    run: str | None = None,
    filter: str | None = None,
) -> HTMLResponse:
    """Sonuç bölümü (HTMX yoklamasının hedefi): kararı sistemde bekleyen öğe varken yenilenir."""
    known = load_known_types(session)
    results = build_results_view(
        session, known, run_id=_run_param(run), item_filter=_filter_param(filter)
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
            errors.append(str(exc.detail))
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
    """11.9.1 "Türe yerleştir" — `unplaced` ya da `conflict` öğe İK'nın seçtiği bilinen türe
    yerleşir: `method=manual`, etiket `verified`, olay kullanıcı adıyla. Yerleştirme yalnız
    kopyalar ve kaydeder (K11)."""
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
        )
    except (ItemNotPlaceableError, ContentMismatchError, OSError):
        return refused(status.HTTP_409_CONFLICT, FILE_MISSING)
    session.commit()
    query = urlencode({"run": run_id, "notice": placement.status.value})
    return RedirectResponse(f"{TRAINING_PATH}?{query}#item-{item_id}", status.HTTP_303_SEE_OTHER)


# --- bilinen belgeler -------------------------------------------------------------------------


def _label_counts(session: Session) -> dict[tuple[str, str], int]:
    rows = session.execute(
        select(ExampleFileRecord.type_slug, ExampleFileRecord.label, func.count())
        .where(ExampleFileRecord.label.is_not(None), ExampleFileRecord.removed_at.is_(None))
        .group_by(ExampleFileRecord.type_slug, ExampleFileRecord.label)
    ).tuples()
    return {(slug, label): count for slug, label, count in rows if label is not None}


def _source_text(known: KnownType) -> str:
    return "Katalog" if known.in_catalog else "Önerilen"


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
        text = _fill(second if confirmation else first, **decision.values)
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
        code, message = exc.status_code, str(exc.detail)
    elif isinstance(exc, UnknownTypeError):
        code, message = status.HTTP_422_UNPROCESSABLE_CONTENT, UNKNOWN_TYPE_MESSAGE
    elif isinstance(exc, ConfirmationRefusedError):
        code, message = status.HTTP_400_BAD_REQUEST, CONFIRMATION_REFUSED
    elif isinstance(exc, ExampleDecisionError):
        code, message = status.HTTP_409_CONFLICT, str(exc)
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
