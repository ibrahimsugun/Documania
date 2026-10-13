"""Bekleyen işte yol gösterme (PRD 10.11.2; PLAN.md §D120 d).

Kullanıcının karar vermesi gereken bekleyen kuyruk öğesi, kararın verileceği yere bağlantı ve tek
cümlelik "ne yapmalı" ipucu taşır. Metinler `app.web.feedback.HINTS` kaydındandır (msgid; şablon
`translate` ile isteğin dilinde gösterir, 10.11.3). Bu modül yalnız hangi ipucunun ve hangi adımın
gösterileceğini seçer; yazma yetkisine göre süzme (10.1.8) şablonun işidir: salt okunur Kullanıcı
yazma adımlarını görmez, "İK'ya bildirin" ipucunu görür.

**Aday türle bağ.** Unknown öğesi ile aday tür arasında modelde doğrudan bağ yoktur. Bağ 11.5.3'ün
ilişkisidir: öğenin ilk kaynak sayfası adayın örnek sayfalarından biridir (`sample_page_ids`;
aday türün sayfası ve toplu yeniden analiz de bu tanımı kullanır, `app.web.routers.catalog`). Bir
sayfa birden çok adayın örneği olabilir (yeniden analiz başka ad önerdiyse); öğe önce bekleyen,
sonra onaylanmış adaya, eşitlikte en yeni adaya bağlanır. Reddedilen aday bağlantı almaz.

**Davranış (koddan doğrulandı).** Aday tür onayı ve reddi bağlı bekleyen öğeyi çözmez
(`app.catalog.candidates`): onaydan sonra öğe, aday türün sayfasındaki toplu yeniden analizle
(11.5.3) ya da partinin yeniden analiziyle yeni plana göre yerleşir; retten sonra öğe Unknown
kuyruğunda kalır ve elle kapatılır. Unknown öğesi türsüz olduğu için çalışana atanamaz (K8).

Hiçbir ipucu belge içeriğini değiştiren bir yol önermez (R12, K17): adımlar onay, atama, profil
onayı, kapatma, yeniden analiz ve yeniden yüklemedir.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CandidateDocumentType, CandidateTypeStatus, Page, QueueItem, QueueKind
from app.matching.match import EmployeeAction
from app.pipeline.plan_models import PlanEmployee
from app.web.feedback import (
    HINTS,
    RESOLVE_UNKNOWN,
    RESOLVE_UNKNOWN_APPROVED,
    RESOLVE_UNKNOWN_CANDIDATE,
    RESOLVE_UNREADABLE,
    RESOLVE_UNRESOLVED,
    RESOLVE_UNRESOLVED_PROFILE,
    RESOLVE_UNRESOLVED_TYPELESS,
    STEP_ASSIGN,
    STEP_CANDIDATE_APPROVE,
    STEP_CANDIDATE_APPROVED,
    STEP_CANDIDATE_REANALYZE,
    STEP_CLOSE,
    STEP_PROFILE,
    STEP_REUPLOAD,
    STEP_SOURCES,
    STEP_TYPE_ADD,
    STEP_UPLOAD_REANALYZE,
    TAB_UNKNOWN,
    TAB_UNKNOWN_READER,
    TAB_UNREADABLE,
    TAB_UNREADABLE_READER,
    TAB_UNRESOLVED,
    TAB_UNRESOLVED_READER,
)

CANDIDATES_PATH = "/document-types/candidate-types"
NEW_TYPE_PATH = "/document-types/new"
UPLOAD_PATH = "/upload"

# Adayın bağ önceliği: bekleyen > onaylanmış; reddedilen bağlantı almaz.
_LINKED = {CandidateTypeStatus.PENDING.value: 2, CandidateTypeStatus.APPROVED.value: 1}

# Kuyruklar listesinde sekmenin başındaki tek cümle: (yazabilen, salt okunur).
TAB_HINTS: dict[str, tuple[str, str]] = {
    QueueKind.UNKNOWN.value: (HINTS[TAB_UNKNOWN], HINTS[TAB_UNKNOWN_READER]),
    QueueKind.UNREADABLE.value: (HINTS[TAB_UNREADABLE], HINTS[TAB_UNREADABLE_READER]),
    QueueKind.UNRESOLVED.value: (HINTS[TAB_UNRESOLVED], HINTS[TAB_UNRESOLVED_READER]),
}


@dataclass(frozen=True, slots=True)
class Step:
    """Kuyruk öğesi sayfasındaki önerilen adım: ipucu (msgid) ve kararın verileceği yer (sayfadaki
    bölümün çapası ya da başka sayfa)."""

    text: str
    url: str


def first_page(payload: Any) -> tuple[int, int] | None:
    """Kuyruk kaydının ilk kaynak sayfası `(dosya kimliği, 0 tabanlı sıra)`; kayıt bozuk ya da
    sayfasızsa `None` (öğe hiçbir adayla ilişkilendirilmez)."""
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list) or not sources or not isinstance(sources[0], dict):
        return None
    file_id, pages = sources[0].get("file_id"), sources[0].get("pages", [])
    if isinstance(file_id, bool) or not isinstance(file_id, int):
        return None
    if not isinstance(pages, list) or not pages:
        return None
    if not all(isinstance(page, int) and not isinstance(page, bool) for page in pages):
        return None
    return file_id, pages[0]


def candidates_of(session: Session, items: Iterable[QueueItem]) -> dict[int, CandidateDocumentType]:
    """Unknown öğelerinin bağlı olduğu aday tür (öğe kimliği → aday); bağı olmayan öğe yoktur.
    Yalnız okur."""
    firsts = {
        item.id: page
        for item in items
        if item.kind == QueueKind.UNKNOWN.value and (page := first_page(item.payload_json))
    }
    if not firsts:
        return {}
    file_ids = {file_id for file_id, _ in firsts.values()}
    page_ids = {
        (file_id, index): page_id
        for page_id, file_id, index in session.execute(
            select(Page.id, Page.file_id, Page.index).where(Page.file_id.in_(file_ids))
        )
    }
    wanted = {page_ids[page] for page in firsts.values() if page in page_ids}
    by_page: dict[int, CandidateDocumentType] = {}
    for candidate in session.scalars(select(CandidateDocumentType)):
        rank = _LINKED.get(candidate.status)
        if rank is None:
            continue
        for page_id in wanted.intersection(candidate.sample_page_ids):
            held = by_page.get(page_id)
            if held is None or (rank, candidate.id) > (_LINKED[held.status], held.id):
                by_page[page_id] = candidate
    return {
        item_id: by_page[page_ids[page]]
        for item_id, page in firsts.items()
        if page in page_ids and page_ids[page] in by_page
    }


def candidate_url(candidate: CandidateDocumentType | None) -> str | None:
    return None if candidate is None else f"{CANDIDATES_PATH}/{candidate.id}"


def _type_slug(payload: Any) -> str | None:
    slug = payload.get("document_type_slug") if isinstance(payload, dict) else None
    return slug if isinstance(slug, str) else None


def _proposes_profile(payload: Any) -> bool:
    raw = payload.get("employee_guess") if isinstance(payload, dict) else None
    try:
        guess = PlanEmployee.model_validate(raw)
    except ValidationError:
        return False
    return guess.action is EmployeeAction.PENDING


def resolution_hint(item: QueueItem, candidate: CandidateDocumentType | None) -> str:
    """Bekleyen öğenin "Çözüm" sütunundaki yapılacak iş (msgid), kuyruk türüne göre (§D120 d)."""
    if item.kind == QueueKind.UNKNOWN.value:
        if candidate is None:
            return HINTS[RESOLVE_UNKNOWN]
        if candidate.status == CandidateTypeStatus.APPROVED.value:
            return HINTS[RESOLVE_UNKNOWN_APPROVED]
        return HINTS[RESOLVE_UNKNOWN_CANDIDATE]
    if _type_slug(item.payload_json) is None:
        return HINTS[RESOLVE_UNRESOLVED_TYPELESS]
    if item.kind == QueueKind.UNREADABLE.value:
        return HINTS[RESOLVE_UNREADABLE]
    if _proposes_profile(item.payload_json):
        return HINTS[RESOLVE_UNRESOLVED_PROFILE]
    return HINTS[RESOLVE_UNRESOLVED]


def item_steps(
    item: QueueItem,
    candidate: CandidateDocumentType | None,
    *,
    can_profile: bool,
    can_assign: bool,
    can_close: bool,
) -> list[Step]:
    """Bekleyen öğenin önerilen adımları, sırayla; çapalar öğe sayfasının bölümleridir
    (`#new-profile`, `#assign`, `#close`, `#sources`)."""
    steps: list[Step] = []
    if item.kind == QueueKind.UNKNOWN.value:
        url = candidate_url(candidate)
        if candidate is not None and url is not None:
            if candidate.status == CandidateTypeStatus.APPROVED.value:
                steps.append(Step(HINTS[STEP_CANDIDATE_APPROVED], url))
            else:
                steps.append(Step(HINTS[STEP_CANDIDATE_APPROVE], url))
                steps.append(Step(HINTS[STEP_CANDIDATE_REANALYZE], url))
        else:
            steps.append(Step(HINTS[STEP_TYPE_ADD], NEW_TYPE_PATH))
            steps.append(Step(HINTS[STEP_UPLOAD_REANALYZE], f"/uploads/{item.upload_id}#actions"))
    elif item.kind == QueueKind.UNREADABLE.value:
        steps.append(Step(HINTS[STEP_SOURCES], "#sources"))
        if can_assign:
            steps.append(Step(HINTS[STEP_ASSIGN], "#assign"))
        steps.append(Step(HINTS[STEP_REUPLOAD], UPLOAD_PATH))
    else:
        if can_profile:
            steps.append(Step(HINTS[STEP_PROFILE], "#new-profile"))
        if can_assign:
            steps.append(Step(HINTS[STEP_ASSIGN], "#assign"))
        if not (can_profile or can_assign):
            steps.append(Step(HINTS[STEP_REUPLOAD], UPLOAD_PATH))
    if can_close:
        steps.append(Step(HINTS[STEP_CLOSE], "#close"))
    return steps
