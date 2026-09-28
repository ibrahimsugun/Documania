"""14.2.1–14.2.3, 14.3.1 — çalışanın belge paketleri: tanımlama, karşılanma hesabı, tamamlanma ve
açığa dönme, iptal ve yeniden açma, yenileme noktaları (PLAN.md §C89).

Veriler sentetiktir: çalışanlar, katalog türleri (`tests/groups/conftest.py`) ve çıktı satırları
elle yazılır; taşıma ve arşivleme testlerinde dosyalar geçici veri dizinindedir. Gerçek kimlik
belgesi ve yapay zekâ çağrısı yoktur.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeePackage,
    Event,
    PackageStatus,
    Upload,
    UploadFile,
)
from app.events import EventType
from app.groups import (
    NOTE_MAX_LENGTH,
    GroupArchivedError,
    GroupNotFoundError,
    PackageEmployeeNotFoundError,
    PackageFormError,
    PackageNotFoundError,
    PackageStateError,
    add_item,
    assign_package,
    cancel_package,
    create_group,
    employee_packages,
    employees_with_missing_packages,
    evaluate_package,
    open_package_counts,
    package_counts,
    refresh_employee_packages,
    remove_item,
    reopen_package,
    set_group_archived,
)
from app.storage import DataLayout, archive_document, move_document, prepare_data_dir

ACTOR = "ik-ayse"
OWNER, OWNER_FOLDER = "E0001", "Ivan_Petrov_E0001"
OTHER, OTHER_FOLDER = "E0002", "Ana_Prueba_E0002"
PACKAGE_EVENTS = (
    EventType.PACKAGE_ASSIGNED,
    EventType.PACKAGE_COMPLETED,
    EventType.PACKAGE_REOPENED,
    EventType.PACKAGE_CANCELLED,
)
BASE_TIME = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


@pytest.fixture
def employees(session: Session) -> None:
    session.add(Employee(id=OWNER, folder_name=OWNER_FOLDER, given_names="Ivan", surname="Petrov"))
    session.add(Employee(id=OTHER, folder_name=OTHER_FOLDER, given_names="Ana", surname="Prueba"))
    session.commit()


def _document(
    session: Session,
    slug: str,
    *,
    owner: str = OWNER,
    status: DocumentStatus = DocumentStatus.ACTIVE,
    minutes: int = 0,
    name: str | None = None,
) -> Document:
    folder = OWNER_FOLDER if owner == OWNER else OTHER_FOLDER
    document = Document(
        employee_id=owner,
        type_slug=slug,
        path=f"Employees/{folder}/Hazir/{name or slug}.pdf",
        format="pdf",
        source_refs_json=[],
        status=status.value,
        created_at=BASE_TIME + timedelta(minutes=minutes),
    )
    session.add(document)
    session.flush()
    return document


def _serbia_group(session: Session, *, optional_id_card: bool = True) -> int:
    """Sırbistan iş başvurusu: Passport etiketi, Profile Picture etiketi, oturma kartı türü
    (zorunlu) ve isteğe bağlı kimlik kartı etiketi."""
    group = create_group(session, name="Sırbistan iş başvurusu", description=None, actor=ACTOR)
    add_item(session, group.id, match_kind="label", file_label="Passport", actor=ACTOR)
    add_item(session, group.id, match_kind="label", file_label="Profile Picture", actor=ACTOR)
    add_item(session, group.id, match_kind="type", type_slug="residence_card", actor=ACTOR)
    if optional_id_card:
        add_item(
            session,
            group.id,
            match_kind="label",
            file_label="Identity Card",
            required=False,
            actor=ACTOR,
        )
    session.commit()
    return group.id


def _assign(session: Session, group_id: int, **kwargs: Any) -> EmployeePackage:
    result = assign_package(
        session, kwargs.pop("employee_id", OWNER), group_id, actor=ACTOR, **kwargs
    )
    assert result.package is not None and not result.warn
    session.commit()
    return result.package


def _package_events(session: Session) -> list[tuple[str, str, str | None, dict[str, Any]]]:
    rows = session.scalars(
        select(Event)
        .where(Event.type.in_([kind.value for kind in PACKAGE_EVENTS]))
        .order_by(Event.id)
    )
    return [(row.type, row.actor, row.employee_id, row.data_json or {}) for row in rows]


def _ticks(session: Session, package: EmployeePackage) -> list[tuple[str, bool, int | None]]:
    view = evaluate_package(session, package)
    return [
        (item.title, item.required, item.document.id if item.document else None)
        for item in view.items
    ]


# --- 14.2.1: tanımlama ---------------------------------------------------------------------------


@pytest.mark.usefixtures("employees")
def test_assigning_a_group_opens_a_package_with_the_requester_and_an_event(
    session: Session,
) -> None:
    group_id = _serbia_group(session)

    package = _assign(session, group_id, note="  Belgrad   ofisi  ")

    assert (package.employee_id, package.group_id, package.status) == (
        OWNER,
        group_id,
        PackageStatus.OPEN.value,
    )
    assert package.requested_by == ACTOR and package.requested_at.tzinfo is UTC
    assert package.note == "Belgrad ofisi"
    assert (package.completed_at, package.cancelled_at, package.cancel_note) == (None, None, None)
    assert _package_events(session) == [
        (
            "PACKAGE_ASSIGNED",
            ACTOR,
            OWNER,
            {"package_id": package.id, "group_id": group_id, "duplicate": False},
        )
    ]


@pytest.mark.usefixtures("employees")
def test_an_archived_group_cannot_become_a_package(session: Session) -> None:
    group_id = _serbia_group(session)
    set_group_archived(session, group_id, True, actor=ACTOR)
    session.commit()

    with pytest.raises(GroupArchivedError):
        assign_package(session, OWNER, group_id, actor=ACTOR)

    session.rollback()
    assert session.scalar(select(func.count()).select_from(EmployeePackage)) == 0
    assert _package_events(session) == []


@pytest.mark.usefixtures("employees")
def test_unknown_employee_group_or_blank_actor_is_refused(session: Session) -> None:
    group_id = _serbia_group(session)

    with pytest.raises(PackageEmployeeNotFoundError):
        assign_package(session, "E9999", group_id, actor=ACTOR)
    with pytest.raises(GroupNotFoundError):
        assign_package(session, OWNER, 999, actor=ACTOR)
    with pytest.raises(ValueError, match="actor"):
        assign_package(session, OWNER, group_id, actor="  ")


@pytest.mark.usefixtures("employees")
def test_a_note_longer_than_the_limit_is_refused(session: Session) -> None:
    group_id = _serbia_group(session)

    with pytest.raises(PackageFormError) as refused:
        assign_package(session, OWNER, group_id, actor=ACTOR, note="x" * (NOTE_MAX_LENGTH + 1))

    assert list(refused.value.problems) == ["note"]
    assert session.scalar(select(func.count()).select_from(EmployeePackage)) == 0


@pytest.mark.usefixtures("employees")
def test_a_second_package_of_the_same_group_needs_a_confirmation(session: Session) -> None:
    group_id = _serbia_group(session)
    first = _assign(session, group_id)

    warned = assign_package(session, OWNER, group_id, actor=ACTOR)
    assert (warned.package, warned.warn) == (None, True)
    assert session.scalar(select(func.count()).select_from(EmployeePackage)) == 1

    second = assign_package(session, OWNER, group_id, actor=ACTOR, confirm_duplicate=True)
    session.commit()
    assert second.package is not None and second.package.id != first.id
    assert _package_events(session)[-1][3] == {
        "package_id": second.package.id,
        "group_id": group_id,
        "duplicate": True,
    }
    # Başka çalışan ve başka grup uyarı almaz; aynı çalışana birden çok paket tanımlanabilir.
    assert not assign_package(session, OTHER, group_id, actor=ACTOR).warn
    other_group = create_group(session, name="Almanya vizesi", description=None, actor=ACTOR)
    assert not assign_package(session, OWNER, other_group.id, actor=ACTOR).warn


@pytest.mark.usefixtures("employees")
def test_a_cancelled_package_of_the_same_group_does_not_warn(session: Session) -> None:
    group_id = _serbia_group(session)
    package = _assign(session, group_id)
    cancel_package(session, OWNER, package.id, actor=ACTOR, note="Başvuru ertelendi")
    session.commit()

    assert not assign_package(session, OWNER, group_id, actor=ACTOR).warn


# --- 14.2.2: karşılanma hesabı -------------------------------------------------------------------


@pytest.mark.usefixtures("employees")
def test_a_label_item_is_met_by_any_country_and_a_type_item_only_by_its_type(
    session: Session,
) -> None:
    group_id = _serbia_group(session)
    package = _assign(session, group_id)
    russian = _document(session, "russian_passport")
    # Oturma kartı etiketini taşıyan başka tür yok; kimlik kartı etiketi Kosova belgesini almaz.
    kosovo = _document(session, "kosovo_id_document")

    assert _ticks(session, package) == [
        ("Passport", True, russian.id),
        ("Profile Picture", True, None),
        ("Serbian Residence Card", True, None),
        ("Identity Card", False, None),
    ]
    assert kosovo.id not in [document_id for _, _, document_id in _ticks(session, package)]


@pytest.mark.usefixtures("employees")
def test_only_active_documents_of_the_employee_meet_an_item_and_the_newest_wins(
    session: Session,
) -> None:
    group_id = _serbia_group(session)
    package = _assign(session, group_id)
    _document(session, "russian_passport", status=DocumentStatus.ARCHIVED, minutes=5)
    _document(session, "turkish_passport", status=DocumentStatus.SUPERSEDED, minutes=6)
    _document(session, "residence_card", owner=OTHER)
    older = _document(session, "russian_passport", minutes=1)
    newer = _document(session, "turkish_passport", minutes=2)
    # Pasif türün (Sırp pasaportu) etkin belgesi de etiketle karşılar; en yeni o değil.
    _document(session, "serbian_passport", minutes=0)

    ticks = _ticks(session, package)
    assert ticks[0] == ("Passport", True, newer.id)
    assert ticks[2] == ("Serbian Residence Card", True, None)
    assert older.id != newer.id


@pytest.mark.usefixtures("employees")
def test_the_same_document_can_meet_items_of_several_packages(session: Session) -> None:
    group_id = _serbia_group(session)
    other = create_group(session, name="Almanya vizesi", description=None, actor=ACTOR)
    add_item(session, other.id, match_kind="type", type_slug="russian_passport", actor=ACTOR)
    first, second = _assign(session, group_id), _assign(session, other.id)
    passport = _document(session, "russian_passport")

    assert _ticks(session, first)[0][2] == passport.id
    assert _ticks(session, second) == [("Russian Passport", True, passport.id)]


@pytest.mark.usefixtures("employees")
def test_a_removed_item_leaves_the_package_and_optional_items_do_not_block_it(
    session: Session,
) -> None:
    group_id = _serbia_group(session)
    package = _assign(session, group_id)
    _document(session, "russian_passport")
    _document(session, "profile_picture")
    view = evaluate_package(session, package)
    (residence_item,) = [item for item in view.items if item.title == "Serbian Residence Card"]

    remove_item(session, group_id, residence_item.item_id, actor=ACTOR)
    session.commit()

    view = evaluate_package(session, package)
    assert [item.title for item in view.items] == ["Passport", "Profile Picture", "Identity Card"]
    # İsteğe bağlı kimlik kartı eksik; zorunlu kalemler tamam.
    assert (view.required_met, view.required_total, view.complete) == (2, 2, True)
    assert view.state_label == "Tamamlandı — başvuru başlatılabilir"


@pytest.mark.usefixtures("employees")
def test_viewing_a_package_writes_nothing(session: Session) -> None:
    group_id = _serbia_group(session)
    package = _assign(session, group_id)
    for slug in ("russian_passport", "profile_picture", "residence_card"):
        _document(session, slug)
    session.commit()
    events_before = _package_events(session)

    views = employee_packages(session, OWNER)

    assert [(view.id, view.state) for view in views] == [(package.id, PackageStatus.COMPLETED)]
    assert views[0].status == PackageStatus.OPEN.value  # yazılı durum yenilemeyi bekler
    assert not session.dirty and not session.new
    assert _package_events(session) == events_before


# --- 14.2.3: tamamlanma ve açığa dönme -----------------------------------------------------------


@pytest.mark.usefixtures("employees")
def test_refresh_completes_the_package_when_every_required_item_is_met(session: Session) -> None:
    group_id = _serbia_group(session)
    package = _assign(session, group_id)
    _document(session, "russian_passport")
    assert refresh_employee_packages(session, OWNER, actor=ACTOR) == []
    view = evaluate_package(session, package)
    assert view.state_label == "Açık — 1/3 zorunlu kalem"

    _document(session, "profile_picture")
    _document(session, "residence_card")
    (transition,) = refresh_employee_packages(session, OWNER, actor=ACTOR)
    session.commit()

    assert (transition.previous, transition.current) == (
        PackageStatus.OPEN,
        PackageStatus.COMPLETED,
    )
    assert package.status == PackageStatus.COMPLETED.value
    assert package.completed_at is not None and package.completed_at.tzinfo is UTC
    assert _package_events(session)[-1] == (
        "PACKAGE_COMPLETED",
        ACTOR,
        OWNER,
        {"package_id": package.id, "group_id": group_id},
    )
    # Yeni geçiş yoksa ikinci yenileme olay yazmaz.
    assert refresh_employee_packages(session, OWNER, actor=ACTOR) == []
    assert len(_package_events(session)) == 2


@pytest.mark.usefixtures("employees")
def test_a_package_returns_to_open_when_a_required_document_is_gone(session: Session) -> None:
    group_id = _serbia_group(session)
    package = _assign(session, group_id)
    documents = [
        _document(session, slug)
        for slug in ("russian_passport", "profile_picture", "residence_card")
    ]
    refresh_employee_packages(session, OWNER)
    session.commit()

    documents[2].status = DocumentStatus.ARCHIVED.value
    (transition,) = refresh_employee_packages(session, OWNER, actor=ACTOR)
    session.commit()

    assert transition.current is PackageStatus.OPEN
    assert (package.status, package.completed_at) == (PackageStatus.OPEN.value, None)
    kinds = [(kind, actor) for kind, actor, _, _ in _package_events(session)]
    assert kinds == [
        ("PACKAGE_ASSIGNED", ACTOR),
        ("PACKAGE_COMPLETED", "system"),
        ("PACKAGE_REOPENED", ACTOR),
    ]
    assert _package_events(session)[-1][3] == {
        "package_id": package.id,
        "group_id": group_id,
        "previous_status": "completed",
    }


@pytest.mark.usefixtures("employees")
def test_a_package_is_completed_at_once_when_the_documents_are_already_there(
    session: Session,
) -> None:
    group_id = _serbia_group(session)
    for slug in ("turkish_passport", "profile_picture", "residence_card"):
        _document(session, slug)

    package = _assign(session, group_id)

    assert package.status == PackageStatus.COMPLETED.value
    assert [kind for kind, _, _, _ in _package_events(session)] == [
        "PACKAGE_ASSIGNED",
        "PACKAGE_COMPLETED",
    ]


@pytest.mark.usefixtures("employees")
def test_a_group_without_required_items_is_met_at_once(session: Session) -> None:
    group = create_group(session, name="Boş grup", description=None, actor=ACTOR)
    add_item(
        session, group.id, match_kind="label", file_label="Passport", required=False, actor=ACTOR
    )

    package = _assign(session, group.id)

    assert package.status == PackageStatus.COMPLETED.value


@pytest.mark.usefixtures("employees")
def test_a_group_item_change_reaches_its_packages_at_once(session: Session) -> None:
    group_id = _serbia_group(session, optional_id_card=False)
    package = _assign(session, group_id)
    for slug in ("russian_passport", "profile_picture", "residence_card"):
        _document(session, slug)
    refresh_employee_packages(session, OWNER)
    session.commit()
    assert open_package_counts(session, [group_id]) == {group_id: 0}

    # Yeni zorunlu kalem tamamlanan paketi açığa döndürür; kaldırılınca yeniden tamamlanır.
    item = add_item(session, group_id, match_kind="label", file_label="Identity Card", actor=ACTOR)
    session.commit()
    assert package.status == PackageStatus.OPEN.value
    assert open_package_counts(session, [group_id]) == {group_id: 1}

    remove_item(session, group_id, item.id, actor=ACTOR)
    session.commit()
    assert package.status == PackageStatus.COMPLETED.value
    assert [(kind, actor) for kind, actor, _, _ in _package_events(session)][-2:] == [
        ("PACKAGE_REOPENED", ACTOR),
        ("PACKAGE_COMPLETED", ACTOR),
    ]


# --- iptal ve yeniden açma -----------------------------------------------------------------------


@pytest.mark.usefixtures("employees")
def test_cancelling_needs_a_reason_keeps_the_row_and_logs_no_note(session: Session) -> None:
    group_id = _serbia_group(session)
    package = _assign(session, group_id, note="Belgrad ofisi")

    for reason in (None, "   "):
        with pytest.raises(PackageFormError):
            cancel_package(session, OWNER, package.id, actor=ACTOR, note=reason)
    with pytest.raises(PackageFormError):
        cancel_package(session, OWNER, package.id, actor=ACTOR, note="x" * (NOTE_MAX_LENGTH + 1))

    cancel_package(session, OWNER, package.id, actor=ACTOR, note="Başvuru  iptal")
    session.commit()

    assert package.status == PackageStatus.CANCELLED.value
    assert (package.cancelled_by, package.cancel_note, package.note) == (
        ACTOR,
        "Başvuru iptal",
        "Belgrad ofisi",
    )
    assert package.cancelled_at is not None
    assert session.scalar(select(func.count()).select_from(EmployeePackage)) == 1
    event = _package_events(session)[-1]
    assert event == (
        "PACKAGE_CANCELLED",
        ACTOR,
        OWNER,
        {"package_id": package.id, "group_id": group_id, "previous_status": "open"},
    )
    assert "iptal" not in json.dumps(event[3]) and "Belgrad" not in json.dumps(event[3])
    with pytest.raises(PackageStateError):
        cancel_package(session, OWNER, package.id, actor=ACTOR, note="yine")


@pytest.mark.usefixtures("employees")
def test_a_cancelled_package_is_left_out_of_refresh_and_counts(session: Session) -> None:
    group_id = _serbia_group(session)
    package = _assign(session, group_id)
    cancel_package(session, OWNER, package.id, actor=ACTOR, note="Vazgeçildi")
    session.commit()
    for slug in ("russian_passport", "profile_picture", "residence_card"):
        _document(session, slug)

    assert refresh_employee_packages(session, OWNER) == []
    assert package.status == PackageStatus.CANCELLED.value
    assert package_counts(session) == {}
    assert employee_packages(session, OWNER)[0].state_label == "İptal edildi"


@pytest.mark.usefixtures("employees")
def test_reopening_returns_a_cancelled_package_and_evaluates_it(session: Session) -> None:
    group_id = _serbia_group(session)
    package = _assign(session, group_id)
    cancel_package(session, OWNER, package.id, actor=ACTOR, note="Vazgeçildi")
    session.commit()
    for slug in ("russian_passport", "profile_picture", "residence_card"):
        _document(session, slug)

    reopen_package(session, OWNER, package.id, actor="ik-mehmet")
    session.commit()

    assert package.status == PackageStatus.COMPLETED.value
    assert (package.cancelled_at, package.cancelled_by, package.cancel_note) == (None, None, None)
    assert [
        (kind, actor, data.get("previous_status"))
        for kind, actor, _, data in _package_events(session)
    ][-2:] == [
        ("PACKAGE_REOPENED", "ik-mehmet", "cancelled"),
        ("PACKAGE_COMPLETED", "ik-mehmet", None),
    ]
    with pytest.raises(PackageStateError):
        reopen_package(session, OWNER, package.id, actor=ACTOR)


@pytest.mark.usefixtures("employees")
def test_a_package_of_another_employee_is_not_found(session: Session) -> None:
    group_id = _serbia_group(session)
    package = _assign(session, group_id)

    with pytest.raises(PackageNotFoundError):
        cancel_package(session, OTHER, package.id, actor=ACTOR, note="yanlış")
    with pytest.raises(PackageNotFoundError):
        reopen_package(session, OWNER, 999, actor=ACTOR)


# --- 14.3.1: liste sayıları ----------------------------------------------------------------------


@pytest.mark.usefixtures("employees")
def test_package_counts_give_open_packages_and_missing_required_items(session: Session) -> None:
    group_id = _serbia_group(session)
    other = create_group(session, name="Almanya vizesi", description=None, actor=ACTOR)
    add_item(session, other.id, match_kind="type", type_slug="russian_passport", actor=ACTOR)
    _assign(session, group_id)
    _assign(session, other.id)
    _assign(session, other.id, employee_id=OTHER)
    _document(session, "russian_passport")
    _document(session, "russian_passport", owner=OTHER)
    refresh_employee_packages(session, OWNER)
    refresh_employee_packages(session, OTHER)
    session.commit()

    counts = package_counts(session)
    assert (counts[OWNER].open, counts[OWNER].missing, counts[OWNER].completed) == (1, 2, 1)
    assert (counts[OTHER].open, counts[OTHER].missing, counts[OTHER].completed) == (0, 0, 1)
    assert employees_with_missing_packages(session) == {OWNER}
    assert set(package_counts(session, [OTHER])) == {OTHER}
    assert open_package_counts(session, [group_id, other.id]) == {group_id: 1, other.id: 0}


# --- yenileme noktaları: arşivleme ve taşıma -----------------------------------------------------


def _stored_document(
    session: Session, layout: DataLayout, slug: str, *, upload_id: str = "u_paket1"
) -> Document:
    """Dosyası diskte, kaynağı Inbox'ta olan etkin çıktı (arşivleme ve taşıma dosya ister)."""
    if session.get(Upload, upload_id) is None:
        session.add(Upload(id=upload_id, channel="web"))
        session.flush()
    original = f"{slug}-orijinal".encode()
    inbox = layout.upload_inbox_dir(upload_id)
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"{slug}.pdf").write_bytes(original)
    upload_file = UploadFile(
        upload_id=upload_id,
        original_name=f"{slug}.pdf",
        stored_path=layout.relative(inbox / f"{slug}.pdf"),
        sha256=hashlib.sha256(original).hexdigest(),
        mime="application/pdf",
        page_count=1,
    )
    session.add(upload_file)
    session.flush()
    ready = layout.ensure_employee_tree(OWNER_FOLDER) / "Hazir"
    path = ready / f"Ivan_Petrov-{slug}.pdf"
    path.write_bytes(b"%PDF-1.4 " + slug.encode())
    document = Document(
        employee_id=OWNER,
        type_slug=slug,
        path=layout.relative(path),
        format="pdf",
        source_refs_json=[{"file_id": upload_file.id, "pages": [0]}],
        status=DocumentStatus.ACTIVE.value,
    )
    session.add(document)
    session.flush()
    return document


