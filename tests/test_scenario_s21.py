"""09.3 — PRD §9 kabul senaryosu S21 uçtan uca: "Sırbistan iş başvurusu" grubu (Passport etiketi,
Profile Picture etiketi, çevirili diploma türü) çalışana paket olarak tanımlı; önce Rus pasaportu,
sonra fotoğraf ve çevirili diploma yükleniyor (14.2.2, 14.2.3; PLAN.md §C89).

Beklenen: pasaport kalemi ülkeye bakılmadan tik alır; üç belge Hazir'a girince paket "Tamamlandı —
başvuru başlatılabilir" olur ve `PACKAGE_COMPLETED` yazılır; diploma arşivlenince paket açığa döner
ve `PACKAGE_REOPENED` yazılır.

Senaryo gerçek yoldan geçer: paket panelin profil formuyla (`POST /employees/{id}/packages`)
tanımlanır, partiler yükleme uç noktasıyla açılır ve `process_upload` ile render → analiz → plan →
uygulama adımlarından geçer (yenileme uygulamanın sonunda, aynı işlemde), diploma `archive_document`
ile arşivlenir (panelin iki aşamalı arşiv onayı `tests/web/test_queue_page.py`'dedir). Ortam ve
yardımcılar S1–S5'inkilerdir; çevirili diploma türü kataloğa S19'daki gibi veritabanı kaydı olarak
eklenir. Yapay zekâ canlı çağrılmaz (kayıtlı yanıt); belgeler ve kişi sentetiktir, gerçek kimlik
belgesi yoktur (CONVENTIONS §6).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import Catalog, CatalogEntry, import_catalog
from app.db.models import Document, EmployeePackage, Event, PackageStatus
from app.events import EventType
from app.groups import add_item, create_group
from app.storage import DataLayout, archive_document
from tests import test_scenarios_s01_s05 as s01_s05
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    SyntheticPage,
    document_page,
    make_document_pdf_bytes,
    passport_page,
    profile_picture_page,
    recorded_provider,
)
from tests.test_scenarios_s01_s05 import (
    CATALOG,
    ORNEKOVA_FOLDER,
    ORNEKOVA_PERSONAL,
    PASSPORT_NUMBER,
    SIGNED_IN,
    _names,
    _process,
    _register_employee,
    _upload,
)

# Ortam fikstürleri S1–S5'inkilerdir; pytest onları bu modüldeki adlarından bulur.
engine = s01_s05.engine
session = s01_s05.session
layout = s01_s05.layout
client = s01_s05.client

DIPLOMA = "translated_diploma"
DIPLOMA_NUMBER = "DIP-0000021"
DIPLOMA_FIELDS = ("surname", "given_names", "document_number")
PASSPORT_OUTPUT = "Test_Ornekova-Passport.pdf"
DIPLOMA_OUTPUT = "Test_Ornekova-Translated-Diploma.pdf"
PHOTO_OUTPUT = "Test_Ornekova-Profile-Picture.jpeg"
GROUP_NAME = "Sırbistan iş başvurusu"
COMPLETED = "Tamamlandı — başvuru başlatılabilir"


def _diploma_entry() -> CatalogEntry:
    """Ülkesiz çevirili diploma türü; çalışma izninin kaydından türetilir (tek ya da iki sayfa)."""
    permit = CATALOG.get("work_permit")
    assert permit is not None
    return permit.model_copy(
        update={
            "slug": DIPLOMA,
            "name": "Translated Diploma",
            "file_label": "Translated Diploma",
            "description": "Yeminli tercümesiyle diploma.",
            "required_fields": DIPLOMA_FIELDS,
            "prompt_description": "Diplomanın tercümesi; sahibinin adı, soyadı ve numarası yazılı.",
        }
    )


def _passport() -> SyntheticPage:
    return passport_page(
        PERSON_ORNEKOVA, document_number=PASSPORT_NUMBER, expiry_date=date(2030, 1, 1)
    )


def _diploma() -> SyntheticPage:
    return document_page(
        DIPLOMA,
        title="DIPLOMA — CERTIFIED TRANSLATION",
        person=PERSON_ORNEKOVA,
        document_number=DIPLOMA_NUMBER,
        shows=("surname", "given_names", "document_number"),
        language="en",
        script="latin",
        required_fields=DIPLOMA_FIELDS,
    )


@dataclass(frozen=True)
class _PackageRow:
    id: int
    status: str
    requested_by: str
    completed_at: datetime | None


@dataclass(frozen=True)
class _EventRow:
    type: str
    actor: str
    employee_id: str | None
    upload_id: str | None
    data: dict[str, Any] | None


def _package(session: Session) -> _PackageRow:
    """Tek paketin güncel satırı; okuma işlemi bırakılır (SQLite yazma kilidi panel isteğini
    bekletmesin)."""
    session.expire_all()
    (package,) = session.scalars(select(EmployeePackage)).all()
    row = _PackageRow(package.id, package.status, package.requested_by, package.completed_at)
    session.rollback()
    return row


def _package_events(session: Session) -> list[_EventRow]:
    kinds = [kind.value for kind in EventType if kind.value.startswith("PACKAGE_")]
    rows = [
        _EventRow(row.type, row.actor, row.employee_id, row.upload_id, row.data_json)
        for row in session.scalars(select(Event).where(Event.type.in_(kinds)).order_by(Event.id))
    ]
    session.rollback()
    return rows


def _card(client: TestClient, employee_id: str, package_id: int) -> str:
    page = client.get(f"/employees/{employee_id}")
    assert page.status_code == 200
    match = re.search(
        rf'<article class="package-card[^"]*" id="package-{package_id}">.*?</article>',
        page.text,
        re.S,
    )
    assert match is not None
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", match.group(0))).strip()


def test_s21_package_ticks_as_documents_arrive_completes_and_reopens_on_archive(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    import_catalog(session, Catalog((*CATALOG, _diploma_entry())))
    session.commit()
    employee_id = _register_employee(
        session,
        layout,
        PERSON_ORNEKOVA,
        [("russian_passport", PASSPORT_NUMBER), (DIPLOMA, DIPLOMA_NUMBER)],
    ).id
    group = create_group(session, name=GROUP_NAME, description=None, actor="ik")
    add_item(session, group.id, match_kind="label", file_label="Passport", actor="ik")
    add_item(session, group.id, match_kind="label", file_label="Profile Picture", actor="ik")
    add_item(session, group.id, match_kind="type", type_slug=DIPLOMA, actor="ik")
    group_id = group.id
    session.commit()

    # İK paketi profilden tanımlar; belge yok, paket açık.
    assigned = client.post(
        f"/employees/{employee_id}/packages",
        data={"group_id": str(group_id)},
        follow_redirects=False,
    )
    assert assigned.status_code == 303
    package = _package(session)
    assert (package.status, package.requested_by) == ("open", SIGNED_IN.username)
    assert "Açık — 0/3 zorunlu kalem" in _card(client, employee_id, package.id)

    # 1) Rus pasaportu: "Passport" etiketli kalem ülkeye bakılmadan tik alır; paket açık kalır.
    passport = _passport()
    first = _upload(client, session, ("pasaport.pdf", make_document_pdf_bytes([passport])))
    _process(session, layout, first, recorded_provider(tmp_path / "kayit-1", [passport]))
    session.rollback()

    assert _package(session).status == PackageStatus.OPEN.value
    card = _card(client, employee_id, package.id)
    assert "Açık — 1/3 zorunlu kalem" in card
    assert f"✓ Karşılandı: Passport zorunlu {PASSPORT_OUTPUT}" in card
    assert "○ Eksik: Profile Picture zorunlu" in card
    assert "○ Eksik: Translated Diploma zorunlu" in card
    assert [row.type for row in _package_events(session)] == ["PACKAGE_ASSIGNED"]

    # 2) Çevirili diploma ve fotoğraf aynı dosyada: ikisi de Hazir'a girer, paket tamamlanır.
    diploma, photo = _diploma(), profile_picture_page()
    second = _upload(client, session, ("diploma.pdf", make_document_pdf_bytes([diploma, photo])))
    second_id = second.id
    _process(session, layout, second, recorded_provider(tmp_path / "kayit-2", [diploma, photo]))
    session.rollback()

    ready = layout.ready_dir(ORNEKOVA_FOLDER)
    assert _names(ready) == sorted([PASSPORT_OUTPUT, DIPLOMA_OUTPUT, PHOTO_OUTPUT])
    package = _package(session)
    assert package.status == PackageStatus.COMPLETED.value
    assert package.completed_at is not None
    completed = _package_events(session)[-1]
    assert completed == _EventRow(
        EventType.PACKAGE_COMPLETED.value,
        "system",
        employee_id,
        second_id,
        {"package_id": package.id, "group_id": group_id},
    )
    card = _card(client, employee_id, package.id)
    assert COMPLETED in card
    assert f"✓ Karşılandı: Translated Diploma zorunlu {DIPLOMA_OUTPUT}" in card
    assert f"✓ Karşılandı: Profile Picture zorunlu {PHOTO_OUTPUT}" in card
    profile_md = layout.profile_path(ORNEKOVA_FOLDER).read_text(encoding="utf-8")
    assert f"### {GROUP_NAME} — {COMPLETED}" in profile_md
    missing = client.get("/employees", params={"packages": "missing"})
    assert "Eksik paketi olan çalışan yok." in missing.text

    # 3) Diploma arşivlenince kalem tikini kaybeder, paket açığa döner ve olay yazılır.
    diploma_id = session.scalars(select(Document.id).where(Document.type_slug == DIPLOMA)).one()
    archive_document(session, layout, diploma_id, actor="ik-ayse")
    session.commit()

    package = _package(session)
    assert (package.status, package.completed_at) == (PackageStatus.OPEN.value, None)
    assert _package_events(session)[-1] == _EventRow(
        EventType.PACKAGE_REOPENED.value,
        "ik-ayse",
        employee_id,
        None,
        {"package_id": package.id, "group_id": group_id, "previous_status": "completed"},
    )
    card = _card(client, employee_id, package.id)
    assert "Açık — 2/3 zorunlu kalem" in card and "○ Eksik: Translated Diploma zorunlu" in card
    assert "1 açık · 1 eksik" in client.get("/employees", params={"packages": "missing"}).text
    profile_md = layout.profile_path(ORNEKOVA_FOLDER).read_text(encoding="utf-8")
    assert f"### {GROUP_NAME} — Açık — 2/3 zorunlu kalem" in profile_md

    # Olaylar kişisel değer taşımaz (CONVENTIONS §6).
    events = _package_events(session)
    assert [row.type for row in events] == [
        "PACKAGE_ASSIGNED",
        "PACKAGE_COMPLETED",
        "PACKAGE_REOPENED",
    ]
    logged = json.dumps([row.data for row in events], ensure_ascii=False)
    for value in ORNEKOVA_PERSONAL:
        assert value not in logged
