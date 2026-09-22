"""10.5.1-10.5.4 — çalışan profili: CV benzeri kart, profil fotoğrafı yokluğu, belge listesi ve
açma/indirme, bağlam çalışanıyla yükleme; 05.7.3 — alanın kaynağı ve belgede okunan farklı değer.

Veri sentetiktir: çalışanlar, belgeler ve dosyalar testte üretilir (`tests/fixtures/gen.py`
yardımcılarıyla); gerçek kimlik belgesi ya da yapay zekâ çağrısı yoktur. Sınamalar HTTP
katmanından (`TestClient`) ve profil çekirdeğinden (`build_profile`) yapılır.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    ContactKind,
    Document,
    DocumentStatus,
    Employee,
    EmployeeContact,
    EmployeeFieldObservation,
    EmployeeIdentifier,
    FieldOutcome,
    KnownDocumentType,
    Upload,
    UploadFile,
)
from app.profiles.render import calculate_age
from app.storage import DataLayout
from app.web.routers.employees import build_profile
from app.web.routers.upload_page import UploadProcessor, get_upload_processor
from tests.fixtures.gen import make_docx_bytes, make_pdf_bytes, make_portrait_image_bytes

PASSPORT = "russian_passport"
PHOTO = "profile_picture"
ATTACHMENT = "attachment"
EMPTY = "—"

ACTIVE = DocumentStatus.ACTIVE.value
SUPERSEDED = DocumentStatus.SUPERSEDED.value
ARCHIVED = DocumentStatus.ARCHIVED.value


def _catalog(session: Session) -> None:
    for slug, name, label in (
        (PASSPORT, "Rus Pasaportu", "Pasaport"),
        (PHOTO, "Profile Picture", "Profile-Picture"),
        (ATTACHMENT, "Ek Dosya", "Attachment"),
    ):
        session.add(
            KnownDocumentType(
                slug=slug,
                name=name,
                file_label=label,
                sides="single",
                direct=True,
                analyze=True,
                output_format="pdf",
            )
        )
    session.flush()


def _employee(
    session: Session,
    number: int = 1,
    given_names: str = "Dmitry",
    surname: str = "Vasiliev",
    **fields: object,
) -> Employee:
    employee_id = f"E{number:04d}"
    employee = Employee(
        id=employee_id,
        folder_name=f"{given_names}_{surname}_{employee_id}",
        given_names=given_names,
        surname=surname,
        **fields,
    )
    session.add(employee)
    session.flush()
    return employee


def _document(
    session: Session,
    layout: DataLayout,
    employee: Employee,
    slug: str,
    file_name: str,
    content: bytes | None,
    *,
    status: str = ACTIVE,
    created_at: datetime | None = None,
    sequence_no: int = 1,
) -> Document:
    """Belge satırını yazar; `content` verilirse dosyayı çalışanın `Hazir/` klasörüne koyar."""
    directory = layout.ensure_employee_tree(employee.folder_name) / "Hazir"
    path = directory / file_name
    if content is not None:
        path.write_bytes(content)
    document = Document(
        employee_id=employee.id,
        type_slug=slug,
        path=layout.relative(path),
        format=path.suffix.removeprefix("."),
        sequence_no=sequence_no,
        source_refs_json=[],
        status=status,
    )
    if created_at is not None:
        document.created_at = created_at
    session.add(document)
    session.flush()
    return document


def _fields(html: str) -> dict[str, str]:
    """Kartın `<dt>` etiketi → `<dd>` metni (etiketsiz, boşluklar tekleştirilmiş)."""
    card = html.split('<dl class="profile-fields">', 1)[1].split("</dl>", 1)[0]
    pairs = re.findall(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", card, re.S)
    return {
        label: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip() for label, value in pairs
    }


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        _catalog(session)
        session.commit()


# --- 10.5.1: kart -------------------------------------------------------------------------------


def test_card_shows_every_field_of_the_employee(
    client: TestClient, session_factory: sessionmaker[Session], seeded: None
) -> None:
    date_of_birth = date(1988, 3, 14)
    with session_factory() as session:
        employee = _employee(
            session,
            given_names="Dmitry",
            surname="Vasiliev",
            other_names="Ivanovich",
            original_script_name="Васильев Дмитрий",
            nationality="RUS",
            date_of_birth=date_of_birth,
        )
        session.add_all(
            [
                EmployeeIdentifier(employee_id=employee.id, kind=PASSPORT, value="711234567"),
                EmployeeIdentifier(employee_id=employee.id, kind="work_permit", value="WP-0042"),
                EmployeeContact(
                    employee_id=employee.id, kind=ContactKind.PHONE.value, value="+90 555 000 11 22"
                ),
                EmployeeContact(
                    employee_id=employee.id, kind=ContactKind.PHONE.value, value="+90 555 999 88 77"
                ),
                EmployeeContact(
                    employee_id=employee.id,
                    kind=ContactKind.EMAIL.value,
                    value="dmitry@example.test",
                ),
                EmployeeContact(
                    employee_id=employee.id,
                    kind=ContactKind.ADDRESS.value,
                    value="Örnek Mah. 1. Sok. No:2, İstanbul",
                ),
                # Eski numara (`is_current` yanlış) kartta görünmez.
                EmployeeContact(
                    employee_id=employee.id,
                    kind=ContactKind.PHONE.value,
                    value="+90 555 111 11 11",
                    is_current=False,
                ),
            ]
        )
        session.commit()

    response = client.get("/employees/E0001")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Dmitry Vasiliev · belgeee</title>" in response.text
    assert "<h1>Dmitry Vasiliev</h1>" in response.text
    assert "E0001 · Aktif" in response.text
    assert _fields(response.text) == {
        "Ad": "Dmitry",
        "Soyad": "Vasiliev",
        "Diğer isimler": "Ivanovich",
        "Orijinal yazım": "Васильев Дмитрий",
        "Vatandaşlık": "RUS",
        "Doğum tarihi": "14.03.1988",
        "Yaş": str(calculate_age(date_of_birth, today=date.today())),
        "Telefon": "+90 555 000 11 22 +90 555 999 88 77",
        "E-posta": "dmitry@example.test",
        "Adres": "Örnek Mah. 1. Sok. No:2, İstanbul",
        "Belge numaraları": "Rus Pasaportu 711234567 work_permit WP-0042",
    }
    assert "+90 555 111 11 11" not in response.text


def test_unknown_fields_show_a_dash_instead_of_disappearing(
    client: TestClient, session_factory: sessionmaker[Session], seeded: None
) -> None:
    with session_factory() as session:
        _employee(session, given_names="Nino", surname="Beridze")
        session.commit()

    fields = _fields(client.get("/employees/E0001").text)

    assert fields.pop("Ad") == "Nino"
    assert fields.pop("Soyad") == "Beridze"
    assert fields == {
        "Diğer isimler": EMPTY,
        "Orijinal yazım": EMPTY,
        "Vatandaşlık": EMPTY,
        "Doğum tarihi": EMPTY,
        "Yaş": EMPTY,
        "Telefon": EMPTY,
        "E-posta": EMPTY,
        "Adres": EMPTY,
        "Belge numaraları": EMPTY,
    }


def test_age_is_the_completed_years_on_the_reference_day(
    layout: DataLayout, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        _employee(session, 1, "Ada", "Once", date_of_birth=date(1990, 9, 19))
        _employee(session, 2, "Ada", "Bugun", date_of_birth=date(1990, 9, 18))
        _employee(session, 3, "Ada", "Yok")
        session.commit()

        today = date(2026, 9, 18)
        ages = {
            employee_id: build_profile(session, layout, employee_id, today=today).age  # type: ignore[union-attr]
            for employee_id in ("E0001", "E0002", "E0003")
        }

    assert ages == {"E0001": 35, "E0002": 36, "E0003": None}


def test_identifier_of_a_type_outside_the_catalog_keeps_its_raw_label(
    client: TestClient, session_factory: sessionmaker[Session], seeded: None
) -> None:
    with session_factory() as session:
        employee = _employee(session)
        session.add(EmployeeIdentifier(employee_id=employee.id, kind="old_permit", value="X1"))
        session.commit()

    assert _fields(client.get("/employees/E0001").text)["Belge numaraları"] == "old_permit X1"


def test_names_read_from_documents_are_escaped(
    client: TestClient, session_factory: sessionmaker[Session], seeded: None
) -> None:
    with session_factory() as session:
        _employee(session, given_names="<script>alert(1)</script>", surname="O'Neil & Co")
        session.commit()

    page = client.get("/employees/E0001").text

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "O&#39;Neil &amp; Co" in page


def test_latin_name_and_original_spelling_are_shown_apart(
    client: TestClient, session_factory: sessionmaker[Session], seeded: None
) -> None:
    # 05.2.2: ad ve soyad Latin, Latin olmayan yazım "Orijinal yazım"da; uyarı yok.
    with session_factory() as session:
        _employee(
            session,
            given_names="Đorđe",
            surname="Živković",
            original_script_name="Ђорђе Живковић",
        )
        session.commit()

    page = client.get("/employees/E0001").text
    fields = _fields(page)

    assert (fields["Ad"], fields["Soyad"], fields["Orijinal yazım"]) == (
        "Đorđe",
        "Živković",
        "Ђорђе Живковић",
    )
    assert "<h1>Đorđe Živković</h1>" in page
    assert "Latin yazım eksik" not in page


@pytest.mark.parametrize(
    "names",
    [
        {"given_names": "محمد", "surname": "علي"},
        {"given_names": "Test", "surname": "ОРНЕКОВА"},
        {"other_names": "ИВАНОВИЧ"},
    ],
    ids=["arabic", "cyrillic-surname", "cyrillic-other-names"],
)
def test_card_flags_a_latin_field_that_still_carries_another_script(
    client: TestClient,
    session_factory: sessionmaker[Session],
    seeded: None,
    names: dict[str, str],
) -> None:
    # Onarımın Latin yazım bulamadığı eski kayıt (05.2.2): alan olduğu gibi, kart uyarır.
    with session_factory() as session:
        employee = _employee(session)
        for name, value in names.items():
            setattr(employee, name, value)
        session.commit()

    page = client.get("/employees/E0001").text

    assert '<span class="badge badge-missing">Latin yazım eksik</span>' in page


# --- 05.7.3: alanın kaynağı ve farklı değer uyarısı ----------------------------------------------


def _source(session: Session, upload_id: str = "u_20260915_0001") -> UploadFile:
    upload = session.get(Upload, upload_id) or Upload(id=upload_id, channel="web")
    upload_file = UploadFile(
        upload=upload,
        original_name="tarama.pdf",
        stored_path=f"Inbox/{upload_id}/tarama.pdf",
        sha256="0" * 64,
        mime="application/pdf",
    )
    session.add(upload_file)
    session.flush()
    return upload_file


def _sourced_document(
    session: Session,
    layout: DataLayout,
    employee: Employee,
    source: UploadFile,
    file_name: str,
    *,
    content: bytes | None = b"%PDF-1.4 sentetik",
    status: str = ACTIVE,
    created_at: datetime | None = None,
) -> Document:
    document = _document(
        session,
        layout,
        employee,
        PASSPORT,
        file_name,
        content,
        status=status,
        created_at=created_at,
    )
    document.source_refs_json = [{"file_id": source.id, "pages": [0, 1]}]
    session.flush()
    return document


def _observe(
    session: Session, field: str, outcome: FieldOutcome, source: UploadFile, page: int = 0
) -> None:
    session.add(
        EmployeeFieldObservation(
            employee_id="E0001",
            field=field,
            outcome=outcome.value,
            file_id=source.id,
            page_index=page,
        )
    )
    session.flush()


def _field_html(page: str, label: str) -> str:
    card = page.split('<dl class="profile-fields">', 1)[1].split("</dl>", 1)[0]
    match = re.search(rf"<dt>{label}</dt>\s*<dd>(.*?)</dd>", card, re.S)
    assert match is not None
    return match.group(1)


def test_each_field_links_to_the_document_it_was_filled_from(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    with session_factory() as session:
        employee = _employee(session, nationality="RUS", date_of_birth=date(1990, 1, 1))
        first, second = _source(session), _source(session)
        filled_from = _sourced_document(session, layout, employee, first, "Pasaport.pdf")
        confirmed_by = _sourced_document(session, layout, employee, second, "Kart.pdf")
        # Doğum tarihi ilk belgeden doldu; ikinci belge aynısını okudu. Uyruğu dolduran yok:
        # aynı değeri okuyan ilk belge kaynaktır.
        _observe(session, "date_of_birth", FieldOutcome.FILLED, first)
        _observe(session, "date_of_birth", FieldOutcome.SAME, second)
        _observe(session, "nationality", FieldOutcome.SAME, second)
        session.commit()
        ids = (filled_from.id, confirmed_by.id)

    page = client.get("/employees/E0001").text

    link = '<a href="/employees/E0001/documents/{}/file" target="_blank" rel="noopener">{}</a>'
    assert "Kaynak: " + link.format(ids[0], "Pasaport.pdf") in _field_html(page, "Doğum tarihi")
    assert "Kaynak: " + link.format(ids[1], "Kart.pdf") in _field_html(page, "Vatandaşlık")
    fields = _fields(page)
    assert fields["Doğum tarihi"] == "01.01.1990 Kaynak: Pasaport.pdf"
    assert fields["Vatandaşlık"] == "RUS Kaynak: Kart.pdf"
    # Gözlemi olmayan alanın kaynağı yoktur; uyarı da yoktur.
    assert (fields["Ad"], fields["Soyad"]) == ("Dmitry", "Vasiliev")
    assert "belgede farklı değer okundu" not in page


def test_a_different_value_read_in_a_document_is_warned_and_the_field_stays(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    with session_factory() as session:
        employee = _employee(session, date_of_birth=date(1990, 1, 1))
        first, second, third = _source(session), _source(session), _source(session)
        _sourced_document(session, layout, employee, first, "Pasaport.pdf")
        second_document = _sourced_document(session, layout, employee, second, "Kart.pdf")
        third_document = _sourced_document(session, layout, employee, third, "Izin.pdf")
        _observe(session, "date_of_birth", FieldOutcome.FILLED, first)
        _observe(session, "date_of_birth", FieldOutcome.CONFLICT, second)
        _observe(session, "date_of_birth", FieldOutcome.CONFLICT, third)
        _observe(session, "surname", FieldOutcome.CONFLICT, third)
        session.commit()
        ids = (second_document.id, third_document.id)

    page = client.get("/employees/E0001").text

    birth = _field_html(page, "Doğum tarihi")
    assert birth.startswith("01.01.1990")
    assert '<span class="badge badge-missing">Farklı değer</span>' in birth
    assert "Doğum tarihi: belgede farklı değer okundu: " in birth
    for document_id in ids:
        assert f'href="/employees/E0001/documents/{document_id}/file"' in birth
    surname = _field_html(page, "Soyad")
    assert surname.startswith("Vasiliev")
    assert "Soyad: belgede farklı değer okundu: " in surname
    assert "Kaynak:" not in surname  # soyadı belgeden dolmadı, aynısını okuyan da yok
    assert _fields(page)["Soyad"] == (
        "Vasiliev Farklı değer Soyad: belgede farklı değer okundu: Izin.pdf"
    )


def test_the_source_prefers_the_active_output_and_falls_back_to_history_or_the_upload(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    # Aynı kaynaktan yeniden analizle iki çıktı (K18): etkin olan. Dosyası kaybolmuş çıktı: geçmişi.
    # Çıktısı bu çalışanda olmayan kaynak (henüz yürütülmedi, başka çalışana taşındı): parti.
    with session_factory() as session:
        employee = _employee(session, nationality="RUS", date_of_birth=date(1990, 1, 1))
        reanalyzed, lost = _source(session), _source(session)
        pending = _source(session, "u_20260916_0002")
        _sourced_document(
            session,
            layout,
            employee,
            reanalyzed,
            "Eski.pdf",
            status=SUPERSEDED,
            created_at=datetime(2026, 9, 15, tzinfo=UTC),
        )
        current = _sourced_document(
            session,
            layout,
            employee,
            reanalyzed,
            "Yeni.pdf",
            created_at=datetime(2026, 9, 16, tzinfo=UTC),
        )
        # Daha yeni ama etkin olmayan çıktı (arşivlenmiş) etkin olanın önüne geçmez.
        _sourced_document(
            session,
            layout,
            employee,
            reanalyzed,
            "Arsiv.pdf",
            status=ARCHIVED,
            created_at=datetime(2026, 9, 17, tzinfo=UTC),
        )
        gone = _sourced_document(session, layout, employee, lost, "Kayip.pdf", content=None)
        _observe(session, "date_of_birth", FieldOutcome.FILLED, reanalyzed)
        _observe(session, "nationality", FieldOutcome.FILLED, lost)
        _observe(session, "other_names", FieldOutcome.CONFLICT, pending)
        # Kökenin ilk sayfası değil: bu gözlemin çıktısı bulunmaz, parti sayfasına gider.
        _observe(session, "original_script_name", FieldOutcome.CONFLICT, reanalyzed, page=1)
        session.commit()
        current_id, gone_id = current.id, gone.id

    page = client.get("/employees/E0001").text

    birth = _field_html(page, "Doğum tarihi")
    assert f'href="/employees/E0001/documents/{current_id}/file"' in birth
    assert "Eski.pdf" not in birth and "Arsiv.pdf" not in birth
    nationality = _field_html(page, "Vatandaşlık")
    assert f'Kaynak: <a href="/documents/{gone_id}/history">Kayip.pdf</a>' in nationality
    other_names = _field_html(page, "Diğer isimler")
    assert '<a href="/uploads/u_20260916_0002">Parti u_20260916_0002</a>' in other_names
    original = _field_html(page, "Orijinal yazım")
    assert '<a href="/uploads/u_20260915_0001">Parti u_20260915_0001</a>' in original


@pytest.mark.parametrize(
    "source_refs",
    [
        {"file_id": 1, "pages": [0]},
        [],
        ["x"],
        [{"pages": [0]}],
        [{"file_id": 1, "pages": []}],
        [{"file_id": 1, "pages": ["0"]}],
    ],
    ids=["not-a-list", "empty", "not-a-mapping", "no-file", "no-pages", "page-not-a-number"],
)
def test_an_output_with_a_corrupt_origin_is_not_taken_as_the_source(
    layout: DataLayout, session_factory: sessionmaker[Session], source_refs: object
) -> None:
    with session_factory() as session:
        _catalog(session)
        employee = _employee(session, date_of_birth=date(1990, 1, 1))
        source = _source(session)
        document = _sourced_document(session, layout, employee, source, "Pasaport.pdf")
        document.source_refs_json = source_refs
        _observe(session, "date_of_birth", FieldOutcome.FILLED, source)
        session.commit()

        profile = build_profile(session, layout, "E0001")

    assert profile is not None
    link = profile.field_sources["date_of_birth"].source
    assert link is not None
    assert (link.label, link.url) == ("Parti u_20260915_0001", "/uploads/u_20260915_0001")


def test_field_sources_carry_no_value_of_their_own(
    layout: DataLayout, session_factory: sessionmaker[Session]
) -> None:
    # Kart alanın değerini zaten gösterir; kaynak ve uyarı yalnız belge adı ve bağlantıdır.
    with session_factory() as session:
        _catalog(session)
        employee = _employee(session, date_of_birth=date(1990, 1, 1))
        source = _source(session)
        _sourced_document(session, layout, employee, source, "Pasaport.pdf")
        _observe(session, "date_of_birth", FieldOutcome.CONFLICT, source)
        session.commit()

        profile = build_profile(session, layout, "E0001")

    assert profile is not None
    assert set(profile.field_sources) == {"date_of_birth"}
    sources = profile.field_sources["date_of_birth"]
    assert sources.source is None
    assert [link.label for link in sources.conflicts] == ["Pasaport.pdf"]
    assert sources.warning == "Doğum tarihi: belgede farklı değer okundu"


def test_unknown_employee_is_a_404_page_with_a_way_back(client: TestClient) -> None:
    response = client.get("/employees/E9999")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "Çalışan bulunamadı." in response.text
    assert 'href="/employees"' in response.text


def test_employee_list_links_number_and_name_to_the_profile(
    client: TestClient, session_factory: sessionmaker[Session], seeded: None
) -> None:
    with session_factory() as session:
        _employee(session)
        session.commit()

    listing = client.get("/employees").text

    assert listing.count('href="/employees/E0001"') == 2
    assert client.get("/employees/E0001").status_code == 200


# --- 10.5.4: profil fotoğrafı ve yokluğu --------------------------------------------------------


def test_card_shows_the_profile_picture_document(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    portrait = make_portrait_image_bytes()
    with session_factory() as session:
        employee = _employee(session)
        _document(session, layout, employee, PHOTO, "Dmitry_Vasiliev-Profile-Picture.jpg", portrait)
        session.commit()

    page = client.get("/employees/E0001").text
    photo = client.get("/employees/E0001/photo")

    assert '<img src="/employees/E0001/photo"' in page
    assert "Eksik belge" not in page
    assert "Fotoğraf yok" not in page
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/jpeg"
    assert photo.headers["x-content-type-options"] == "nosniff"
    assert photo.headers["cache-control"] == "private, no-store"
    assert photo.content == portrait  # sunucu görüntüyü işlemez (K11)


def test_card_without_a_profile_picture_shows_a_placeholder_and_flags_it_missing(
    client: TestClient, session_factory: sessionmaker[Session], seeded: None
) -> None:
    with session_factory() as session:
        _employee(session)
        session.commit()

    page = client.get("/employees/E0001").text
    profile_html = page.split('<section class="profile-card"', 1)[1].split("</section>", 1)[0]

    assert "<img" not in profile_html
    assert "Fotoğraf yok" in profile_html
    assert re.search(r'class="badge badge-missing">Eksik belge</span>\s*Profile Picture', page)
    assert client.get("/employees/E0001/photo").status_code == 404


def test_only_an_active_profile_picture_counts_and_the_newest_one_wins(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    older, newer = make_portrait_image_bytes(size=(120, 160)), make_portrait_image_bytes("PNG")
    with session_factory() as session:
        employee = _employee(session)
        for status, name, content, day in (
            (ARCHIVED, "arsiv.jpg", make_portrait_image_bytes(size=(60, 80)), 1),
            (SUPERSEDED, "eski.jpg", make_portrait_image_bytes(size=(70, 90)), 2),
            (ACTIVE, "ilk.jpg", older, 3),
            (ACTIVE, "yeni.png", newer, 4),
        ):
            _document(
                session,
                layout,
                employee,
                PHOTO,
                name,
                content,
                status=status,
                created_at=datetime(2026, 9, day, tzinfo=UTC),
            )
        session.commit()

    photo = client.get("/employees/E0001/photo")

    assert photo.headers["content-type"] == "image/png"
    assert photo.content == newer
    assert "Eksik belge" not in client.get("/employees/E0001").text


def test_a_profile_picture_that_is_only_superseded_or_archived_is_still_missing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    with session_factory() as session:
        employee = _employee(session)
        _document(
            session,
            layout,
            employee,
            PHOTO,
            "eski.jpg",
            make_portrait_image_bytes(),
            status=SUPERSEDED,
        )
        _document(
            session,
            layout,
            employee,
            PHOTO,
            "arsiv.jpg",
            make_portrait_image_bytes(),
            status=ARCHIVED,
        )
        session.commit()

    page = client.get("/employees/E0001").text

    assert "Eksik belge" in page
    assert "Fotoğraf yok" in page
    assert client.get("/employees/E0001/photo").status_code == 404


def test_a_recorded_photo_that_cannot_be_shown_gets_the_placeholder_not_a_broken_image(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    """Belge kaydı var ama dosya diskte yok (ya da görüntü değil): kırık `<img>` çizilmez."""
    with session_factory() as session:
        gone = _employee(session, 1)
        _document(session, layout, gone, PHOTO, "yok.jpg", None)
        as_pdf = _employee(session, 2, "Anna", "Zeta")
        _document(session, layout, as_pdf, PHOTO, "foto.pdf", make_pdf_bytes())
        session.commit()

    for employee_id in ("E0001", "E0002"):
        page = client.get(f"/employees/{employee_id}").text
        assert "<img" not in page
        assert "Fotoğraf yok" in page
        assert client.get(f"/employees/{employee_id}/photo").status_code == 404


# --- 10.5.2: belge listesi, açma, indirme --------------------------------------------------------


def test_document_list_shows_every_status_with_open_and_download_links(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    with session_factory() as session:
        employee = _employee(session)
        other = _employee(session, 2, "Anna", "Zeta")
        active = _document(
            session, layout, employee, PASSPORT, "Dmitry_Vasiliev-Pasaport.pdf", make_pdf_bytes()
        )
        old = _document(
            session,
            layout,
            employee,
            PASSPORT,
            "Dmitry_Vasiliev-Pasaport-old.pdf",
            make_pdf_bytes(2),
            status=SUPERSEDED,
        )
        archived = _document(
            session,
            layout,
            employee,
            ATTACHMENT,
            "Dmitry_Vasiliev-CV.docx",
            make_docx_bytes(),
            status=ARCHIVED,
        )
        _document(session, layout, other, PASSPORT, "Anna_Zeta-Pasaport.pdf", make_pdf_bytes())
        session.commit()
        ids = (active.id, old.id, archived.id)

    page = client.get("/employees/E0001").text
    section = page.split('<section class="profile-documents">', 1)[1].split("</section>", 1)[0]
    rows = [
        [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell)).strip() for cell in cells]
        for cells in (
            re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", section.split("<tbody>")[1], re.S)
        )
    ]

    assert '<span class="count">3</span>' in section
    assert sorted(row[:4] for row in rows) == sorted(
        [
            ["Rus Pasaportu", "Dmitry_Vasiliev-Pasaport.pdf", "pdf", "Etkin"],
            ["Rus Pasaportu", "Dmitry_Vasiliev-Pasaport-old.pdf", "pdf", "Eski sürüm"],
            ["Ek Dosya", "Dmitry_Vasiliev-CV.docx", "docx", "Arşivlendi"],
        ]
    )
    assert "Anna_Zeta" not in section
    for document_id in ids:
        # Belgeye tıklamak yeni sekmede açar; ayrıca indirme bağlantısı var.
        assert re.search(
            rf'<a href="/employees/E0001/documents/{document_id}/file" target="_blank" '
            rf'rel="noopener">',
            section,
        )
        assert f'<a href="/employees/E0001/documents/{document_id}/download">İndir</a>' in section
    assert section.count("output-superseded") == 2  # eski sürüm ve arşivlenmiş sönük çizilir


def test_document_whose_file_is_gone_is_listed_without_links(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    with session_factory() as session:
        employee = _employee(session)
        document = _document(session, layout, employee, PASSPORT, "kayip.pdf", None)
        session.commit()
        document_id = document.id

    section = client.get("/employees/E0001").text.split('<section class="profile-documents">')[1]

    assert "kayip.pdf" in section
    assert "Dosya bulunamadı" in section
    assert f"/documents/{document_id}/file" not in section
    assert f"/documents/{document_id}/download" not in section
    # Geçmiş (10.6.1) dosyaya bağlı değildir: dosyası kaybolan belgenin de kökeni izlenir.
    assert f'<a href="/documents/{document_id}/history">Geçmiş</a>' in section
    assert client.get(f"/employees/E0001/documents/{document_id}/file").status_code == 404


def test_employee_without_documents_says_so(
    client: TestClient, session_factory: sessionmaker[Session], seeded: None
) -> None:
    with session_factory() as session:
        _employee(session)
        session.commit()

    page = client.get("/employees/E0001").text

    assert "Henüz belge yok." in page
    assert '<span class="count">0</span>' in page


def test_open_serves_the_stored_bytes_inline_and_download_as_an_attachment(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    content = make_pdf_bytes(3)
    with session_factory() as session:
        employee = _employee(session)
        document = _document(
            session, layout, employee, PASSPORT, "Dmitry_Vasiliev-Pasaport.pdf", content
        )
        session.commit()
        base = f"/employees/E0001/documents/{document.id}"

    opened = client.get(f"{base}/file")
    downloaded = client.get(f"{base}/download")

    assert opened.status_code == downloaded.status_code == 200
    assert opened.headers["content-type"] == downloaded.headers["content-type"] == "application/pdf"
    assert opened.headers["content-disposition"].startswith("inline")
    assert downloaded.headers["content-disposition"].startswith("attachment")
    for response in (opened, downloaded):
        assert 'filename="Dmitry_Vasiliev-Pasaport.pdf"' in response.headers["content-disposition"]
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "private, no-store"
        assert response.content == content  # bayt bayt aynı dosya (K10, K17)


def test_word_attachment_is_always_delivered_as_a_download(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    content = make_docx_bytes()
    with session_factory() as session:
        employee = _employee(session)
        document = _document(
            session, layout, employee, ATTACHMENT, "Dmitry_Vasiliev-CV.docx", content
        )
        session.commit()

    opened = client.get(f"/employees/E0001/documents/{document.id}/file")

    assert opened.status_code == 200
    assert opened.headers["content-type"] == "application/octet-stream"
    assert opened.headers["content-disposition"].startswith("attachment")
    assert opened.content == content


def test_non_ascii_file_name_is_sent_in_the_extended_header_form(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    with session_factory() as session:
        employee = _employee(session)
        document = _document(
            session, layout, employee, PASSPORT, "Şükrü_Öztürk-Pasaport.pdf", make_pdf_bytes()
        )
        session.commit()

    response = client.get(f"/employees/E0001/documents/{document.id}/download")

    assert response.status_code == 200
    assert (
        f"filename*=utf-8''{quote('Şükrü_Öztürk-Pasaport.pdf')}"
        in response.headers["content-disposition"]
    )


def test_a_document_is_only_reachable_through_its_own_employee(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    with session_factory() as session:
        owner = _employee(session)
        _employee(session, 2, "Anna", "Zeta")
        document = _document(session, layout, owner, PASSPORT, "Pasaport.pdf", make_pdf_bytes())
        session.commit()
        document_id = document.id

    assert client.get(f"/employees/E0001/documents/{document_id}/file").status_code == 200
    for route in ("file", "download"):
        response = client.get(f"/employees/E0002/documents/{document_id}/{route}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Belge bulunamadı."
        assert client.get(f"/employees/E9999/documents/{document_id}/{route}").status_code == 404
        assert client.get(f"/employees/E0001/documents/999/{route}").status_code == 404


@pytest.mark.parametrize(
    "stored_path",
    ["../outside.pdf", "/etc/passwd", "Employees\\x\\Hazir\\y.pdf", "Employees//y.pdf", "C:/x.pdf"],
)
def test_a_stored_path_that_leaves_the_data_directory_is_never_served(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
    tmp_path: Path,
    stored_path: str,
) -> None:
    (layout.root.parent / "outside.pdf").write_bytes(make_pdf_bytes())
    with session_factory() as session:
        employee = _employee(session)
        document = _document(session, layout, employee, PASSPORT, "Pasaport.pdf", make_pdf_bytes())
        document.path = stored_path
        session.commit()
        document_id = document.id

    for route in ("file", "download"):
        response = client.get(f"/employees/E0001/documents/{document_id}/{route}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Belge dosyası bulunamadı."
    assert "Dosya bulunamadı" in client.get("/employees/E0001").text


def test_panel_has_no_way_to_change_a_document(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: None,
) -> None:
    content = make_pdf_bytes()
    with session_factory() as session:
        employee = _employee(session)
        document = _document(session, layout, employee, PASSPORT, "Pasaport.pdf", content)
        session.commit()
        document_id = document.id
        stored = layout.resolve(document.path)

    profile_paths = {
        path: set(operations)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/employees/{employee_id}")
    }
    assert profile_paths == {
        "/employees/{employee_id}": {"get"},
        "/employees/{employee_id}/photo": {"get"},
        "/employees/{employee_id}/documents/{document_id}/file": {"get"},
        "/employees/{employee_id}/documents/{document_id}/download": {"get"},
    }

    urls = (
        "/employees/E0001",
        "/employees/E0001/photo",
        f"/employees/E0001/documents/{document_id}/file",
        f"/employees/E0001/documents/{document_id}/download",
    )
    for url in urls:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert client.request(method, url).status_code == 405, (method, url)
    assert stored.read_bytes() == content


# --- 10.5.3: profil sayfasından yükleme ----------------------------------------------------------


class _Processor:
    def __init__(self) -> None:
        self.upload_ids: list[str] = []

    def __call__(self, upload_id: str) -> None:
        self.upload_ids.append(upload_id)


def test_upload_form_carries_the_profile_employee_as_context(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    seeded: None,
) -> None:
    recorded = _Processor()
    processor: UploadProcessor = recorded
    app.dependency_overrides[get_upload_processor] = lambda: processor
    with session_factory() as session:
        _employee(session, 1)
        _employee(session, 2, "Anna", "Zeta")
        session.commit()

    page = client.get("/employees/E0002").text
    form = page.split('<form id="upload-form"', 1)[1].split("</form>", 1)[0]

    assert 'hx-post="/upload"' in form
    assert 'hx-encoding="multipart/form-data"' in form
    assert re.search(r'<input id="files" name="files" type="file" multiple\b', form)
    assert "<select" not in form  # çalışan seçtirilmez, profilin çalışanı sabittir
    assert 'src="/static/upload.js"' in page
    assert 'id="upload-result"' in page
    context = re.search(r'<input type="hidden" name="context_employee_id" value="([^"]*)"', form)
    assert context is not None and context.group(1) == "E0002"

    # Sayfanın kendi verdiği alanla gönderilen yükleme, o çalışanın bağlamıyla açılır.
    response = client.post(
        "/upload",
        files=[("files", ("cv.pdf", make_pdf_bytes(), "application/octet-stream"))],
        data={"context_employee_id": context.group(1)},
    )

    assert response.status_code == 201
    with session_factory() as session:
        upload = session.scalars(select(Upload)).one()
        assert upload.context_employee_id == "E0002"
    assert recorded.upload_ids == [upload.id]
    assert f"/uploads/{upload.id}" in response.text
