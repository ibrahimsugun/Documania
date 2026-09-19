"""Kalıcı işçi kuyruğunun işleyicisi (PRD 13.3.1; PLAN.md §C72).

**İşi yürütme.** `run_claimed_upload` alınmış işin partisini `resume_upload` ile durduğu aşamadan
sonuna kadar işler: yeni parti baştan, yarıda kalmış parti kaldığı aşamadan (`executing`'de yapay
zekâ çağrılmaz, commit edilmiş plan uygulanır — K9). Orkestrasyonun geçiş kancası (`checkpoint`)
partinin her geçişinde, aynı işlemde, işin hâlâ bu işleyicide olduğunu denetler ve kirayı yeniler;
parti son duruma vardığı işlemde iş `finished` olur. Böylece parti durumu ile iş durumu hiçbir an
ayrışmaz. İş başka bir işleyiciye geçmişse eski işleyici partiye bir daha yazmaz (`LeaseLostError`).

Uzun süren bir adımda (analiz tek işlemdir, C43) kira ayrıca bir kalp atışı iş parçacığıyla kiranın
üçte birinde bir, kendi oturumunda yenilenir. SQLite'ta işleyen oturum adım boyunca yazma kilidini
tuttuğu için kalp atışı o sürede bekler ya da yenileyemez; zararı yoktur: kilit tutulurken işi
kimse alamaz, kilit geçişte bırakılır ve kira o geçişte zaten yenilenmiştir.

**Kuyruk döngüsü.** `Worker` panel sürecinde açılışta başlar (`app.main`, `start_worker`) ve
`WORKER_POLL_SECONDS` aralıkla kuyruğu tarar: önce kirası en çok deneme kadar dolmuş işlerden
vazgeçer, sonra sıradaki işi (bekleyen ya da kirası dolmuş) alıp işler; iş buldukça beklemeden
devam eder. Uygulama yeniden başlayınca yarıda kalan partinin kirası dolar ve döngü onu kaldığı
aşamadan sürdürür — kabul kriteri budur. Kapanışta döngü süren işi kesmez; süreç giderse iş kirası
dolunca yeniden alınır. Yapay zekâ sağlayıcısı kurulamıyorsa döngü başlamaz, işler kuyrukta bekler.

Hata metni loga yazılmaz (kişisel değer taşıyabilir, CONVENTIONS §6); yalnız türü ve partinin
kimliği yazılır.
"""

from __future__ import annotations

import logging
import threading

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.provider import AnalysisProvider, ProviderConfigError, create_provider
from app.config import Settings
from app.db.models import Upload, UploadStatus
from app.db.session import create_db_engine, create_session_factory
from app.pipeline.orchestrate import (
    UPLOAD_TRANSITIONS,
    Checkpoint,
    ProcessedUpload,
    UploadTransitionError,
    resume_upload,
)
from app.storage import DataLayout
from app.worker.queue import (
    Claim,
    LeaseLostError,
    abandon_exhausted,
    claim_next,
    claim_upload,
    finish_claim,
    new_claim_token,
    renew_claim,
)

logger = logging.getLogger(__name__)

# Kapanışta süren işin bitmesi beklenmez; döngünün yalnız taramayı bırakması beklenir.
STOP_TIMEOUT_SECONDS = 5.0


def lease_checkpoint(claim: Claim, *, lease_seconds: int) -> Checkpoint:
    """Geçiş kancası: işin sahipliğini denetler, kirayı yeniler; son durumda işi bitirir."""

    def checkpoint(session: Session, status: UploadStatus) -> None:
        if UPLOAD_TRANSITIONS[status]:
            renew_claim(session, claim, lease_seconds=lease_seconds)
        else:
            finish_claim(session, claim)

    return checkpoint


def run_claimed_upload(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    claim: Claim,
    *,
    settings: Settings,
    provider: AnalysisProvider,
    heartbeat_seconds: float | None = None,
) -> ProcessedUpload | None:
    """Alınmış işin partisini sonuna kadar işler (modül açıklaması).

    Sonuç `resume_upload`'ınkidir. İş bu arada başka bir işleyiciye geçtiyse ya da parti zaten son
    durumdaysa (iş yalnız `finished` işaretlenir) `None`. `heartbeat_seconds` kalp atışı aralığıdır
    (varsayılan kiranın üçte biri).
    """
    lease = settings.worker_lease_seconds
    heartbeat = _Heartbeat(
        session_factory, claim, lease_seconds=lease, interval=heartbeat_seconds or lease / 3
    )
    heartbeat.start()
    try:
        with session_factory() as session:
            upload = session.get_one(Upload, claim.upload_id)
            try:
                return resume_upload(
                    session,
                    layout,
                    upload,
                    settings=settings,
                    provider=provider,
                    checkpoint=lease_checkpoint(claim, lease_seconds=lease),
                )
            except UploadTransitionError:
                # Parti son durumda (ör. iş dışından işlendi): işlenecek bir şey yok, iş biter.
                finish_claim(session, claim)
                session.commit()
                return None
    except LeaseLostError:
        logger.warning(
            "Parti %s bu işleyicide bırakıldı: iş başka bir işleyiciye geçti", claim.upload_id
        )
        return None
    finally:
        heartbeat.stop()