@pytest.mark.usefixtures("employees")
def test_archiving_a_document_reopens_the_package_in_the_same_transaction(
    session: Session, layout: DataLayout
) -> None:
    group_id = _serbia_group(session)
    package = _assign(session, group_id)
    documents = [
        _stored_document(session, layout, slug)
        for slug in ("russian_passport", "profile_picture", "residence_card")
    ]
    refresh_employee_packages(session, OWNER)
    session.commit()
    assert package.status == PackageStatus.COMPLETED.value

    archive_document(session, layout, documents[2].id, actor=ACTOR)
    session.commit()

    assert package.status == PackageStatus.OPEN.value
    assert _package_events(session)[-1][:3] == ("PACKAGE_REOPENED", ACTOR, OWNER)
    profile = layout.profile_path(OWNER_FOLDER).read_text(encoding="utf-8")
    assert "### Sırbistan iş başvurusu — Açık — 2/3 zorunlu kalem" in profile


@pytest.mark.usefixtures("employees")
def test_moving_a_document_refreshes_both_employees(session: Session, layout: DataLayout) -> None:
    group = create_group(session, name="Almanya vizesi", description=None, actor=ACTOR)
    add_item(session, group.id, match_kind="label", file_label="Passport", actor=ACTOR)
    session.commit()
    owner_package = _assign(session, group.id)
    other_package = _assign(session, group.id, employee_id=OTHER)
    passport = _stored_document(session, layout, "russian_passport")
    refresh_employee_packages(session, OWNER)
    session.commit()
    assert owner_package.status == PackageStatus.COMPLETED.value

    move_document(session, layout, passport.id, OTHER, actor=ACTOR)
    session.commit()

    assert owner_package.status == PackageStatus.OPEN.value
    assert other_package.status == PackageStatus.COMPLETED.value
    moved = [
        (kind, employee_id)
        for kind, actor, employee_id, _ in _package_events(session)[-2:]
        if actor == ACTOR
    ]
    assert moved == [("PACKAGE_REOPENED", OWNER), ("PACKAGE_COMPLETED", OTHER)]
