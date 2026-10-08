"""09.3 — PRD §9 kabul senaryosu S23 uçtan uca: doğum tarihi taşımayan çalışma izni genel yüklemeyle
geliyor; ad-soyad kayıtlı çalışana uyuyor, numarası kayıtlı değil (05.5.4; PLAN.md §D109).

Beklenen (§20.2.2 satır 5a): ad tek etkin çalışana uyuyorsa belge onun Hazir'ına `matched_by: name`
ile girer; çalışana isim yazımı, belge numarası, profil alanı ve iletişim bilgisi eklenmez, profilin
belge listesinde ve yükleme ayrıntısında "Yalnız isimle eşleşti" etiketi durur. Aynı adda iki
çalışan varsa Unresolved (`PERSON_AMBIGUOUS`), yeni çalışan yok. Tek çalışan pasifse 10.5.7 kuralı:
Unresolved (`inactive_employee`), çalışan kişi tahmini; donmuş plan yeniden çalıştırmada değişmez
(K9), yeniden analiz (K18) yeni kuralla Hazir'a koyar.

S10'un eski `dogum-tarihi-yok` düzeni (aynı çalışma izni, kayıtlı ehliyet numarası) bu senaryodur;
S10 belgede okunan doğum tarihi farklı olan düzenle kalır (`tests/test_scenarios_s06_s10.py`).
Senaryo gerçek yoldan geçer: parti yükleme uç noktasıyla açılır ve `process_upload` ile render →
analiz → plan → uygulama adımlarından geçer. Ortam ve yardımcılar S1–S5'inkilerdir. Yapay zekâ
canlı çağrılmaz (kayıtlı yanıt); belge ve kişi sentetiktir, gerçek kimlik belgesi yoktur
(CONVENTIONS §6).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeFieldObservation,
    EmployeeIdentifier,
    EmployeeStatus,
    Event,
    QueueItem,
    QueueKind,
    Upload,
)
from app.events import EventType
from app.matching.match import EmployeeAction, MatchedBy, normalize_document_number
from app.pipeline.plan import PlanEmployee, PlanItem, Route, name_matched_documents
from app.profiles.field_fill import fill_profile_fields
from app.storage import DataLayout
from app.storage.move import move_document
from app.web.auth import get_current_user
from tests import test_scenarios_s01_s05 as s01_s05
from tests.fixtures.gen import (
    PERSON_PRUEBA,
    PERSON_SIDOROV,
    SyntheticPage,
    document_page,
    make_document_pdf_bytes,
    recorded_provider,
)
from tests.test_scenarios_s01_s05 import (
    LICENSE_NUMBER,
    PERMIT_NUMBER,
    PERMIT_OUTPUT,
    SIDOROV_FOLDER,
    SIDOROV_PERSONAL,
    SIGNED_IN,
    _assert_no_personal_values,
    _items,
    _names,
    _process,
    _register_employee,
    _upload,
)
from tests.test_scenarios_s11_s18 import _use_provider

# Ortam fikstürleri S1–S5'inkilerdir; pytest onları bu modüldeki adlarından bulur.
engine = s01_s05.engine
session = s01_s05.session
layout = s01_s05.layout
client = s01_s05.client

# Sentetik adres: belgede açıkça yazılı iletişim bilgisi (05.8.1) — satır 5a'da birikmemeli.
ADDRESS = "Test ulica 1, Novi Sad"
LICENSE = ("serbian_driving_license", LICENSE_NUMBER)
NAME_ONLY_LABELS = {
    "tr": "Yalnız isimle eşleşti",
    "en": "Matched by name only",
    "sr": "Upareno samo po imenu",
}
AMBIGUOUS_REASON = (
    "Belirsiz eşleşme: belgede doğum tarihi yok, ad-soyad birden fazla çalışana uyuyor "
    "(E0001, E0002). Çalışan otomatik eşleştirilmez."
)


def _permit() -> SyntheticPage:
    """Tek sayfalı çalışma izni: ad, soyad, uyruk, izin numarası, son geçerlilik ve adres; doğum
    tarihi yok (tür taşımıyor)."""
    return document_page(
        "work_permit",
        title="RADNA DOZVOLA / WORK PERMIT",
        person=PERSON_SIDOROV,
        document_number=PERMIT_NUMBER,
        expiry_date=date(2027, 3, 31),
        shows=("surname", "given_names", "nationality", "document_number", "expiry_date"),
        language="sr",
        script="latin",
        address=ADDRESS,
    )


def _process_permit(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> str:
    """İzin genel yüklemeyle (bağlam çalışanı yok) gelir ve işlenir; partinin kimliği."""
    permit = _permit()
    upload = _upload(client, session, ("izin.pdf", make_document_pdf_bytes([permit])))
    _process(session, layout, upload, recorded_provider(tmp_path / "kayit-1", [permit]))
    upload_id = upload.id
    session.commit()
    return upload_id


def _count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _assert_nothing_accumulated(session: Session, employee_ids: tuple[str, ...]) -> None:
    """Kayıtlı çalışanlara belgeden hiçbir şey eklenmedi (05.5.4): isim yazımı yalnız İK'nın
    kaydı, numara yalnız ehliyet, profil alanı gözlemi ve iletişim kaydı yok."""
    session.expire_all()
    assert session.scalars(select(Employee.id).order_by(Employee.id)).all() == list(employee_ids)
    assert session.scalars(select(EmployeeAlias.raw_name)).all() == ["Ivan Sidorov"] * len(
        employee_ids
    )
    assert session.execute(
        select(EmployeeIdentifier.kind, EmployeeIdentifier.value).order_by(EmployeeIdentifier.id)
    ).all() == [(LICENSE[0], normalize_document_number(LICENSE[1]))] * len(employee_ids)
    assert (_count(session, EmployeeFieldObservation), _count(session, EmployeeContact)) == (0, 0)
    session.rollback()


def _plan_items(session: Session, upload_id: str) -> tuple[PlanItem, ...]:
    """Partinin güncel planının öğeleri; okuma işlemi bırakılır (SQLite yazma kilidi panel
    isteğini bekletmesin)."""
    session.expire_all()
    items = _items(session, session.get_one(Upload, upload_id))
    session.rollback()
    return items


def _queued_rows(session: Session, upload_id: str) -> list[tuple[str, str]]:
    session.expire_all()
    query = select(QueueItem).where(QueueItem.upload_id == upload_id).order_by(QueueItem.id)
    rows = [(row.kind, row.reason) for row in session.scalars(query)]
    session.rollback()
    return rows


def _upload_events(session: Session, upload_id: str) -> list[Event]:
    session.expire_all()
    return list(
        session.scalars(select(Event).where(Event.upload_id == upload_id).order_by(Event.id))
    )


def _document_rows(session: Session) -> list[Document]:
    session.expire_all()
    return list(session.scalars(select(Document).order_by(Document.id)))


def _documents(session: Session) -> list[tuple[str, str, str]]:
    session.expire_all()
    rows = [
        (document.employee_id, Path(document.path).name, document.status)
        for document in session.scalars(select(Document).order_by(Document.id))
    ]
    session.rollback()
    return rows


def _labelled(html: str, start: str) -> str:
    """`start` ile açılan tablo satırı."""
    assert start in html, start
    return html.split(start, 1)[1].split("</tr>", 1)[0]


def _signed_in_as(client: TestClient, language: str) -> None:
    application = client.app
    assert isinstance(application, FastAPI)
    user = replace(SIGNED_IN, language=language)
    application.dependency_overrides[get_current_user] = lambda: user


def test_s23_permit_without_a_birth_date_lands_in_the_single_employees_hazir_without_accumulating(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    employee_id = _register_employee(session, layout, PERSON_SIDOROV, [LICENSE]).id

    upload_id = _process_permit(session, layout, client, tmp_path)

    # §20.2.2 satır 5a: numara kayıtlı değil, belgede doğum tarihi yok, ad tek etkin çalışana
    # uyuyor → Hazir, `matched_by: name`. Numara temiz olsa da satır 6'ya inilmez.
    (item,) = _plan_items(session, upload_id)
    assert (item.route, item.route_reason, item.target_name) == (Route.READY, None, PERMIT_OUTPUT)
    assert item.employee == PlanEmployee(
        action=EmployeeAction.MATCH, employee_id=employee_id, matched_by=MatchedBy.NAME
    )
    assert _documents(session) == [(employee_id, PERMIT_OUTPUT, "active")]
    assert _names(layout.ready_dir(SIDOROV_FOLDER)) == [PERMIT_OUTPUT]
    assert _queued_rows(session, upload_id) == []

    # Birikim yok: isim yazımı, numara, profil alanı ve iletişim bilgisi eklenmedi; geçmiş belgeden
    # alan dolduran komut (05.7.3) da bu belgeyi atlar.
    _assert_nothing_accumulated(session, (employee_id,))
    assert fill_profile_fields(session, actor="test") == []
    session.commit()
    _assert_nothing_accumulated(session, (employee_id,))

    events = _upload_events(session, upload_id)
    types = [EventType(row.type) for row in events]
    for forbidden in (
        EventType.EMPLOYEE_CREATED,
        EventType.EMPLOYEE_PENDING,
        EventType.EMPLOYEE_FIELD_FILLED,
        EventType.PERSON_NOT_MATCHED,
    ):
        assert forbidden not in types
    (matched,) = [row for row in events if row.type == EventType.PERSON_MATCHED]
    assert (matched.employee_id, matched.data_json) == (
        employee_id,
        {"rule": "name", "matched_by": "name", "employee_ids": [employee_id]},
    )
    assert EventType.OUTPUT_SAVED in types
    _assert_no_personal_values(events, (*SIDOROV_PERSONAL, ADDRESS))

    # Görünürlük: profilin belge listesi ve yükleme ayrıntısının plan/çıktı satırı, üç dilde.
    (document_id,) = [row.id for row in _document_rows(session)]
    session.rollback()  # okuma işlemi bırakılır: SQLite yazma kilidi panel isteğini bekletmesin
    for language, label in NAME_ONLY_LABELS.items():
        _signed_in_as(client, language)
        profile = client.get(f"/employees/{employee_id}")
        assert profile.status_code == 200, profile.text
        listing = profile.text.split('<section class="profile-documents">', 1)[1]
        listing = listing.split("</section>", 1)[0]
        assert label in _labelled(listing, PERMIT_OUTPUT)
        detail = client.get(f"/uploads/{upload_id}")
        assert detail.status_code == 200, detail.text
        assert label in _labelled(detail.text, '<tr id="item-i1"')
        assert label in _labelled(detail.text, f'<tr id="output-{document_id}"')


def test_s23_a_document_moved_by_hr_no_longer_carries_the_name_only_label(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    _register_employee(session, layout, PERSON_SIDOROV, [LICENSE])
    other_id = _register_employee(session, layout, PERSON_PRUEBA, []).id
    session.commit()
    upload_id = _process_permit(session, layout, client, tmp_path)
    (document,) = _document_rows(session)
    document_id = document.id
    assert name_matched_documents([document]) == {document_id}
    session.rollback()

    # İsim eşleşmesi yanlışsa İK belgeyi taşır (10.8.1): sahibini artık İK belirledi, çıktının
    # etiketi kalkar. Donmuş planın öğesi isimle eşleşmiş kalır (K9).
    move_document(session, layout, document_id, other_id, actor=SIGNED_IN.username)
    session.commit()
    (moved,) = _document_rows(session)
    assert (moved.id, moved.employee_id) == (document_id, other_id)
    assert name_matched_documents([moved]) == frozenset()
    session.rollback()

    label = NAME_ONLY_LABELS["tr"]
    profile = client.get(f"/employees/{other_id}")
    assert profile.status_code == 200, profile.text
    listing = profile.text.split('<section class="profile-documents">', 1)[1]
    assert f"/documents/{document_id}/file" in listing.split("</section>", 1)[0]
    assert label not in listing.split("</section>", 1)[0]
    detail = client.get(f"/uploads/{upload_id}")
    assert detail.status_code == 200, detail.text
    assert label in _labelled(detail.text, '<tr id="item-i1"')
    assert label not in _labelled(detail.text, f'<tr id="output-{document_id}"')


def test_s23_two_employees_with_the_same_name_send_it_to_unresolved_without_a_new_employee(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    first = _register_employee(session, layout, PERSON_SIDOROV, [LICENSE])
    namesake = replace(PERSON_SIDOROV, date_of_birth=date(1979, 1, 1))
    second = _register_employee(session, layout, namesake, [LICENSE])

    upload_id = _process_permit(session, layout, client, tmp_path)

    # Satır 5a'nın belirsizi: ad iki kayda uyuyor → Unresolved + `PERSON_AMBIGUOUS` (satır 4'ün
    # kalıbıyla), kişi tahmini yok; yalnız isimle yeni çalışan açılmaz (K7).
    (item,) = _plan_items(session, upload_id)
    assert (item.route, item.route_reason, item.target_name) == (
        Route.UNRESOLVED,
        AMBIGUOUS_REASON,
        None,
    )
    assert item.employee == PlanEmployee(
        action=EmployeeAction.NONE, employee_id=None, matched_by=None
    )
    assert _queued_rows(session, upload_id) == [(QueueKind.UNRESOLVED.value, AMBIGUOUS_REASON)]
    assert _documents(session) == []
    assert _names(layout.employees) == sorted([first.folder_name, second.folder_name])
    _assert_nothing_accumulated(session, (first.id, second.id))

    events = _upload_events(session, upload_id)
    types = [EventType(row.type) for row in events]
    assert EventType.EMPLOYEE_CREATED not in types and EventType.EMPLOYEE_PENDING not in types
    assert EventType.PERSON_MATCHED not in types
    (ambiguous,) = [row for row in events if row.type == EventType.PERSON_AMBIGUOUS]
    assert (ambiguous.employee_id, ambiguous.message, ambiguous.data_json) == (
        None,
        AMBIGUOUS_REASON,
        {"rule": "name_ambiguous", "queue": "unresolved", "employee_ids": ["E0001", "E0002"]},
    )
    _assert_no_personal_values(events, (*SIDOROV_PERSONAL, ADDRESS))


@pytest.mark.parametrize("reactivate", ["rerun", "reanalyze"])
def test_s23_a_single_inactive_employee_keeps_it_in_unresolved_until_reanalysis(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path, reactivate: str
) -> None:
    employee = _register_employee(session, layout, PERSON_SIDOROV, [LICENSE])
    employee_id = employee.id
    employee.status = EmployeeStatus.INACTIVE.value
    session.commit()

    upload_id = _process_permit(session, layout, client, tmp_path)

    # 10.5.7: isim pasif çalışanı bulur ama belge otomatik yerleşmez; çalışan kişi tahmini kalır,
    # hiçbir şey birikmez.
    (item,) = _plan_items(session, upload_id)
    assert item.route is Route.UNRESOLVED
    assert item.route_reason is not None
    assert item.route_reason.startswith(
        f"Pasif çalışan ({employee_id}) ile eşleşti (inactive_employee)"
    )
    session.expire_all()
    (queued,) = session.scalars(select(QueueItem).where(QueueItem.upload_id == upload_id)).all()
    assert queued.payload_json["employee_guess"] == {
        "action": "match",
        "employee_id": employee_id,
        "matched_by": "name",
    }
    session.rollback()
    assert _documents(session) == []
    _assert_nothing_accumulated(session, (employee_id,))

    # İK çalışanı etkinleştirir. Yeniden çalıştırma donmuş planı uygular (K9): belge yerleşmez.
    session.get_one(Employee, employee_id).status = EmployeeStatus.ACTIVE.value
    session.commit()
    if reactivate == "rerun":
        rerun = client.post(f"/api/uploads/{upload_id}/rerun")
        assert rerun.status_code == 200, rerun.text
        assert rerun.json()["version"] == 1
        assert _documents(session) == []
        (frozen,) = _plan_items(session, upload_id)
        assert frozen == item
        return

    # Yeniden analiz yeni plan sürümü açar (K18): çalışan artık etkin, belge isimle Hazir'a girer;
    # yine hiçbir şey birikmez.
    _use_provider(client, recorded_provider(tmp_path / "kayit-2", [_permit()]))
    reanalyzed = client.post(f"/api/uploads/{upload_id}/reanalyze")
    assert reanalyzed.status_code == 200, reanalyzed.text
    assert reanalyzed.json()["version"] == 2
    (placed,) = _plan_items(session, upload_id)
    assert (placed.route, placed.employee) == (
        Route.READY,
        PlanEmployee(
            action=EmployeeAction.MATCH, employee_id=employee_id, matched_by=MatchedBy.NAME
        ),
    )
    assert _documents(session) == [(employee_id, PERMIT_OUTPUT, "active")]
    _assert_nothing_accumulated(session, (employee_id,))
