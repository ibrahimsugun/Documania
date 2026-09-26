"""Maliyet ölçümü görünümü (PRD 13.1.1): sayfa, parti ve ay bazında token ve maliyet.

Kaynak olay logudur (K15): sayfa analizi olayları (`PAGE_ANALYZED`, `PAGE_ANALYSIS_FAILED`) ve
aday tür incelemesi olayı (`CANDIDATE_TYPE_EXAMINED`, 11.5.5; `app.events.USAGE_EVENT_TYPES`)
sağlayıcıya harcatılan token toplamını `usage` alanında taşır (`app.pipeline.analyze`,
`app.catalog.propose`). Görünüm yalnız okur; hiçbir kayıt ve belge değişmez.

- `GET /metrics` aylık ve parti bazında toplamları gösterir. Ay, olayın UTC zamanındandır. Parti
  tablosu en son analiz edilen `BATCH_LIMIT` partiyi listeler; her satır parti sayfasına bağlanır.
- `GET /metrics/uploads/{upload_id}` bir partinin sayfa bazında dökümüdür: aynı sayfa yeniden
  analiz edildiyse (K18) harcamaların toplamı, analiz sayısıyla birlikte.

**Maliyet gösterim anında hesaplanır.** Olay yalnız ölçümü (model adı ve token sayıları) taşır;
maliyet, olaydaki modelin fiyatıyla çarpımıdır. Fiyat `app.ai.pricing`'den gelir: önce `.env`'deki
`AI_MODEL_PRICES`, sonra paketle gelen yerleşik tablo (`app/ai/model_prices.yaml`); önbellekten
okunan girdi tokenı fiyatın önbellek oranıyla hesaplanır. Sayfa, görülen her modelin hangi
kayıtla ve hangi kaynaktan fiyatlandığını "Kullanılan fiyatlar" bölümünde gösterir. Ucuz model
ön elemesi (13.2.1) yapılan sayfa iki modele harcatmış olabilir: olay tokenların modellere
dağılımını (`usage_by_model`) taşıyorsa her pay kendi modelinin fiyatıyla hesaplanır.
Dağılım bozuksa ya da toplamı `usage`'a eşit değilse yok sayılır ve toplam olayın
`model`'ine yazılır. Fiyatı tanımlı olmayan modelin tokenları sayılır ama maliyete girmez:
hiçbiri fiyatlanamıyorsa maliyet "—", bir kısmı fiyatlanıyorsa "en az" ile başlar. Kullanım
kaydı olmayan analizler (ölçüm eklenmeden önceki partiler, kullanım bildirmeyen sağlayıcı)
"ölçülmemiş" sütununda sayılır, toplamlara girmez.

Sayfa analizi (ve fotoğraf kontrolü) ile işçinin aday tür incelemesi ölçülür. İnceleme bir
partiye ait değildir: toplamda ve ay satırında sayılır, parti tablosunda görünmez. Tür açıklaması ve
Telegram belge isteği çağrıları bu görünümde yoktur (bkz. PLAN.md §C70).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.pricing import PriceBook, PriceSource, price_book
from app.ai.usage import TokenUsage, token_cost
from app.config import ModelPrice, Settings, get_settings
from app.db.models import Event, Upload, UploadFile
from app.db.session import get_session
from app.events import USAGE_BY_MODEL_DATA_KEY, USAGE_DATA_KEY, USAGE_EVENT_TYPES
from app.web.auth import PanelUser, require_panel_user
from app.web.templating import render_page

router = APIRouter(tags=["metrics"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]

BATCH_LIMIT = 100
"""Parti tablosunda listelenen en çok parti (en son analiz edilenden geriye)."""

UPLOAD_NOT_FOUND = "Parti bulunamadı."
UNKNOWN = "—"
COST_STEP = Decimal("0.0001")
NO_MODEL = "(model adı yok)"
ACTIVE_KEY = "metrics"

Prices = Mapping[str, ModelPrice] | PriceBook

SOURCE_LABELS = {
    PriceSource.SETTINGS: ".env (AI_MODEL_PRICES)",
    PriceSource.BUILTIN: "yerleşik tablo",
}
NO_PRICE = "fiyat yok"


@dataclass(frozen=True, slots=True)
class UsageEvent:
    """Token ölçümü taşıması beklenen bir sayfa analizi olayı; `usage` `None` ise ölçülmemiş.

    `by_model` ön elemeli sayfada `usage`'ın modellere dağılımıdır (13.2.1); yoksa boş.
    """

    ts: datetime
    upload_id: str | None
    file_id: int | None
    page_index: int | None
    model: str | None
    usage: TokenUsage | None
    by_model: tuple[tuple[str, TokenUsage], ...] = ()

    def shares(self) -> tuple[tuple[str, TokenUsage], ...]:
        """Fiyatlanacak paylar: (model, token); dağılım yoksa bütün `usage` olayın modelinindir."""
        if self.usage is None:
            return ()
        if self.by_model:
            return self.by_model
        return ((self.model if self.model is not None else NO_MODEL, self.usage),)


@dataclass(slots=True)
class Tally:
    """Olayların toplamı: analiz ve ölçülmemiş sayısı, token toplamı, fiyatlanabilen maliyet."""

    analyses: int = 0
    unmetered: int = 0
    usage: TokenUsage = field(default_factory=TokenUsage)
    cost: Decimal = Decimal(0)
    priced: int = 0
    unpriced: int = 0
    models: set[str] = field(default_factory=set)
    unpriced_models: set[str] = field(default_factory=set)
    model_usage: dict[str, TokenUsage] = field(default_factory=dict)
    last_ts: datetime | None = None

    def add(self, event: UsageEvent, prices: Prices) -> None:
        self.analyses += 1
        if self.last_ts is None or event.ts > self.last_ts:
            self.last_ts = event.ts
        if event.usage is None:
            self.unmetered += 1
            return
        self.usage += event.usage
        for model, usage in event.shares():
            self.models.add(model)
            self.model_usage[model] = self.model_usage.get(model, TokenUsage()) + usage
            price = prices.get(model)
            if price is None:
                self.unpriced += 1
                self.unpriced_models.add(model)
            else:
                self.priced += 1
                self.cost += token_cost(usage, price)

    @property
    def cost_text(self) -> str:
        """Maliyet (USD). Hiçbir ölçülmüş çağrı fiyatlanamıyorsa "—"; bir kısmı fiyatlanamıyorsa
        fiyatlananların toplamı "en az" ile."""
        if not self.priced:
            return UNKNOWN
        text = f"{self.cost.quantize(COST_STEP, rounding=ROUND_HALF_UP)} USD"
        return f"en az {text}" if self.unpriced else text


@dataclass(frozen=True, slots=True)
class MetricsRow:
    """Bir tablo satırı; sayılar gösterime hazırdır."""

    label: str
    href: str | None
    analyses: int
    unmetered: int
    input_tokens: str
    output_tokens: str
    total_tokens: str
    cost: str
    models: str


@dataclass(frozen=True, slots=True)
class PriceRow:
    """Görülen bir modelin fiyatı: eşleşen kayıt, kaynağı, USD / milyon token ve token payı."""

    model: str
    key: str
    source: str
    input_price: str
    cached_input_price: str
    output_price: str
    input_tokens: str
    cached_input_tokens: str
    output_tokens: str


@dataclass(frozen=True, slots=True)
class PriceListInfo:
    """Yerleşik tablonun eşitleme tarihi ve kaynak sayfaları (sağlayıcı → adres)."""

    synced: str
    sources: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class MetricsOverview:
    total: MetricsRow
    months: tuple[MetricsRow, ...]
    batches: tuple[MetricsRow, ...]
    batch_count: int
    prices_configured: bool
    unpriced_models: tuple[str, ...]
    prices: tuple[PriceRow, ...] = ()
    price_list: PriceListInfo | None = None


@dataclass(frozen=True, slots=True)
class UploadMetrics:
    upload_id: str
    total: MetricsRow
    pages: tuple[MetricsRow, ...]
    prices_configured: bool
    unpriced_models: tuple[str, ...]
    prices: tuple[PriceRow, ...] = ()
    price_list: PriceListInfo | None = None


def read_usage_events(session: Session, *, upload_id: str | None = None) -> list[UsageEvent]:
    """Kullanım taşıyabilen olayları zaman sırasıyla okur (`upload_id` verilirse yalnız o parti)."""
    statement = (
        select(Event.ts, Event.upload_id, Event.file_id, Event.page_index, Event.data_json)
        .where(Event.type.in_([event_type.value for event_type in USAGE_EVENT_TYPES]))
        .order_by(Event.ts, Event.id)
    )
    if upload_id is not None:
        statement = statement.where(Event.upload_id == upload_id)
    events: list[UsageEvent] = []
    for ts, event_upload_id, file_id, page_index, data in session.execute(statement):
        data = data if isinstance(data, dict) else {}
        model = data.get("model")
        usage = TokenUsage.from_event_data(data.get(USAGE_DATA_KEY))
        events.append(
            UsageEvent(
                ts=ts,
                upload_id=event_upload_id,
                file_id=file_id,
                page_index=page_index,
                model=model if isinstance(model, str) else None,
                usage=usage,
                by_model=_usage_by_model(data.get(USAGE_BY_MODEL_DATA_KEY), usage),
            )
        )
    return events


def _usage_by_model(data: object, usage: TokenUsage | None) -> tuple[tuple[str, TokenUsage], ...]:
    """Olaydaki model dağılımı (13.2.1); yok, bozuk ya da toplamı `usage`'a eşit değilse boş —
    maliyet o zaman toplamın olayın modeline yazılmasıyla hesaplanır."""
    if usage is None or not isinstance(data, Mapping) or not data:
        return ()
    shares: list[tuple[str, TokenUsage]] = []
    total = TokenUsage()
    for model, value in data.items():
        share = TokenUsage.from_event_data(value)
        if not isinstance(model, str) or not model or share is None:
            return ()
        shares.append((model, share))
        total += share
    return tuple(shares) if total == usage else ()


def _book(prices: Prices) -> PriceBook:
    return prices if isinstance(prices, PriceBook) else PriceBook(prices)


def _price_rows(book: PriceBook, tally: Tally) -> tuple[PriceRow, ...]:
    """Tallydeki her modelin fiyat satırı (model adına göre sıralı)."""
    rows = []
    for model in sorted(tally.model_usage):
        usage = tally.model_usage[model]
        resolved = book.resolve(model)
        if resolved is None:
            key, source, prices = UNKNOWN, NO_PRICE, (UNKNOWN, UNKNOWN, UNKNOWN)
        else:
            price = resolved.price
            cached = price.cached_input_per_mtok
            key, source = resolved.key, SOURCE_LABELS[resolved.source]
            prices = (
                _usd(price.input_per_mtok),
                "girdi fiyatıyla" if cached is None else _usd(cached),
                _usd(price.output_per_mtok),
            )
        rows.append(
            PriceRow(
                model=model,
                key=key,
                source=source,
                input_price=prices[0],
                cached_input_price=prices[1],
                output_price=prices[2],
                input_tokens=_number(usage.input_tokens),
                cached_input_tokens=_number(usage.cached_input_tokens),
                output_tokens=_number(usage.output_tokens),
            )
        )
    return tuple(rows)


def _price_list_info(book: PriceBook) -> PriceListInfo | None:
    if book.price_list is None:
        return None
    return PriceListInfo(
        synced=book.price_list.synced.isoformat(),
        sources=tuple(sorted(book.price_list.sources.items())),
    )


def _usd(value: Decimal) -> str:
    """Birim fiyat: sondaki sıfırlar olmadan (`0.2`, `30`)."""
    text = format(value.normalize(), "f")
    return f"{text} USD"


def build_overview(session: Session, prices: Prices) -> MetricsOverview:
    """Tüm sayfa analizi olaylarından toplam, ay ve parti satırları."""
    prices = _book(prices)
    total = Tally()
    months: dict[str, Tally] = {}
    batches: dict[str, Tally] = {}
    for event in read_usage_events(session):
        total.add(event, prices)
        months.setdefault(event.ts.strftime("%Y-%m"), Tally()).add(event, prices)
        if event.upload_id is not None:
            batches.setdefault(event.upload_id, Tally()).add(event, prices)
    newest_first = sorted(
        batches.items(), key=lambda item: (item[1].last_ts, item[0]), reverse=True
    )
    return MetricsOverview(
        total=_row("Toplam", total),
        months=tuple(_row(month, months[month]) for month in sorted(months, reverse=True)),
        batches=tuple(
            _row(upload_id, tally, href=f"/metrics/uploads/{upload_id}")
            for upload_id, tally in newest_first[:BATCH_LIMIT]
        ),
        batch_count=len(batches),
        prices_configured=bool(prices),
        unpriced_models=tuple(sorted(total.unpriced_models)),
        prices=_price_rows(prices, total),
        price_list=_price_list_info(prices),
    )


def build_upload_metrics(session: Session, upload: Upload, prices: Prices) -> UploadMetrics:
    """Bir partinin sayfa bazında dökümü; aynı sayfanın yeniden analizleri toplanır (K18)."""
    prices = _book(prices)
    file_names = {
        file_id: name
        for file_id, name in session.execute(
            select(UploadFile.id, UploadFile.original_name).where(UploadFile.upload_id == upload.id)
        )
    }
    total = Tally()
    pages: dict[tuple[int | None, int | None], Tally] = {}
    for event in read_usage_events(session, upload_id=upload.id):
        total.add(event, prices)
        pages.setdefault((event.file_id, event.page_index), Tally()).add(event, prices)

    def _order(key: tuple[int | None, int | None]) -> tuple[int, int, int, int]:
        file_id, page_index = key
        return (
            file_id is None,
            file_id or 0,
            page_index is None,
            page_index or 0,
        )

    def _label(key: tuple[int | None, int | None]) -> str:
        file_id, page_index = key
        name = file_names.get(file_id) if file_id is not None else None
        page = f"sayfa {page_index + 1}" if page_index is not None else "sayfa bilinmiyor"
        return f"{name} — {page}" if name is not None else page.capitalize()

    return UploadMetrics(
        upload_id=upload.id,
        total=_row("Toplam", total),
        pages=tuple(_row(_label(key), pages[key]) for key in sorted(pages, key=_order)),
        prices_configured=bool(prices),
        unpriced_models=tuple(sorted(total.unpriced_models)),
        prices=_price_rows(prices, total),
        price_list=_price_list_info(prices),
    )


def _row(label: str, tally: Tally, *, href: str | None = None) -> MetricsRow:
    return MetricsRow(
        label=label,
        href=href,
        analyses=tally.analyses,
        unmetered=tally.unmetered,
        input_tokens=_number(tally.usage.input_tokens),
        output_tokens=_number(tally.usage.output_tokens),
        total_tokens=_number(tally.usage.total_tokens),
        cost=tally.cost_text,
        models=", ".join(sorted(tally.models)) or UNKNOWN,
    )


def _number(value: int) -> str:
    """Binlik ayraçlı sayı (Türkçe yazım: 12.345)."""
    return f"{value:,}".replace(",", ".")


@router.get("/metrics", response_class=HTMLResponse)
def metrics_page(
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HTMLResponse:
    overview = build_overview(session, price_book(settings))
    # Okuma işlemi de SQLite'ta yazma kilidini tutar (`app.db.session`): sayfa çizilirken
    # arka plandaki bir işleyici beklemesin.
    session.rollback()
    return render_page(
        request, "metrics.html", user=user, active=ACTIVE_KEY, overview=overview, limit=BATCH_LIMIT
    )


@router.get("/metrics/uploads/{upload_id}", response_class=HTMLResponse)
def metrics_upload_page(
    upload_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HTMLResponse:
    upload = session.get(Upload, upload_id)
    if upload is None:
        session.rollback()
        return render_page(
            request,
            "metrics_upload.html",
            user=user,
            active=ACTIVE_KEY,
            status_code=status.HTTP_404_NOT_FOUND,
            error=UPLOAD_NOT_FOUND,
        )
    view = build_upload_metrics(session, upload, price_book(settings))
    session.rollback()
    return render_page(request, "metrics_upload.html", user=user, active=ACTIVE_KEY, metrics=view)
