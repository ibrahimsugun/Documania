"""09.3 — PRD §9 kabul senaryosu S24 uçtan uca: çalışanın tek kaynaklı pasaportu ve arşivdeki
eski pasaportu kalıcı siliniyor (10.5.12; PLAN.md §D110).

Beklenen: tek onayla değişiklik yok; iki onayla iki dosya, `Alinan` kopyaları ve Inbox orijinali
diskten kalkar; belge satırları `deleted`, dosya adresi 404, paket tiki düşer; başka belgeye kaynak
olan orijinal kalır; `DOCUMENT_DELETED` kullanıcı adıyla.

Kurgu: kayıtlı Sidorov'un eski pasaportu ehliyetiyle aynı PDF'te gelir (S4 kalıbı: aynı yüklemeden
iki belge) ve arşivlenir; yeni pasaportu tek sayfalık ayrı bir yüklemedir. "Pasaport" etiketli
grubun paketi yeni pasaportla tamamlanmıştır. İki pasaport profilin iki aşamalı onayıyla
(`/documents/{id}/delete/confirm` → `/prepare` → `/delete`) silinir. Partiler yükleme uç
noktasıyla açılır ve `process_upload` ile işlenir; yapay zekâ canlı çağrılmaz (kayıtlı yanıt).
Belge ve kişi sentetiktir, gerçek kimlik belgesi yoktur (CONVENTIONS §6). Ortam S1–S5'inkidir.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, EmployeePackage, Event, PackageStatus, User
from app.events import EventType
from app.groups import add_item, assign_package, create_group
from app.storage import DataLayout, archive_document
from app.telegram.intent import find_documents
from app.web.auth import SESSION_COOKIE
from tests import test_scenarios_s01_s05 as s01_s05
from tests.fixtures.gen import (
    PERSON_SIDOROV,
    SyntheticPage,
    driving_license_pages,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
)
from tests.test_scenarios_s01_s05 import (
    LICENSE_NUMBER,
    LICENSE_OUTPUT,
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

COOKIE = "s24-oturum"
PASSPORT_NUMBER = "00 0000077"
PASSPORT_OUTPUT = "Ivan_Sidorov-Passport.pdf"
# §20.6 "Belgeyi kalıcı sil" ikinci metninin kalıbı.
SECOND = (
    "Belge dosyası ve kopyaları ({n}) diskten silinecek, başka belgelere de kaynak olan dosyalar "
    "({m}) kalacaktır; bu işlem geri alınamaz. Son kararınız mı?"
)


def _passport(expiry: date) -> SyntheticPage:
    return passport_page(PERSON_SIDOROV, document_number=PASSPORT_NUMBER, expiry_date=expiry)


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def _counts(html: str) -> dict[str, str]:
    return dict(re.findall(r'name="(files_deleted|files_kept)" value="(\d+)"', html))


def _rows(session: Session) -> list[tuple[str, str, str | None]]:
    session.expire_all()
    rows = [
        (document.type_slug, document.status, document.path)
        for document in session.scalars(select(Document).order_by(Document.id))
    ]
    session.rollback()
    return rows


def _world(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> tuple[str, int, int, int]:
    """Sidorov: ehliyet + eski pasaport (aynı PDF, pasaport arşivde), yeni pasaport (tek kaynak)
    ve tamamlanmış "Pasaport" paketi. (çalışan, eski pasaport, yeni pasaport, paket)."""
    client.cookies.set(SESSION_COOKIE, COOKIE)
    # Belge açma erişim logu (10.9.2) `users` satırına bağlanır.
    session.add(
        User(
            id=SIGNED_IN.id,
            username=SIGNED_IN.username,
            password_hash="sentetik",
            role=SIGNED_IN.role,
        )
    )
    employee_id = _register_employee(
        session,
        layout,
        PERSON_SIDOROV,
        [("serbian_driving_license", LICENSE_NUMBER), ("russian_passport", PASSPORT_NUMBER)],
    ).id
    license_front, license_back = driving_license_pages(
        PERSON_SIDOROV, document_number=LICENSE_NUMBER, expiry_date=date(2031, 6, 30)
    )
    pages = [license_front, license_back, _passport(date(2028, 1, 31))]
    first = _upload(client, session, ("eski.pdf", make_document_pdf_bytes(pages)))
    _process(session, layout, first, recorded_provider(tmp_path / "kayit-1", pages))
    session.commit()
    old = session.scalars(select(Document.id).where(Document.type_slug == "russian_passport")).one()
    archive_document(session, layout, old, actor=SIGNED_IN.username)
    session.commit()

    new_page = _passport(date(2034, 1, 31))
    second = _upload(client, session, ("pasaport.pdf", make_document_pdf_bytes([new_page])))
    _process(session, layout, second, recorded_provider(tmp_path / "kayit-2", [new_page]))
    session.commit()
    new = session.scalars(
        select(Document.id).where(
            Document.type_slug == "russian_passport", Document.status == "active"
        )
    ).one()

    group = create_group(session, name="Vize dosyasi", description=None, actor="ik")
    add_item(session, group.id, match_kind="label", file_label="Passport", actor="ik")
    package = assign_package(session, employee_id, group.id, actor="ik").package
    assert package is not None and package.status == PackageStatus.COMPLETED.value
    package_id = package.id
    session.commit()
    return employee_id, old, new, package_id


def test_s24_one_confirmation_changes_nothing_two_delete_the_passports_and_keep_the_shared_original(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    employee_id, old, new, package_id = _world(session, layout, client, tmp_path)
    hazir, alinan = layout.ready_dir(SIDOROV_FOLDER), layout.received_dir(SIDOROV_FOLDER)
    assert _names(hazir) == [LICENSE_OUTPUT, PASSPORT_OUTPUT]
    assert _names(alinan) == ["eski.pdf", "pasaport.pdf"]
    before = _rows(session)
    archived_path = layout.resolve(next(path for _, s, path in before if s == "archived") or "")
    inboxes = {path.parent.name: path for path in layout.inbox.glob("*/*.pdf")}
    assert len(inboxes) == 2
    file_urls = [f"/employees/{employee_id}/documents/{doc}/file" for doc in (old, new)]
    assert [client.get(url).status_code for url in file_urls] == [200, 200]

    # Tek onay: birinci metin ve hazırlık; hiçbir şey değişmez.
    assert client.get(f"/documents/{new}/delete/confirm").status_code == 200
    prepared = client.post(f"/documents/{new}/delete/prepare")
    assert prepared.status_code == 200
    assert SECOND.format(n=3, m=0) in prepared.text
    assert _rows(session) == before
    assert _names(hazir) == [LICENSE_OUTPUT, PASSPORT_OUTPUT] and archived_path.exists()

    # İki onay: yeni pasaport (tek kaynak) ve arşivdeki eski pasaport (ehliyetle ortak kaynak).
    done = client.post(
        f"/documents/{new}/delete",
        data={"confirmation": _token(prepared.text), **_counts(prepared.text)},
        follow_redirects=False,
    )
    assert done.status_code == 303, done.text
    prepared = client.post(f"/documents/{old}/delete/prepare")
    assert SECOND.format(n=1, m=2) in prepared.text
    done = client.post(
        f"/documents/{old}/delete",
        data={"confirmation": _token(prepared.text), **_counts(prepared.text)},
        follow_redirects=False,
    )
    assert done.status_code == 303, done.text

    # İki pasaport dosyası, yeni pasaportun Alinan kopyası ve Inbox orijinali diskten kalktı;
    # ehliyete kaynak olan eski PDF'in orijinali ve Alinan kopyası yerinde.
    assert _names(hazir) == [LICENSE_OUTPUT]
    assert not archived_path.exists()
    assert _names(alinan) == ["eski.pdf"]
    remaining = [path for path in inboxes.values() if path.exists()]
    assert [path.name for path in remaining] == ["eski.pdf"]
    assert [(slug, status, path is None) for slug, status, path in _rows(session)] == [
        ("serbian_driving_license", "active", False),
        ("russian_passport", "deleted", True),
        ("russian_passport", "deleted", True),
    ]
    # Dosya adresi 404, paket tiki düştü, bot belgeyi bulmuyor.
    assert [client.get(url).status_code for url in file_urls] == [404, 404]
    session.expire_all()
    assert session.get_one(EmployeePackage, package_id).status == PackageStatus.OPEN.value
    assert find_documents(session, employee_id, ["russian_passport"]) == []
    deleted = session.scalars(
        select(Event).where(Event.type == EventType.DOCUMENT_DELETED.value).order_by(Event.id)
    ).all()
    assert [(event.document_id, event.actor) for event in deleted] == [
        (new, SIGNED_IN.username),
        (old, SIGNED_IN.username),
    ]
    assert [event.data_json["previous_status"] for event in deleted if event.data_json] == [
        "active",
        "archived",
    ]
    session.rollback()
