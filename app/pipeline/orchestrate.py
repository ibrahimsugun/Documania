"""Planı yeniden çalıştırma ve partiyi yeniden analiz — PRD 06.6.1, 06.6.2 (K9, K18, S18).

**Güncel plan.** Partinin güncel planı en yüksek sürümlü `plans` kaydıdır; eski sürümler
değiştirilmez ve silinmez.

**Yeniden çalıştırma (06.6.1).** Güncel plan `read_plan` ile okunur ve olduğu gibi uygulayıcıya
verilir (K9). Yapay zekâ çağrılmaz: bu yol sağlayıcı almaz; sayfa analizine, gruplamaya ve çalışan
eşleştirmeye dokunmaz. Plan yeniden üretilmez ve yeni sürüm açılmaz — planlamanın yan etkileri
(çalışan açma, profil önerisi, kimlik birikimi, aday tür görülmesi) tekrar yürümez. Uygulayıcı
ilk uygulamadaki `plans` kaydını (aynı kimlik, aynı `plan_hash`) aldığı için plan öğesi başına
idempotent uygulayıcı (07.8.1) ikinci kopya üretmez; yeniden planlama aynı içerikte bile yeni
sürüm ve yeni hash doğurur ve öğeleri uygulanmamış görünür, bu yüzden yeniden çalıştırmanın
yerini tutmaz. Dondurulduktan sonra değişmiş ya da sözleşmeye uymayan plan yürütülmez
(`PlanIntegrityError`); planı olmayan parti yeniden çalıştırılmaz (`NoPlanError`).

**Yeniden analiz (06.6.2).** Planı olan partinin sayfaları sağlayıcıya yeniden gönderilir (03.7),
yeni analizlerden bir sonraki plan sürümü üretilir (06.1, K18), önceki sürümlerin etkin çıktıları
(`documents.status = active`) "eski sürüm" (`superseded`) işaretlenir ve yeni plan uygulanır.
Eski çıktı silinmez, taşınmaz, yeniden adlandırılmaz: satırı ve dosyası yerinde kalır, temizlik
İK'nın arşive taşımasıdır. Başka partinin ve plana bağlı olmayan çıktıya dokunulmaz. Planı
olmayan partiyi baştan işlemek orkestrasyonun (09.2) işidir; yeniden analiz sağlayıcıyı çağırmadan
reddeder. Eski sürümün kuyruk kaydı `queue_items.plan_id` ile ayrılır (güncel plana ait değil).

**Uygulayıcı.** `PlanExecutor` planı uygulayan adımdır — çıktılar (07.x), kuyruk kayıtları (08.1);
09.2 bunları tek adımda birleştirir. Sözleşmesi: doğrulanmış planı ve kaydını alır, yapay zekâ
çağırmaz, planı değiştirmez, plan öğesi başına idempotenttir (07.8.1) ve oturumu commit etmez.
Uygulama bitince `plans.executed_at` son uygulamanın zamanı olur.

**Olay.** `PLAN_RERUN` doğrulamadan sonra, uygulayıcıdan önce yazılır: veri `plan_id`, `version`,
`plan_hash`. `PLAN_REANALYZED` yeni plan (`PLAN_CREATED`) ve eski sürüm işaretlemesinden sonra,
uygulayıcıdan önce yazılır: veri yeni ve önceki planın kimliği ile sürümü, `plan_hash`, `model`,
sayfa sonuç sayıları ve eski sürüm işaretlenen çıktıların kimlikleri. Mesaj yok, kişisel değer
yok. Uygulayıcının olayları partinin bağlamında yazılır.

Parti durumuna dokunulmaz (09.2.1); yalnız analiz kısmi başarıda `partial` yazar (03.7.2). Oturum
commit edilmez — işlem sınırı çağıranındır; hata olursa hiçbir iz kalmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompts import build_page_analysis_instructions
from app.ai.provider import AnalysisProvider
from app.catalog import Catalog
from app.db.models import Document, DocumentStatus, Plan, Upload, utcnow
from app.events import EventType, event_context, record_event
from app.pipeline.analyze import UploadAnalysisResult, analyze_upload
from app.pipeline.plan import PlanDocument, create_plan, read_plan
from app.storage import DataLayout


class PlanExecutor(Protocol):
    """Doğrulanmış planı uygulayan adım; sözleşmesi modül açıklamasında."""

    def __call__(
        self, session: Session, layout: DataLayout, plan: Plan, document: PlanDocument
    ) -> None: ...


class NoPlanError(LookupError):
    """Partinin planı yok: yeniden çalıştırılacak ya da yeniden analiz edilecek sürüm bulunmadı."""


@dataclass(frozen=True, slots=True)
class PlanRun:
    """Yeniden çalıştırmanın sonucu: uygulanan kayıt ve doğrulanmış planı."""

    plan: Plan
    document: PlanDocument


@dataclass(frozen=True, slots=True)
class Reanalysis:
    """Yeniden analizin sonucu.

    `plan` açılan yeni sürümdür, `previous_plan` yeniden analizden önceki güncel plan.
    `superseded_document_ids` bu yeniden analizde "eski sürüm" işaretlenen çıktılardır.
    """

    plan: Plan
    document: PlanDocument
    previous_plan: Plan
    superseded_document_ids: tuple[int, ...]
    analysis: UploadAnalysisResult


def current_plan(session: Session, upload: Upload) -> Plan | None:
    """Partinin en yüksek sürümlü planı; plan yoksa `None`."""
    session.flush()
    return session.scalars(
        select(Plan).where(Plan.upload_id == upload.id).order_by(Plan.version.desc()).limit(1)
    ).first()


def rerun_plan(
    session: Session, layout: DataLayout, upload: Upload, *, executor: PlanExecutor
) -> PlanRun:
    """Partinin güncel planını yapay zekâya ve planlamaya sormadan yeniden uygular (06.6.1).

    Plan yoksa `NoPlanError`, saklanan plan doğrulanmazsa `PlanIntegrityError`; iki durumda da
    olay yazılmaz ve uygulayıcı çağrılmaz. Oturum commit edilmez.
    """
    plan = _require_current_plan(session, upload)
    document = read_plan(plan)
    with event_context(upload_id=upload.id):
        record_event(
            session,
            EventType.PLAN_RERUN,
            data={"plan_id": plan.id, "version": plan.version, "plan_hash": plan.plan_hash},
        )
        _execute(session, layout, plan, document, executor=executor)
    return PlanRun(plan, document)


def reanalyze_upload(
    session: Session,
    layout: DataLayout,
    upload: Upload,
    *,
    provider: AnalysisProvider,
    catalog: Catalog,
    executor: PlanExecutor,
    reference_date: date | None = None,
) -> Reanalysis:
    """Planı olan partiyi yeniden analiz eder, yeni plan sürümünü açar ve uygular (06.6.2).

    `catalog` hem analiz talimatının hem planın kataloğudur (`export_catalog(session)`); plan
    modeli `provider.model`'dır. `reference_date` `create_plan`'e aynen geçer. Plan yoksa
    sağlayıcı çağrılmadan `NoPlanError`. Oturum commit edilmez.
    """
    previous = _require_current_plan(session, upload)
    analysis = analyze_upload(
        session,
        layout,
        upload,
        provider=provider,
        instructions=build_page_analysis_instructions(catalog),
    )
    plan = create_plan(
        session,
        layout,
        upload,
        catalog=catalog,
        model=provider.model,
        reference_date=reference_date,
    )
    document = read_plan(plan)
    superseded = _supersede_older_outputs(session, plan)
    with event_context(upload_id=upload.id):
        record_event(
            session,
            EventType.PLAN_REANALYZED,
            data={
                "plan_id": plan.id,
                "version": plan.version,
                "plan_hash": plan.plan_hash,
                "model": plan.model,
                "previous_plan_id": previous.id,
                "previous_version": previous.version,
                "pages": {
                    "analyzed": len(analysis.analyzed),
                    "failed": len(analysis.failed),
                    "skipped": len(analysis.skipped),
                },
                "superseded_document_ids": list(superseded),
            },
        )
        _execute(session, layout, plan, document, executor=executor)
    return Reanalysis(plan, document, previous, superseded, analysis)


def _require_current_plan(session: Session, upload: Upload) -> Plan:
    plan = current_plan(session, upload)
    if plan is None:
        raise NoPlanError(f"Partinin planı yok (parti {upload.id}); önce parti işlenmeli.")
    return plan


def _execute(
    session: Session,
    layout: DataLayout,
    plan: Plan,
    document: PlanDocument,
    *,
    executor: PlanExecutor,
) -> None:
    executor(session, layout, plan, document)
    plan.executed_at = utcnow()
    session.flush()


def _supersede_older_outputs(session: Session, plan: Plan) -> tuple[int, ...]:
    # K18: partinin önceki sürümlerinin etkin çıktıları yerinde kalır, yalnız durumu değişir.
    older = select(Plan.id).where(Plan.upload_id == plan.upload_id, Plan.version < plan.version)
    documents = session.scalars(
        select(Document)
        .where(Document.plan_id.in_(older), Document.status == DocumentStatus.ACTIVE.value)
        .order_by(Document.id)
    ).all()
    for output in documents:
        output.status = DocumentStatus.SUPERSEDED.value
    session.flush()
    return tuple(output.id for output in documents)
