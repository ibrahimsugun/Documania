"""Aday tür akışı — liste, onay ve ret (PRD 11.5.1, 11.5.2, 11.5.4; K16, §20.6).

Analizcinin önerdiği katalog dışı türler `candidate_document_types`'ta birikir (04.6.1,
`record_candidate_type_sighting`). Bu modül onlar üzerindeki insan kararını yürütür:

- **Liste (11.5.1).** `list_candidate_types` bekleyen (`pending`) adayları görülme sayısına göre
  (çoktan aza; eşitlikte önce görülen önce) adı, görülme sayısı, örnek sayfaları ve sistemin
  incelemesinin durumuyla (11.5.5, `app.catalog.propose`: hazır, başarısız, örnek yok, bekliyor)
  verir. Örnek
  sayfalar `sample_page_ids` sırasıyladır (her görülmenin ilk sayfası): partisi, dosyası ve 0
  tabanlı sırası; görüntüsü analiz kopyasıdır (`pages.image_path`), belgenin kendisi değil. Karar
  verilmiş aday bekleyenler arasında listelenmez. Partinin yoksayılması (10.3.4) görülmeyi
  düşürmez: yoksayma partiyi yükleme listesinden ve kuyruklardan kaldırır, belgenin türü hakkında
  öğrenileni değil. O partilerin sayfaları görülme sayısında ve örneklerde kalır — aday tür kararı
  ve sonraki tür eğitimi bu birikime dayanır.
- **Onay (11.5.2).** `approve_candidate_type` İK'nın tamamladığı katalog kaydını (`CatalogEntry`,
  tür formunun doğrulamasından — 11.1.2 — geçmiş) `create_type` ile kataloğa ekler, adayı `approved`
  işaretler ve `TYPE_APPROVED`'ı kullanıcı adıyla yazar. Tür bir sonraki analizden itibaren analiz
  talimatındadır (katalog her analizde `export_catalog` ile baştan okunur). İki aşamalı onay
  (§20.6 "Yeni belge türünü onayla") çağıranın işidir — panel `app.web.confirm` ile yapar; bu modül
  `USER_CONFIRMED` yazmaz.
- **Ret (11.5.4).** `reject_candidate_type` adayı `rejected` işaretler ve `TYPE_REJECTED` yazar.
  Kayıt silinmez (K16). Aynı ad yeniden önerilirse görülme aynı kayda sayılır, durum değişmez
  (`record_candidate_type_sighting`): reddedilen aday listeye geri düşmez.

Karar yalnız bekleyen adayda verilir ve geri alınmaz (`decide_candidate_type`); aynı anda gelen iki
karardan biri geçer. Olay verisi kişisel değer taşımaz: aday kimliği, aday tür adı (analizcinin tür
adı) ve onayda türün slug'ı. Hiçbir fonksiyon commit etmez; hata olursa çağıran geri alır.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.form import TypeForm
from app.catalog.manage import create_type
from app.catalog.schema import CatalogEntry
from app.db.models import (
    CandidateDocumentType,
    CandidateProposalStatus,
    CandidateTypeStatus,
    Event,
    Page,
    UploadFile,
    decide_candidate_type,
)
from app.events import EventType, record_event
from app.storage import SlugError, slugify

LIST_SAMPLE_LIMIT = 3
DETAIL_SAMPLE_LIMIT = 24
PROPOSAL_PENDING_LABEL = "Bekliyor"
PROPOSAL_STATUS_LABELS = {
    CandidateProposalStatus.READY.value: "Hazır",
    CandidateProposalStatus.FAILED.value: "Başarısız",
    CandidateProposalStatus.NO_SAMPLES.value: "Örnek yok",
}
"""Aday incelemesinin (11.5.5) listede gösterilen durumu; incelenmemiş aday "Bekliyor"."""
_SLUG = re.compile(r"[a-z][a-z0-9_]*")
_SLUG_MAX_LENGTH = 64


class CandidateNotFoundError(LookupError):
    """Aday tür kaydı yok."""


class CandidateDecidedError(ValueError):
    """Aday tür karara bağlanmış (onaylanmış ya da reddedilmiş); yeniden karar verilmez."""

    def __init__(self, candidate_type_id: int, status: str) -> None:
        self.candidate_type_id = candidate_type_id
        self.status = status
        super().__init__(f"Aday tür {candidate_type_id} karara bağlanmış: {status}")


@dataclass(frozen=True, slots=True)
class CandidateSample:
    """Aday türün görüldüğü bir belgenin ilk sayfası; `page_index` 0 tabanlıdır."""

    page_id: int
    upload_id: str
    file_id: int
    file_name: str
    page_index: int
    has_image: bool


@dataclass(frozen=True, slots=True)
class CandidateSummary:
    """Aday türün listelenen hâli. `samples` örnek sayfaların ilk birkaçıdır (sınır çağıranın),
    `sample_total` kayıtlı örnek sayfa sayısıdır. `proposal_status` sistemin incelemesinin
    sonucudur (11.5.5, `CandidateProposalStatus`; `None` henüz incelenmedi)."""

    id: int
    name: str
    description: str | None
    seen_count: int
    status: str
    first_seen_upload_id: str
    samples: tuple[CandidateSample, ...]
    sample_total: int
    proposal_status: str | None = None

    @property
    def proposal_label(self) -> str:
        """İnceleme durumunun Türkçe adı: hazır, başarısız, örnek yok ya da bekliyor."""
        if self.proposal_status is None:
            return PROPOSAL_PENDING_LABEL
        return PROPOSAL_STATUS_LABELS.get(self.proposal_status, PROPOSAL_PENDING_LABEL)


def load_candidate_type(session: Session, candidate_type_id: int) -> CandidateDocumentType:
    """Aday tür kaydı; yoksa `CandidateNotFoundError`."""
    candidate = session.get(CandidateDocumentType, candidate_type_id)
    if candidate is None:
        raise CandidateNotFoundError(candidate_type_id)
    return candidate


def _samples(session: Session, page_ids: Iterable[int]) -> dict[int, CandidateSample]:
    ids = set(page_ids)
    if not ids:
        return {}
    rows = session.execute(
        select(Page, UploadFile)
        .join(UploadFile, Page.file_id == UploadFile.id)
        .where(Page.id.in_(ids))
    ).all()
    return {
        page.id: CandidateSample(
            page_id=page.id,
            upload_id=upload_file.upload_id,
            file_id=upload_file.id,
            file_name=upload_file.original_name,
            page_index=page.index,
            has_image=page.image_path is not None,
        )
        for page, upload_file in rows
    }


def summarize_candidates(
    session: Session, candidates: Sequence[CandidateDocumentType], *, sample_limit: int
) -> list[CandidateSummary]:
    """Adayların gösterimi; örnek sayfalar her aday için ilk `sample_limit` kayıttır. Silinmiş ya da
    bulunamayan sayfa örneklerden düşer (kayıtlı sayı `sample_total`'da kalır).

    Partinin yoksayılması (10.3.4) bir görülmeyi düşürmez: yoksayma partiyi çalışma yüzeylerinden
    (yükleme listesi, kuyruklar) kaldırır, belgenin türü hakkında öğrenileni değil. O sayfalar
    örneklerde ve sayılarda kalır; sonradan tür eğitimi için kullanılabilsinler."""
    shown = {
        candidate.id: list(candidate.sample_page_ids[:sample_limit]) for candidate in candidates
    }
    samples = _samples(session, (page_id for ids in shown.values() for page_id in ids))
    return [
        CandidateSummary(
            id=candidate.id,
            name=candidate.proposed_name,
            description=candidate.description,
            seen_count=candidate.seen_count,
            status=candidate.status,
            first_seen_upload_id=candidate.first_seen_upload_id,
            samples=tuple(
                samples[page_id] for page_id in shown[candidate.id] if page_id in samples
            ),
            sample_total=len(candidate.sample_page_ids),
            proposal_status=candidate.proposal_status,
        )
        for candidate in candidates
    ]


def list_candidate_types(
    session: Session,
    status: CandidateTypeStatus = CandidateTypeStatus.PENDING,
    *,
    sample_limit: int = LIST_SAMPLE_LIMIT,
) -> list[CandidateSummary]:
    """11.5.1 — `status` durumundaki adaylar, görülme sayısına göre (çoktan aza, eşitlikte önce
    görülen önce), örnek sayfalarıyla. Yoksayılan partideki (10.3.4) görülmeler de sayılır: yoksayma
    partiyi çalışma yüzeylerinden kaldırır, tür önerisini değil. Yalnız okur."""
    candidates = session.scalars(
        select(CandidateDocumentType)
        .where(CandidateDocumentType.status == status.value)
        .order_by(CandidateDocumentType.id)
    ).all()
    summaries = summarize_candidates(session, candidates, sample_limit=sample_limit)
    listed = [summary for summary in summaries if summary.seen_count > 0]
    return sorted(listed, key=lambda summary: (-summary.seen_count, summary.id))


def count_pending_candidate_types(session: Session) -> int:
    """Bekleyen aday sayısı; partisi yoksayılmış (10.3.4) görülmeler de sayılır."""
    candidates = session.scalars(
        select(CandidateDocumentType).where(
            CandidateDocumentType.status == CandidateTypeStatus.PENDING.value
        )
    ).all()
    summaries = summarize_candidates(session, candidates, sample_limit=0)
    return sum(1 for summary in summaries if summary.seen_count > 0)


def sample_page_refs(
    session: Session, candidate: CandidateDocumentType
) -> frozenset[tuple[int, int]]:
    """Adayın örnek sayfaları `(dosya kimliği, 0 tabanlı sayfa sırası)` olarak: aday türle ilişkili
    Unknown öğesi ilk kaynak sayfası bunlardan biri olan öğedir (11.5.3)."""
    if not candidate.sample_page_ids:
        return frozenset()
    rows = session.execute(
        select(Page.file_id, Page.index).where(Page.id.in_(candidate.sample_page_ids))
    ).all()
    return frozenset((file_id, index) for file_id, index in rows)


def suggested_form(candidate: CandidateDocumentType) -> TypeForm:
    """Onay formunun açılış değerleri (11.5.2): ad ve dosya etiketi önerilen addan, slug addan
    türetilir (katalog slug biçimine uymuyorsa boş), açıklama adayınkidir. Belgenin yapısı —
    dosya türleri, yüzler, Direkt Belge, zorunlu alanlar, dönüşümler — İK'nın kararıdır; formun
    varsayılanlarıyla açılır."""
    name = candidate.proposed_name
    try:
        slug = slugify(name, "_", max_length=_SLUG_MAX_LENGTH).lower()
    except SlugError:
        slug = ""
    return TypeForm(
        slug=slug if _SLUG.fullmatch(slug) else "",
        name=name,
        file_label=name,
        description=candidate.description or "",
    )


def _pending(session: Session, candidate_type_id: int) -> CandidateDocumentType:
    candidate = load_candidate_type(session, candidate_type_id)
    if candidate.status != CandidateTypeStatus.PENDING.value:
        raise CandidateDecidedError(candidate.id, candidate.status)
    return candidate


def _decide(
    session: Session, candidate: CandidateDocumentType, status: CandidateTypeStatus
) -> None:
    if not decide_candidate_type(session, candidate.id, status):
        # Aynı anda gelen öteki karar geçti.
        session.refresh(candidate)
        raise CandidateDecidedError(candidate.id, candidate.status)


def approve_candidate_type(
    session: Session, candidate_type_id: int, entry: CatalogEntry, *, actor: str
) -> CandidateDocumentType:
    """11.5.2 — bekleyen adayı `entry` kaydıyla kataloğa ekler ve `approved` işaretler.

    Aday yoksa `CandidateNotFoundError`, karara bağlanmışsa `CandidateDecidedError`, slug katalogda
    varsa `TypeExistsError` (`create_type`); üçünde de karar yazılmaz — oturumu çağıran geri alır.
    `TYPE_APPROVED` kullanıcı adıyla (`actor`) yazılır: veri aday kimliği, aday tür adı ve slug.
    """
    candidate = _pending(session, candidate_type_id)
    create_type(session, entry)
    _decide(session, candidate, CandidateTypeStatus.APPROVED)
    record_event(
        session,
        EventType.TYPE_APPROVED,
        actor=actor,
        data={
            "candidate_type_id": candidate.id,
            "candidate_type_name": candidate.proposed_name,
            "document_type_slug": entry.slug,
        },
    )
    session.refresh(candidate)
    return candidate


def reject_candidate_type(
    session: Session, candidate_type_id: int, *, actor: str
) -> CandidateDocumentType:
    """11.5.4 — bekleyen adayı `rejected` işaretler ve `TYPE_REJECTED`'ı kullanıcı adıyla yazar.

    Aday yoksa `CandidateNotFoundError`, karara bağlanmışsa `CandidateDecidedError`. Katalog
    değişmez; kayıt silinmez.
    """
    candidate = _pending(session, candidate_type_id)
    _decide(session, candidate, CandidateTypeStatus.REJECTED)
    record_event(
        session,
        EventType.TYPE_REJECTED,
        actor=actor,
        data={"candidate_type_id": candidate.id, "candidate_type_name": candidate.proposed_name},
    )
    session.refresh(candidate)
    return candidate


def approved_type_slug(session: Session, candidate_type_id: int) -> str | None:
    """Onaylanan adayın kataloğa eklendiği türün slug'ı (`TYPE_APPROVED` olayından); onay olayı
    yoksa `None`."""
    events = session.scalars(
        select(Event).where(Event.type == EventType.TYPE_APPROVED.value).order_by(Event.id.desc())
    )
    for event in events:
        data = event.data_json or {}
        slug = data.get("document_type_slug")
        if data.get("candidate_type_id") == candidate_type_id and isinstance(slug, str):
            return slug
    return None