def claim_and_run(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    upload_id: str,
    *,
    settings: Settings,
    provider: AnalysisProvider,
) -> ProcessedUpload | None:
    """Partinin kuyrukta bekleyen işini alır ve işler; iş beklemiyorsa (başka bir işleyici almış,
    parti işlenmiş ya da yok) hiçbir şey yapmadan `None`."""
    with session_factory() as session:
        claim = claim_upload(
            session, upload_id, token=new_claim_token(), lease_seconds=settings.worker_lease_seconds
        )
        session.commit()
    if claim is None:
        return None
    return run_claimed_upload(session_factory, layout, claim, settings=settings, provider=provider)


class Worker:
    """Kuyruğu tarayıp işleri sırayla işleyen arka plan işleyicisi (modül açıklaması)."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        layout: DataLayout,
        *,
        settings: Settings,
        provider: AnalysisProvider,
        engine: Engine | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._layout = layout
        self._settings = settings
        self._provider = provider
        self._engine = engine  # işleyicinin kendi motoru: durunca kapatılır
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> bool:
        """Tükenen işlerden vazgeçer, sıradaki işi alıp işler; iş aldıysa `True`."""
        settings = self._settings
        with self._session_factory() as session:
            for upload_id in abandon_exhausted(session, max_attempts=settings.worker_max_attempts):
                logger.error("Parti %s bırakıldı: işleyicisi defalarca yarıda kaldı", upload_id)
            claim = claim_next(
                session,
                token=new_claim_token(),
                lease_seconds=settings.worker_lease_seconds,
                max_attempts=settings.worker_max_attempts,
            )
            session.commit()
        if claim is None:
            return False
        run_claimed_upload(
            self._session_factory, self._layout, claim, settings=settings, provider=self._provider
        )
        return True

    def start(self) -> None:
        """Döngüyü arka plan iş parçacığında başlatır; çalışıyorsa bir şey yapmaz."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._loop, name="belgeee-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = STOP_TIMEOUT_SECONDS) -> None:
        """Döngüye durmasını söyler ve en çok `timeout` saniye bekler; süren iş kesilmez."""
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout)
        if self._engine is not None:
            self._engine.dispose()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                worked = self.run_once()
            except Exception as exc:
                logger.error("İşçi kuyruğu taranamadı (%s)", type(exc).__name__)
                worked = False
            if not worked:
                self._stopping.wait(self._settings.worker_poll_seconds)


def start_worker(settings: Settings, layout: DataLayout) -> Worker | None:
    """Panel sürecinin işleyicisini kurar ve başlatır; `WORKER_ENABLED` kapalıysa ya da yapay zekâ
    sağlayıcısı kurulamıyorsa (işler kuyrukta bekler) `None`."""
    if not settings.worker_enabled:
        return None
    try:
        provider = create_provider(settings)
    except ProviderConfigError as exc:
        logger.warning("İşçi kuyruğu başlatılmadı, partiler kuyrukta bekleyecek: %s", exc)
        return None
    engine = create_db_engine(settings.database_url)
    worker = Worker(
        create_session_factory(engine), layout, settings=settings, provider=provider, engine=engine
    )
    worker.start()
    return worker


class _Heartbeat:
    """İşleyen partinin kirasını kendi oturumunda düzenli yeniler (modül açıklaması)."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        claim: Claim,
        *,
        lease_seconds: int,
        interval: float,
    ) -> None:
        self._session_factory = session_factory
        self._claim = claim
        self._lease_seconds = lease_seconds
        self._interval = interval
        self._stopping = threading.Event()
        self._thread = threading.Thread(
            target=self._beat, name=f"belgeee-lease-{claim.upload_id}", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._thread.join()

    def _beat(self) -> None:
        while not self._stopping.wait(self._interval):
            try:
                with self._session_factory() as session:
                    renew_claim(session, self._claim, lease_seconds=self._lease_seconds)
                    session.commit()
            except LeaseLostError:
                return  # iş bitti ya da başka işleyiciye geçti; geçiş kancası da bunu görür
            except Exception as exc:
                logger.warning(
                    "Parti %s için iş kirası yenilenemedi (%s)",
                    self._claim.upload_id,
                    type(exc).__name__,
                )
