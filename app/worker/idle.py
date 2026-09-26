"""İşçinin boş-zaman işleri çerçevesi (PRD 11.5.5, 11.9.3; PLAN.md §C85).

Yükleme kuyruğu boşken işçi, yapay zekâ gerektiren arka plan işlerinden (aday tür incelemesi — tm
113, eğitim modu sınıflandırması — tm 117, 120) **tek birim** yürütür. Kural "inceleme yükleme
işlerini bekletmez"dir: `Worker._loop` önce kuyruğu tarar (`run_once`), yalnız `run_once()` `False`
döndüğünde en çok bir boş-zaman birimi koşar ve sonra yeniden kuyruğa döner. `run_once`'ın
sözleşmesi değişmez. Boş-zaman işi plan dışıdır: partiye ve planına dokunmaz (K9).

**İş.** `IdleJob` tek birim iş yapar (`run_one`), yaptıysa `True` döner. İşleri `create_worker`
verir (`default_idle_jobs`); doğrudan `Worker(...)` kurulumunda liste boştur. Sağlayıcı ayarsızsa
(`provider` yok) boş-zaman işleri koşmaz. Birimin istisnası döngüyü düşürmez; loga yalnız hata türü
yazılır (kişisel değer taşıyabilir, CONVENTIONS §6).

**Birim** (`run_idle_unit`) üç kısa adımdır ve sağlayıcı çağrısı boyunca veritabanı oturumu açık
tutulmaz — SQLite'ta açık işlem yazma kilidini tutar ve yükleme işini bekletirdi (`app.db.session`):

1. Sahiplen ve commit et; ayrı kısa bir işlemde girdiyi oku (`read`), oturumu kapat.
2. Sağlayıcıyı çağır (`call`); kullanım `measure_usage` ile ölçülür.
3. Yeni işlemde sahiplik hâlâ bu birimdeyse sonucu yaz (`write`) ve sahipliği bırak; değilse
   (süresi doldu ve başka bir işleyici aldı) hiçbir şey yazma.

**Sahiplenme** tüketen tablonun satırındadır (`IdleClaimMixin`: belirteç, süre, deneme sayacı;
alanlar tüketen görevin göçündedir, tanım döngüsüz içe aktarma için `app.db.models`'tadır) ve
`IdleTable` kurallarıyla yürür — `app.worker.queue`'nun iş kirası deseni: sahiplenme koşullu
güncellemedir (aynı satırı iki işleyici alamaz); her alış deneme sayacını bir artırır; satırın kime
ait olduğu sürenin değil belirtecin işidir; süresi dolmuş sahiplenme başka işleyicice geri
alınabilir. `WORKER_MAX_ATTEMPTS` deneme tükenince satır kalıcı başarısız olur (`IdleTable.failed`
değerleri) ve bir daha denenmez: birim hatayla bittiyse hemen, işleyicisi yarıda kaldıysa
sahiplenmesinin süresi dolunca (`abandon_exhausted`).

**Maliyet.** Birimin yapay zekâ çağrılarının olayı `usage` (ve gerekirse `usage_by_model`) verisini
`app.events.usage_event_data` ile taşır; olay türü `USAGE_EVENT_TYPES`'a eklenince maliyet paneli
(13.1.1, `app.web.routers.metrics`) onu sayar.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import ColumnElement, and_, inspect, or_, select, update
from sqlalchemy.orm import InstrumentedAttribute, Session, sessionmaker

from app.ai.provider import AnalysisProvider
from app.ai.usage import UsageMeter, measure_usage
from app.config import Settings
from app.db.models import IdleClaimMixin, utcnow
from app.storage import DataLayout
from app.worker.queue import new_claim_token

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IdleContext:
    """Boş-zaman biriminin kullandığı işleyici kaynakları."""

    session_factory: sessionmaker[Session]
    layout: DataLayout
    settings: Settings
    provider: AnalysisProvider


@runtime_checkable
class IdleJob(Protocol):
    """Kuyruk boşken işçinin yürüttüğü arka plan işi. `name` loglarda işin adıdır."""

    name: str

    def run_one(self, context: IdleContext) -> bool:
        """Tek birim iş yapar; yaptıysa (bir satır sahiplenildiyse) `True`, iş yoksa `False`."""
        ...


def default_idle_jobs(settings: Settings) -> tuple[IdleJob, ...]:
    """`create_worker`'ın işçiye verdiği boş-zaman işleri. Tüketen görevler işini buraya ekler:
    aday tür incelemesi (11.5.5, `app.catalog.propose`)."""
    # İş modülü bu modülü içe aktarır; paket başlatılırken döngü olmasın diye burada alınır.
    from app.catalog.propose import CandidateExaminationJob

    return (CandidateExaminationJob(),)


@dataclass(frozen=True, slots=True)
class IdleClaim:
    """Bir işleyicinin sahiplendiği satır: birincil anahtarı ve alışın belirteci."""

    row_id: Any
    token: str


@dataclass(frozen=True)
class IdleTable[M: IdleClaimMixin]:
    """Tüketen tablonun sahiplenme kuralları (modül açıklaması).

    `pending` işi bekleyen satırların koşuludur (ör. incelenmemiş, karara bağlanmamış aday);
    `failed` deneme tükenince satıra yazılan değerlerdir ve satırı `pending` dışına çıkarmalıdır.
    Tablonun birincil anahtarı tek sütundur. İşlevler commit etmez — işlem sınırı çağıranındır.
    """

    model: type[M]
    pending: Callable[[], ColumnElement[bool]]
    failed: Mapping[str, object]

    @property
    def _key(self) -> InstrumentedAttribute[Any]:
        (column,) = inspect(self.model).primary_key
        return getattr(self.model, column.key)

    def _claimable(self, *, now: datetime, max_attempts: int) -> ColumnElement[bool]:
        model = self.model
        return and_(
            self.pending(),
            model.idle_attempts < max_attempts,
            or_(model.idle_claimed_by.is_(None), model.idle_claim_expires_at < now),
        )

    def claim(
        self,
        session: Session,
        *,
        token: str,
        lease_seconds: int,
        max_attempts: int,
        now: datetime | None = None,
    ) -> IdleClaim | None:
        """Sıradaki işi bekleyen satırı `token` ile sahiplenir: sahipsiz ya da sahiplenmesinin
        süresi dolmuş, `max_attempts`'a varmamış ilk satır. Satır yoksa `None`."""
        now = now or utcnow()
        claimable = self._claimable(now=now, max_attempts=max_attempts)
        row_id = session.scalars(
            select(self._key)
            .where(claimable)
            .order_by(self._key)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if row_id is None:
            return None
        # Koşullu güncelleme: satır bu arada başka bir işleyiciye geçtiyse hiçbir satır değişmez.
        result = session.execute(
            update(self.model)
            .where(and_(self._key == row_id, claimable))
            .values(
                idle_claimed_by=token,
                idle_claim_expires_at=now + timedelta(seconds=lease_seconds),
                idle_attempts=self.model.idle_attempts + 1,
            )
            .execution_options(synchronize_session="fetch")
        )
        if not result.rowcount:
            return None
        return IdleClaim(row_id, token)

    def owned(self, session: Session, claim: IdleClaim) -> M | None:
        """Satır hâlâ `claim`'inse kilitleyip taze okur; değilse (başka işleyiciye geçti, bitti,
        ya da bırakıldı) `None`. Sahiplik sürenin değil belirtecin işidir."""
        row = session.scalars(
            select(self.model)
            .where(self._key == claim.row_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
        if row is None or row.idle_claimed_by != claim.token:
            return None
        return row

    def release(self, row: M, *, max_attempts: int) -> bool:
        """Hatayla biten birimin satırını bırakır; deneme tükendiyse `failed` değerlerini yazar.
        Kalıcı başarısız olduysa `True`. Deneme sayacı geri alınmaz."""
        final = row.idle_attempts >= max_attempts
        if final:
            for key, value in self.failed.items():
                setattr(row, key, value)
        self.clear(row)
        return final

    @staticmethod
    def clear(row: IdleClaimMixin) -> None:
        """Satırın sahiplenmesini kaldırır (deneme sayacı kalır)."""
        row.idle_claimed_by = None
        row.idle_claim_expires_at = None

    def abandon_exhausted(
        self, session: Session, *, max_attempts: int, now: datetime | None = None
    ) -> list[Any]:
        """Denemesi tükenmiş ve kimsenin elinde olmayan (sahipsiz ya da süresi dolmuş) bekleyen
        satırlara `failed` değerlerini yazar; birincil anahtarlarını döner."""
        now = now or utcnow()
        model = self.model
        rows = session.scalars(
            select(model)
            .where(
                self.pending(),
                model.idle_attempts >= max_attempts,
                or_(model.idle_claimed_by.is_(None), model.idle_claim_expires_at < now),
            )
            .order_by(self._key)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        ).all()
        for row in rows:
            for key, value in self.failed.items():
                setattr(row, key, value)
            self.clear(row)
        session.flush()
        key_name = self._key.key
        return [getattr(row, key_name) for row in rows]


def run_idle_unit[M: IdleClaimMixin, I, O](
    context: IdleContext,
    table: IdleTable[M],
    *,
    name: str,
    read: Callable[[Session, M], I],
    call: Callable[[AnalysisProvider, I], O],
    write: Callable[[Session, M, O, UsageMeter], None],
    failed: Callable[[Session, M, UsageMeter, bool], None] | None = None,
) -> bool:
    """Tek boş-zaman birimi (modül açıklaması); bir satır sahiplenildiyse `True`.

    `read` girdiyi sahiplenilmiş satırdan okur (oturum sonra kapanır; dönen değer oturumdan bağımsız
    olmalıdır), `call` sağlayıcıyı açık oturum olmadan çağırır, `write` sonucu aynı işlemde satıra
    yazar (olayını da; kullanım `meter`'dadır). Adımlardan biri hata verirse satır bırakılır —
    deneme tükendiyse kalıcı başarısız olur — `failed(session, row, meter, final)` varsa aynı
    işlemde çağrılır (ör. olay) ve istisna yükselir: işleyici yalnız türünü loglar.
    """
    settings = context.settings
    max_attempts = settings.worker_max_attempts
    with context.session_factory() as session:
        for row_id in table.abandon_exhausted(session, max_attempts=max_attempts):
            logger.error("Boş-zaman işi %s: kayıt %s bırakıldı, denemeleri tükendi", name, row_id)
        claim = table.claim(
            session,
            token=new_claim_token(),
            lease_seconds=settings.worker_lease_seconds,
            max_attempts=max_attempts,
        )
        session.commit()
    if claim is None:
        return False

    with measure_usage() as meter:
        try:
            with context.session_factory() as session:
                row = table.owned(session, claim)
                if row is None:
                    return _lost(name, claim)
                source = read(session, row)
                session.rollback()  # okuma işlemi de SQLite yazma kilidini tutar
            result = call(context.provider, source)
            with context.session_factory() as session:
                row = table.owned(session, claim)
                if row is None:
                    return _lost(name, claim)
                write(session, row, result, meter)
                table.clear(row)
                session.commit()
        except Exception:
            _give_back(context, table, claim, meter, failed)
            raise
    return True


def _give_back[M: IdleClaimMixin](
    context: IdleContext,
    table: IdleTable[M],
    claim: IdleClaim,
    meter: UsageMeter,
    failed: Callable[[Session, M, UsageMeter, bool], None] | None,
) -> None:
    with context.session_factory() as session:
        row = table.owned(session, claim)
        if row is None:
            return
        final = table.release(row, max_attempts=context.settings.worker_max_attempts)
        if failed is not None:
            failed(session, row, meter, final)
        session.commit()


def _lost(name: str, claim: IdleClaim) -> bool:
    logger.warning("Boş-zaman işi %s: kayıt %s başka bir işleyiciye geçti", name, claim.row_id)
    return True
