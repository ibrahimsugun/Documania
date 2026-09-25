"""11.5.1, 11.5.2, 11.5.4 — aday türlerin listesi, onayı ve reddi (`app.catalog.candidates`).

Aday tür kaydı 04.6.1'in `record_candidate_type_sighting`'iyle açılır; sayfalar sentetik satırlardır
(görüntü yolu yalnız saklanır, dosya okunmaz)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import app.catalog.candidates as candidates
from app.catalog import (
    CandidateDecidedError,
    CandidateNotFoundError,
    CatalogEntry,
    TypeExistsError,
    TypeForm,
    approve_candidate_type,
    approved_type_slug,
    build_entry,
    compile_catalog,
    count_pending_candidate_types,
    export_catalog,
    import_catalog,
    list_candidate_types,
    load_seed_catalog,
    reject_candidate_type,
    sample_page_refs,
    suggested_form,
)
from app.db.models import (
    CandidateDocumentType,
    CandidateTypeStatus,
    Event,
    KnownDocumentType,
    Page,
    Upload,
    UploadFile,
    record_candidate_type_sighting,
    utcnow,
)
from app.events import EventType

FIRST_UPLOAD = "u_20260919_0001"
SECOND_UPLOAD = "u_20260919_0002"
ACTOR = "ik-yonetici"
DIPLOMA = "Peruvian Diploma"


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


def _pages(
    session: Session, upload_id: str, name: str, count: int, *, images: bool = True
) -> list[Page]:
    if session.get(Upload, upload_id) is None:
        session.add(Upload(id=upload_id, channel="web"))
    upload_file = UploadFile(
        upload_id=upload_id,
        original_name=name,
        stored_path=f"inbox/{upload_id}/{name}",
        sha256="0" * 64,
        mime="application/pdf",
        page_count=count,
    )
    pages = [
        Page(
            file=upload_file,
            index=index,
            image_path=f"cache/{name}-{index}.png" if images else None,
        )
        for index in range(count)
    ]
    session.add_all([upload_file, *pages])
    session.flush()
    return pages


def _see(session: Session, name: str, page: Page, upload_id: str = FIRST_UPLOAD) -> int:
    return record_candidate_type_sighting(
        session, proposed_name=name, upload_id=upload_id, page_id=page.id
    ).candidate_type.id


def _entry(**overrides: Any) -> CatalogEntry:
    record: dict[str, Any] = {
        "slug": "peruvian_diploma",
        "name": DIPLOMA,
        "file_label": "Diploma",
        "country": "PE",
        "expected_file_types": ["pdf", "jpeg"],
        "expected_pages": {"min": 1, "max": 1},
        "sides": "single",
        "direct": False,
        "analyze": True,
        "required_fields": ["surname", "given_names", "document_number"],
        "allowed_conversions": ["wrap_image"],
        "output_format": "pdf",
        "prompt_description": "Peru'da verilmiş diploma; sağ üstte numara.",
    }
    record.update(overrides)
    return CatalogEntry.model_validate(record)


def _events(session: Session, event_type: EventType) -> list[Event]:
    return list(
        session.scalars(select(Event).where(Event.type == event_type.value).order_by(Event.id))
    )


# --- 11.5.1: liste --------------------------------------------------------------------------------


def test_pending_candidates_are_listed_by_seen_count_with_their_sample_pages(
    session: Session,
) -> None:
    first = _pages(session, FIRST_UPLOAD, "bir.pdf", 3)
    second = _pages(session, SECOND_UPLOAD, "iki.pdf", 1)
    permit = _see(session, "Chilean Permit", first[0])
    diploma = _see(session, DIPLOMA, first[2])
    _see(session, "PERUVIAN  diploma", second[0], SECOND_UPLOAD)

    listed = list_candidate_types(session)

    assert [(item.id, item.name, item.seen_count) for item in listed] == [
        (diploma, DIPLOMA, 2),
        (permit, "Chilean Permit", 1),
    ]
    top = listed[0]
    assert top.status == CandidateTypeStatus.PENDING.value
    assert top.first_seen_upload_id == FIRST_UPLOAD
    assert top.sample_total == 2
    assert [
        (sample.page_id, sample.upload_id, sample.file_name, sample.page_index, sample.has_image)
        for sample in top.samples
    ] == [
        (first[2].id, FIRST_UPLOAD, "bir.pdf", 2, True),
        (second[0].id, SECOND_UPLOAD, "iki.pdf", 0, True),
    ]
    assert top.samples[0].file_id == first[2].file_id


def test_equal_seen_counts_keep_the_first_seen_candidate_first(session: Session) -> None:
    (page,) = _pages(session, FIRST_UPLOAD, "bir.pdf", 1)
    earlier = _see(session, "Zambian Licence", page)
    later = _see(session, "Albanian Card", page)

    assert [item.id for item in list_candidate_types(session)] == [earlier, later]


def test_samples_are_limited_in_sighting_order_and_a_missing_page_is_skipped(
    session: Session,
) -> None:
    pages = _pages(session, FIRST_UPLOAD, "bir.pdf", 5, images=False)
    candidate_id = _see(session, DIPLOMA, pages[3])
    for page in (pages[1], pages[4], pages[0]):
        _see(session, DIPLOMA, page)
    candidate = session.get_one(CandidateDocumentType, candidate_id)
    candidate.sample_page_ids = [9999, *candidate.sample_page_ids]  # silinmiş/bozuk kayıt
    session.flush()

    (listed,) = list_candidate_types(session, sample_limit=3)

    assert [sample.page_index for sample in listed.samples] == [3, 1]
    assert not any(sample.has_image for sample in listed.samples)
    assert listed.sample_total == 5
    (none_shown,) = list_candidate_types(session, sample_limit=0)
    assert none_shown.samples == ()


def test_decided_candidates_are_not_listed_as_pending(session: Session) -> None:
    (page,) = _pages(session, FIRST_UPLOAD, "bir.pdf", 1)
    approved = _see(session, DIPLOMA, page)
    rejected = _see(session, "Chilean Permit", page)
    pending = _see(session, "Bolivian Card", page)
    approve_candidate_type(session, approved, _entry(), actor=ACTOR)
    reject_candidate_type(session, rejected, actor=ACTOR)

    assert [item.id for item in list_candidate_types(session)] == [pending]
    assert count_pending_candidate_types(session) == 1
    listed = list_candidate_types(session, CandidateTypeStatus.APPROVED)
    assert [item.id for item in listed] == [approved]
    listed = list_candidate_types(session, CandidateTypeStatus.REJECTED)
    assert [item.id for item in listed] == [rejected]


def test_sample_page_refs_are_file_and_page_positions(session: Session) -> None:
    pages = _pages(session, FIRST_UPLOAD, "bir.pdf", 3)
    candidate_id = _see(session, DIPLOMA, pages[0])
    _see(session, DIPLOMA, pages[2])
    candidate = session.get_one(CandidateDocumentType, candidate_id)

    file_id = pages[0].file_id
    assert sample_page_refs(session, candidate) == {(file_id, 0), (file_id, 2)}
    candidate.sample_page_ids = []
    assert sample_page_refs(session, candidate) == frozenset()


# --- 11.5.2: onay formunun açılışı ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        (DIPLOMA, "peruvian_diploma"),
        ("Carte d'identité  Française", "carte_didentite_francaise"),
        ("Удостоверение личности", "udostoverenie_lichnosti"),
        ("1099 Tax Form", ""),  # slug harfle başlamalı
        ("—", ""),  # slug'a çevrilemiyor
        ("A" + " very" * 20, "a" + "_very" * 12),  # 64 karaktere kelime sınırında
    ],
)
def test_the_approval_form_opens_with_the_candidate_name(
    session: Session, name: str, slug: str
) -> None:
    (page,) = _pages(session, FIRST_UPLOAD, "bir.pdf", 1)
    candidate = session.get_one(CandidateDocumentType, _see(session, name, page))
    candidate.description = "Modelin açıklaması"

    form = suggested_form(candidate)

    assert (form.slug, form.name, form.file_label, form.description) == (
        slug,
        " ".join(name.split()),
        " ".join(name.split()),
        "Modelin açıklaması",
    )
    assert len(form.slug) <= 64
    # Yapı İK'nın kararıdır: formun varsayılanlarıyla açılır.
    assert (form.required_fields, form.allowed_conversions, form.direct) == ("", (), False)
    assert form.expected_file_types == TypeForm().expected_file_types


def test_the_suggested_form_passes_validation_once_hr_completes_it(session: Session) -> None:
    (page,) = _pages(session, FIRST_UPLOAD, "bir.pdf", 1)
    candidate = session.get_one(CandidateDocumentType, _see(session, DIPLOMA, page))

    entry = build_entry(suggested_form(candidate))

    assert (entry.slug, entry.name, entry.file_label, entry.description) == (
        "peruvian_diploma",
        DIPLOMA,
        DIPLOMA,
        None,
    )


# --- 11.5.2: onay ---------------------------------------------------------------------------------


def test_approval_puts_the_type_in_the_catalog_and_logs_type_approved(session: Session) -> None:
    import_catalog(session, load_seed_catalog())
    (page,) = _pages(session, FIRST_UPLOAD, "bir.pdf", 1)
    candidate_id = _see(session, DIPLOMA, page)
    entry = _entry()

    approved = approve_candidate_type(session, candidate_id, entry, actor=ACTOR)
    session.commit()

    assert approved.status == CandidateTypeStatus.APPROVED.value
    catalog = export_catalog(session)
    assert catalog.get(entry.slug) == entry
    # Bir sonraki analizin talimatında (katalog her analizde baştan okunur).
    assert "peruvian_diploma" in compile_catalog(catalog).known_slugs
    (event,) = _events(session, EventType.TYPE_APPROVED)
    assert event.actor == ACTOR
    assert event.data_json == {
        "candidate_type_id": candidate_id,
        "candidate_type_name": DIPLOMA,
        "document_type_slug": "peruvian_diploma",
    }
    assert approved_type_slug(session, candidate_id) == "peruvian_diploma"


def test_approval_with_a_slug_already_in_the_catalog_decides_nothing(session: Session) -> None:
    import_catalog(session, load_seed_catalog())
    (page,) = _pages(session, FIRST_UPLOAD, "bir.pdf", 1)
    candidate_id = _see(session, DIPLOMA, page)
    session.commit()
    seed = session.get_one(KnownDocumentType, "russian_passport").name

    with pytest.raises(TypeExistsError):
        approve_candidate_type(session, candidate_id, _entry(slug="russian_passport"), actor=ACTOR)
    session.rollback()

    assert session.get_one(CandidateDocumentType, candidate_id).status == "pending"
    assert session.get_one(KnownDocumentType, "russian_passport").name == seed
    assert _events(session, EventType.TYPE_APPROVED) == []


@pytest.mark.parametrize("first", ["approve", "reject"])
@pytest.mark.parametrize("second", ["approve", "reject"])
def test_a_decided_candidate_is_not_decided_again(
    session: Session, first: str, second: str
) -> None:
    (page,) = _pages(session, FIRST_UPLOAD, "bir.pdf", 1)
    candidate_id = _see(session, DIPLOMA, page)

    def decide(action: str, slug: str) -> None:
        if action == "approve":
            approve_candidate_type(session, candidate_id, _entry(slug=slug), actor=ACTOR)
        else:
            reject_candidate_type(session, candidate_id, actor=ACTOR)

    decide(first, "peruvian_diploma")
    session.commit()
    with pytest.raises(CandidateDecidedError) as refused:
        decide(second, "peruvian_diploma_2")
    session.rollback()

    expected = "approved" if first == "approve" else "rejected"
    assert (refused.value.candidate_type_id, refused.value.status) == (candidate_id, expected)
    assert session.get(KnownDocumentType, "peruvian_diploma_2") is None
    decisions = _events(session, EventType.TYPE_APPROVED) + _events(
        session, EventType.TYPE_REJECTED
    )
    assert len(decisions) == 1


def test_a_missing_candidate_cannot_be_decided(session: Session) -> None:
    with pytest.raises(CandidateNotFoundError):
        approve_candidate_type(session, 404, _entry(), actor=ACTOR)
    with pytest.raises(CandidateNotFoundError):
        reject_candidate_type(session, 404, actor=ACTOR)


def test_a_decision_lost_to_a_concurrent_one_is_refused(
    monkeypatch: pytest.MonkeyPatch, session: Session
) -> None:
    (page,) = _pages(session, FIRST_UPLOAD, "bir.pdf", 1)
    candidate_id = _see(session, DIPLOMA, page)
    # Öteki işlem adayı `_pending` denetiminden sonra karara bağladı: koşullu güncelleme geçmez.
    monkeypatch.setattr(candidates, "decide_candidate_type", lambda *_: False)

    with pytest.raises(CandidateDecidedError):
        reject_candidate_type(session, candidate_id, actor=ACTOR)
    assert _events(session, EventType.TYPE_REJECTED) == []


# --- 11.5.4: ret ----------------------------------------------------------------------------------


def test_rejection_logs_type_rejected_and_leaves_the_catalog_alone(session: Session) -> None:
    import_catalog(session, load_seed_catalog())
    (page,) = _pages(session, FIRST_UPLOAD, "bir.pdf", 1)
    candidate_id = _see(session, DIPLOMA, page)
    before = [entry.slug for entry in export_catalog(session)]

    rejected = reject_candidate_type(session, candidate_id, actor=ACTOR)
    session.commit()

    assert rejected.status == CandidateTypeStatus.REJECTED.value
    assert [entry.slug for entry in export_catalog(session)] == before
    (event,) = _events(session, EventType.TYPE_REJECTED)
    assert event.actor == ACTOR
    assert event.data_json == {"candidate_type_id": candidate_id, "candidate_type_name": DIPLOMA}
    assert approved_type_slug(session, candidate_id) is None


def test_a_rejected_candidate_seen_again_does_not_return_to_the_list(session: Session) -> None:
    (first,) = _pages(session, FIRST_UPLOAD, "bir.pdf", 1)
    (second,) = _pages(session, SECOND_UPLOAD, "iki.pdf", 1)
    candidate_id = _see(session, DIPLOMA, first)
    reject_candidate_type(session, candidate_id, actor=ACTOR)
    session.commit()

    again = _see(session, "peruvian DIPLOMA", second, SECOND_UPLOAD)

    assert again == candidate_id
    assert list_candidate_types(session) == []
    assert count_pending_candidate_types(session) == 0
    stored = session.get_one(CandidateDocumentType, candidate_id)
    assert (stored.status, stored.seen_count) == ("rejected", 2)


def test_the_approved_slug_is_read_from_the_candidates_own_approval(session: Session) -> None:
    (page,) = _pages(session, FIRST_UPLOAD, "bir.pdf", 1)
    diploma = _see(session, DIPLOMA, page)
    permit = _see(session, "Chilean Permit", page)
    approve_candidate_type(session, diploma, _entry(), actor=ACTOR)
    approve_candidate_type(
        session, permit, _entry(slug="chilean_permit", name="Chilean Permit"), actor=ACTOR
    )
    session.add(Event(type=EventType.TYPE_APPROVED.value, data_json=None))  # bozuk kayıt
    session.flush()

    assert approved_type_slug(session, diploma) == "peruvian_diploma"
    assert approved_type_slug(session, permit) == "chilean_permit"
    assert approved_type_slug(session, 404) is None


# --- 10.3.4: yoksayma tür önerisini düşürmez -----------------------------------------------------
#
# Parti yoksayılınca çalışma yüzeylerinden (yükleme listesi, kuyruklar) kalkar, ama o belgelerden
# öğrenilen tür önerisi yerinde kalır: aday tür kararı ve sonraki tür eğitimi bu birikime dayanır.


def _dismiss(session: Session, upload_id: str) -> None:
    upload = session.get_one(Upload, upload_id)
    upload.dismissed_at = utcnow()
    upload.dismissed_by = ACTOR
    session.flush()


def test_sightings_in_a_dismissed_batch_stay_in_the_count_and_the_samples(
    session: Session,
) -> None:
    first = _pages(session, FIRST_UPLOAD, "bir.pdf", 2)
    second = _pages(session, SECOND_UPLOAD, "iki.pdf", 1)
    diploma = _see(session, DIPLOMA, first[0])
    _see(session, DIPLOMA, first[1])
    _see(session, DIPLOMA, second[0], SECOND_UPLOAD)
    permit = _see(session, "Chilean Permit", second[0], SECOND_UPLOAD)
    _see(session, "Chilean Permit", first[1])
    before = [
        (item.id, item.seen_count, item.sample_total) for item in list_candidate_types(session)
    ]
    assert before == [(diploma, 3, 3), (permit, 2, 2)]

    _dismiss(session, FIRST_UPLOAD)

    listed = list_candidate_types(session)
    assert [(item.id, item.seen_count, item.sample_total) for item in listed] == before
    # Yoksayılan partinin sayfaları örneklerde kalır.
    assert FIRST_UPLOAD in {sample.upload_id for item in listed for sample in item.samples}
    stored = session.get_one(CandidateDocumentType, diploma)
    assert stored.seen_count == 3 and len(stored.sample_page_ids) == 3
    assert count_pending_candidate_types(session) == 2


def test_a_candidate_seen_only_in_dismissed_batches_is_still_pending(
    session: Session,
) -> None:
    (page,) = _pages(session, FIRST_UPLOAD, "bir.pdf", 1)
    (other,) = _pages(session, SECOND_UPLOAD, "iki.pdf", 1)
    kept = _see(session, DIPLOMA, page)
    other_kept = _see(session, "Chilean Permit", other, SECOND_UPLOAD)

    _dismiss(session, FIRST_UPLOAD)

    assert sorted(item.id for item in list_candidate_types(session)) == sorted([kept, other_kept])
    assert count_pending_candidate_types(session) == 2
    (summary,) = candidates.summarize_candidates(
        session, [session.get_one(CandidateDocumentType, kept)], sample_limit=3
    )
    assert (summary.seen_count, summary.sample_total) == (1, 1)
    assert [sample.upload_id for sample in summary.samples] == [FIRST_UPLOAD]
