"""15.3.2 uçtan uca — belge yüklendikçe ek profil alanları (anne adı, doğum yeri, kişisel numara)
çalışanın profiline işlenir (05.7.3 kuralı; PLAN.md §D123 e).

Kurgu: kayıtlı Sidorov'un Sırbistan oturma izni (iki yüz) yüklenir. Ön yüz anne adını, doğum
yerini ve kişisel numarayı yazar; arka yüzün TD1 MRZ'si kişisel numarayı isteğe bağlı veride taşır
(veren devlet `SRB`). Profilde dolu baba adı belgede farklı okunur: değişmez, uyarı olur. Parti
yükleme uç noktasıyla açılır ve `process_upload` ile işlenir; yapay zekâ canlı çağrılmaz (kayıtlı
yanıt). Kişi ve belge sentetiktir (CONVENTIONS §6). Ortam S1–S5'inkidir.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Employee, EmployeeFieldObservation, Event
from app.events import EventType
from app.storage import DataLayout
from tests import test_scenarios_s01_s05 as s01_s05
from tests.fixtures.gen import (
    PERSON_SIDOROV,
    make_document_pdf_bytes,
    recorded_provider,
    residence_card_pages,
)
from tests.test_scenarios_s01_s05 import RESIDENCE_NUMBER, _process, _register_employee, _upload

engine = s01_s05.engine
session = s01_s05.session
layout = s01_s05.layout
client = s01_s05.client

SIDOROV = replace(
    PERSON_SIDOROV,
    mother_name="Galina",
    father_name="Petr",
    place_of_birth="TULA",
    personal_number="0505985 710001",
)
DETAILS = ("mother_name", "father_name", "place_of_birth", "personal_number")


def test_uploaded_document_fills_the_detail_fields_of_the_profile(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    employee_id = _register_employee(
        session, layout, PERSON_SIDOROV, [("serbian_residence_card", RESIDENCE_NUMBER)]
    ).id
    session.get_one(Employee, employee_id).father_name = "Pavel"
    session.commit()
    pages = residence_card_pages(
        SIDOROV,
        document_number=RESIDENCE_NUMBER,
        expiry_date=date(2029, 12, 31),
        with_mrz=True,
        details=DETAILS,
    )

    upload = _upload(client, session, ("boravak.pdf", make_document_pdf_bytes(pages)))
    _process(session, layout, upload, recorded_provider(tmp_path / "kayit", pages))
    session.commit()

    employee = session.get_one(Employee, employee_id)
    assert (employee.mother_name, employee.place_of_birth) == ("Galina", "TULA")
    # MRZ önce gelir: numara arka yüzün MRZ'sinden, ülkesi MRZ'yi veren devlet.
    assert (employee.personal_number, employee.personal_number_country) == (
        "0505985710001",
        "SRB",
    )
    assert employee.father_name == "Pavel"
    outcomes = dict(
        session.execute(
            select(EmployeeFieldObservation.field, EmployeeFieldObservation.outcome).where(
                EmployeeFieldObservation.field.in_(DETAILS)
            )
        ).all()
    )
    assert outcomes == {
        "mother_name": "filled",
        "father_name": "conflict",
        "place_of_birth": "filled",
        "personal_number": "filled",
    }
    filled = session.scalars(
        select(Event).where(Event.type == EventType.EMPLOYEE_FIELD_FILLED.value)
    ).all()
    logged = json.dumps([[event.message, event.data_json] for event in filled], ensure_ascii=False)
    assert {"mother_name", "place_of_birth", "personal_number"} <= {
        event.data_json["field"] for event in filled
    }
    for value in ("Galina", "TULA", "0505985", "710001"):
        assert value not in logged
