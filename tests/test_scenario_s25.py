"""09.3 — PRD §9 kabul senaryosu S25 uçtan uca: pasif çalışan kalıcı siliniyor; bir yüklemesi
yalnız ona, öbürü onunla başka bir çalışana ait (10.5.13; PLAN.md §D110, §D116).

Beklenen: çalışan klasörü, belgeleri, alt kayıtları, yalnız ona ait yüklemenin orijinali ve sayfa
görüntüleri silinir; ortak yüklemenin orijinali ve öbür çalışanın sayfaları kalır; çalışan satırı
`deleted`, kişisel alanları boş; aynı kişinin yeni belgesi eski kayda eşleşmez; olaylarda isim
kalmaz; etkin çalışanda istek reddedilir.

Kurgu: kayıtlı Sidorov'un pasaportu tek sayfalık kendi yüklemesidir; ehliyeti (iki yüz) ile kayıtlı
Ornekova'nın pasaportu aynı PDF'te gelir. Sidorov pasife alınır ve profilin iki aşamalı onayıyla
(`/employees/{id}/delete/confirm` → `/prepare` → `/delete`) silinir. Partiler yükleme uç noktasıyla
açılır ve `process_upload` ile işlenir; yapay zekâ canlı çağrılmaz (kayıtlı yanıt). Belge ve kişi
sentetiktir, gerçek kimlik belgesi yoktur (CONVENTIONS §6). Ortam S1–S5'inkidir.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    Employee,
    EmployeeAlias,
    EmployeeIdentifier,
    EmployeeStatus,
    Event,
    Page,
    Plan,
    UploadFile,
    User,
)
from app.matching.status import change_employee_status
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE
from tests import test_scenarios_s01_s05 as s01_s05
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_SIDOROV,
    driving_license_pages,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
)
from tests.test_scenarios_s01_s05 import (
    LICENSE_NUMBER,
    PASSPORT_NUMBER,
    SIDOROV_FOLDER,
    SIGNED_IN,
    _names,
    _process,
    _register_employee,
    _upload,
)

engine = s01_s05.engine
session = s01_s05.session
layout = s01_s05.layout
client = s01_s05.client

COOKIE = "s25-oturum"
SIDOROV_PASSPORT = "00 0000077"
# §20.6 "Çalışanı kalıcı sil" metinleri (§D110 i).
FIRST = "Ivan Sidorov çalışanını bütün belgeleriyle kalıcı olarak silmek üzeresiniz. Emin misiniz?"
SECOND = (
    "Çalışanın klasörü, belgeleri ({n}) ve kişisel bilgileri silinecek, yalnız E numarası "
    "kalacaktır; bu işlem geri alınamaz. Son kararınız mı?"
)
# Silmeden sonra olaylarda, planlarda ve çalışan satırında geçmemesi gereken değerler.
SIDOROV_VALUES = ("sidorov", "1985-05-05", "0000077", LICENSE_NUMBER)


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def _world(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> tuple[str, str]:
    """Sidorov (pasaport tek başına; ehliyet Ornekova'nın pasaportuyla aynı PDF'te) ve Ornekova.
    (Sidorov, Ornekova)."""
    client.cookies.set(SESSION_COOKIE, COOKIE)
    session.add(
        User(
            id=SIGNED_IN.id,
            username=SIGNED_IN.username,
            password_hash="sentetik",
            role=SIGNED_IN.role,
        )
    )
    sidorov = _register_employee(
        session,
        layout,
        PERSON_SIDOROV,
        [("serbian_driving_license", LICENSE_NUMBER), ("russian_passport", SIDOROV_PASSPORT)],
    ).id
    ornekova = _register_employee(
        session, layout, PERSON_ORNEKOVA, [("russian_passport", PASSPORT_NUMBER)]
    ).id
    session.commit()

    own = [
        passport_page(
            PERSON_SIDOROV, document_number=SIDOROV_PASSPORT, expiry_date=date(2034, 1, 31)
        )
    ]
    first = _upload(client, session, ("pasaport.pdf", make_document_pdf_bytes(own)))
    _process(session, layout, first, recorded_provider(tmp_path / "kayit-1", own))
    session.commit()

    license_front, license_back = driving_license_pages(
        PERSON_SIDOROV, document_number=LICENSE_NUMBER, expiry_date=date(2031, 6, 30)
    )
    shared = [
        license_front,
        license_back,
        passport_page(
            PERSON_ORNEKOVA, document_number=PASSPORT_NUMBER, expiry_date=date(2030, 1, 1)
        ),
    ]
    second = _upload(client, session, ("ortak.pdf", make_document_pdf_bytes(shared)))
    _process(session, layout, second, recorded_provider(tmp_path / "kayit-2", shared))
    session.commit()

    change_employee_status(
        session,
        session.get_one(Employee, sidorov),
        EmployeeStatus.INACTIVE,
        actor=SIGNED_IN.username,
        reason="isten ayrildi",
    )
    session.commit()
    return sidorov, ornekova


def _inbox(session: Session, layout: DataLayout, name: str) -> Path:
    stored = session.scalars(select(UploadFile.stored_path).where(UploadFile.original_name == name))
    return layout.resolve(stored.one())


def _page_images(session: Session, layout: DataLayout, name: str) -> list[bool]:
    file_id = session.scalars(select(UploadFile.id).where(UploadFile.original_name == name)).one()
    pages = session.scalars(select(Page).where(Page.file_id == file_id).order_by(Page.index))
    return [
        page.image_path is not None and layout.resolve(page.image_path).is_file() for page in pages
    ]


def _personal_dump(session: Session, employee_id: str) -> str:
    rows: list[object] = [
        [event.message, event.data_json] for event in session.scalars(select(Event))
    ]
    rows.extend(plan.json for plan in session.scalars(select(Plan)))
    employee = session.get_one(Employee, employee_id)
    rows.append(
        [employee.given_names, employee.surname, employee.folder_name, str(employee.date_of_birth)]
    )
    return json.dumps(rows, ensure_ascii=False, default=str).casefold()


def test_s25_the_inactive_employee_is_deleted_and_the_shared_upload_stays(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    sidorov, ornekova = _world(session, layout, client, tmp_path)
    folder = layout.employee_dir(SIDOROV_FOLDER)
    own_inbox, shared_inbox = (
        _inbox(session, layout, "pasaport.pdf"),
        _inbox(session, layout, "ortak.pdf"),
    )
    ornekova_ready = layout.ready_dir(session.get_one(Employee, ornekova).folder_name)
    owners = sorted(session.execute(select(Document.employee_id, Document.type_slug)).tuples())
    assert owners == [
        (sidorov, "russian_passport"),
        (sidorov, "serbian_driving_license"),
        (ornekova, "russian_passport"),
    ]
    documents = session.scalars(select(Document).where(Document.employee_id == sidorov)).all()
    assert len(documents) == 2
    assert _page_images(session, layout, "pasaport.pdf") == [True]
    assert _page_images(session, layout, "ortak.pdf") == [True, True, True]
    session.rollback()

    # Etkin çalışanda istek reddedilir.
    assert client.get(f"/employees/{ornekova}/delete/confirm").status_code == 409
    assert client.post(f"/employees/{ornekova}/delete/prepare").status_code == 409

    # Tek onay: birinci metin ve hazırlık; hiçbir şey değişmez.
    first = client.get(f"/employees/{sidorov}/delete/confirm")
    assert first.status_code == 200 and FIRST in first.text
    prepared = client.post(f"/employees/{sidorov}/delete/prepare")
    assert prepared.status_code == 200 and SECOND.format(n=2) in prepared.text
    session.expire_all()
    assert session.get_one(Employee, sidorov).status == EmployeeStatus.INACTIVE.value
    assert folder.is_dir() and own_inbox.is_file()
    session.rollback()

    # İki onay.
    done = client.post(
        f"/employees/{sidorov}/delete",
        data={"confirmation": _token(prepared.text), "documents": "2"},
        follow_redirects=False,
    )
    assert done.status_code == 303, done.text
    assert client.get(f"/employees/{sidorov}").status_code == 410

    session.expire_all()
    # Klasör, yalnız ona ait yüklemenin orijinali ve sayfa görüntüsü gitti.
    assert not folder.exists()
    assert not own_inbox.exists()
    assert _page_images(session, layout, "pasaport.pdf") == [False]
    # Ortak yüklemenin orijinali ve Ornekova'nın sayfası, belgesi, klasörü kaldı.
    assert shared_inbox.is_file()
    assert _page_images(session, layout, "ortak.pdf") == [False, False, True]
    assert len(_names(ornekova_ready)) == 1
    # Çalışan satırı iskelet, belgeler `deleted`, alt kayıtlar yok.
    employee = session.get_one(Employee, sidorov)
    assert employee.status == EmployeeStatus.DELETED.value
    assert (employee.given_names, employee.surname, employee.date_of_birth) == ("", "", None)
    assert {
        d.status for d in session.scalars(select(Document).where(Document.employee_id == sidorov))
    } == {"deleted"}
    for model in (EmployeeAlias, EmployeeIdentifier):
        assert session.scalars(select(model).where(model.employee_id == sidorov)).all() == []
    # Olaylarda ve planlarda isim, doğum tarihi, numara kalmadı.
    dump = _personal_dump(session, sidorov)
    for value in SIDOROV_VALUES:
        assert value.casefold() not in dump, value
    assert "ornekova" in dump  # öbür çalışanın kayıtları yerinde
    (event,) = session.scalars(select(Event).where(Event.type == "EMPLOYEE_DELETED")).all()
    assert event.actor == SIGNED_IN.username and event.data_json["documents"] == 2
    session.rollback()

    # Aynı kişinin yeni belgesi (yeni tarama: aynı numara, aynı ad ve doğum tarihi) eski kayda
    # eşleşmez: yeni çalışan açılır, E numarası yenidir. (Aynı baytların yeniden yüklenmesi K10
    # tekrarıdır ve işlenmez — PLAN.md §D116 j.)
    again = [
        passport_page(
            PERSON_SIDOROV, document_number=SIDOROV_PASSPORT, expiry_date=date(2035, 2, 28)
        )
    ]
    third = _upload(client, session, ("yeni.pdf", make_document_pdf_bytes(again)))
    _process(session, layout, third, recorded_provider(tmp_path / "kayit-3", again))
    session.commit()
    (placed,) = session.scalars(
        select(Document).where(
            Document.status == "active",
            Document.type_slug == "russian_passport",
            Document.employee_id != ornekova,
        )
    ).all()
    assert placed.employee_id not in (sidorov, ornekova)
    assert placed.employee_id == "E0003"  # K8: silinen E0001 yeniden verilmedi
    assert session.get_one(Employee, placed.employee_id).surname.casefold() == "sidorov"
    assert session.get_one(Employee, sidorov).status == EmployeeStatus.DELETED.value
