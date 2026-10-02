"""10.5.6 — çalışan profilini düzenleme panelde: form, iki aşamalı onay (§20.6 metinleri birebir,
tek kullanımlık belirteç form değerlerine bağlı), K8 yeniden adlandırma, olaylar ve profil kartı
(K8, K16, K17; kabul senaryosu S16 kalıbı; PLAN.md §C90-a, §D61).

Çalışan ve belgeleri doğrudan yazılır (`tests/fixtures/gen.py` sentetik PDF'leri); gerçek kimlik
belgesi ve ağ çağrısı yoktur. Onay belirteci oturum çerezine bağlıdır; oturum bağımlılığı testte
geçersiz kılındığı için çerez elle konur. Yeniden adlandırmanın ayrıntısı
`tests/matching/test_edit_employee.py`'dedir.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import app.storage.rename as rename_module
import app.web.confirm as confirm
from app.db.models import (
    ConfirmationToken,
    Document,
    DocumentStatus,
    Employee,
    EmployeeFieldObservation,
    Event,
    FieldOutcome,
    KnownDocumentType,
    Upload,
    UploadFile,
    utcnow,
)
from app.events import EventType
from app.matching.match import ProfileFields
from app.storage import DataLayout, sha256_file
from app.web.auth import SESSION_COOKIE
from app.web.confirm import CONFIRMATION_REFUSED, Operation
from app.web.profile_form import BAD_DATE, INVALID_PROFILE
from app.web.routers.employees import NO_FIELD_CHANGES, NOT_EDITABLE, fields_subject
from tests.fixtures.gen import make_pdf_bytes
from tests.web.conftest import SESSION, SIGNED_IN, issue_token

EMPLOYEE_ID = "E0001"
OLD_FOLDER, NEW_FOLDER = "Ivan_Petrov_E0001", "Ivan_Petrova_E0001"
BORN = date(1990, 1, 1)
# §20.6 "Çalışan profilini düzenle" — birebir.
FIRST_TEXT = "Bu çalışanın profil bilgilerini değiştirmek üzeresiniz. Emin misiniz?"
SECOND_TEXT = (
    "Ad ya da soyad değiştiyse klasör ve {n} belge dosyası yeniden adlandırılacaktır. "
    "Son kararınız mı?"
)
CURRENT = {
    "given_names": "Ivan",
    "surname": "Petrov",
    "other_names": "",
    "original_script_name": "Иван Петров",
    "date_of_birth": BORN.isoformat(),
    "nationality": "RUS",
}
RENAMED = CURRENT | {"surname": "Petrova"}


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, SESSION)


@pytest.fixture
def seeded(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, Any]:
    """E0001 Ivan Petrov: iki etkin belge (pasaport, ikamet kartı) ve `profil.md`."""
    with session_factory() as session:
        for slug, name, label in (
            ("ru_passport", "Rus Pasaportu", "Passport"),
            ("residence_card", "İkamet Kartı", "Residence Card"),
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
        session.add(
            Employee(
                id=EMPLOYEE_ID,
                folder_name=OLD_FOLDER,
                given_names="Ivan",
                surname="Petrov",
                original_script_name="Иван Петров",
                date_of_birth=BORN,
                nationality="RUS",
            )
        )
        ready = layout.ensure_employee_tree(OLD_FOLDER) / "Hazir"
        documents = {}
        for slug, name, pages in (
            ("ru_passport", "Ivan_Petrov-Passport.pdf", 1),
            ("residence_card", "Ivan_Petrov-Residence-Card.pdf", 2),
        ):
            (ready / name).write_bytes(make_pdf_bytes(pages))
            document = Document(
                employee_id=EMPLOYEE_ID,
                type_slug=slug,
                path=layout.relative(ready / name),
                format="pdf",
                sequence_no=1,
                source_refs_json=[{"file_id": 3, "pages": [0]}],
                status=DocumentStatus.ACTIVE.value,
            )
            session.add(document)
            session.flush()
            documents[name] = document.id
        session.commit()
    layout.profile_path(OLD_FOLDER).write_text("# Ivan Petrov\n", encoding="utf-8")
    return {"documents": documents, "tree": _tree(layout.root)}


def _tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def _prepare(client: TestClient, values: dict[str, str] = RENAMED) -> Any:
    return client.post(f"/employees/{EMPLOYEE_ID}/fields/prepare", data=values)


def _change(client: TestClient, values: dict[str, str], token: str | None) -> Any:
    data = dict(values)
    if token is not None:
        data["confirmation"] = token
    return client.post(f"/employees/{EMPLOYEE_ID}/fields", data=data, follow_redirects=False)


def _count(session: Session, event_type: EventType) -> int:
    return session.scalar(select(func.count()).where(Event.type == event_type.value)) or 0


def _unchanged(
    session_factory: sessionmaker[Session], layout: DataLayout, seeded: dict[str, Any]
) -> None:
    """Hiçbir şey olmadı: kayıt, dosyalar, olaylar ve gözlemler ilk hâlinde."""
    with session_factory() as session:
        employee = session.get_one(Employee, EMPLOYEE_ID)
        assert (employee.surname, employee.folder_name) == ("Petrov", OLD_FOLDER)
        assert _count(session, EventType.USER_CONFIRMED) == 0
        assert _count(session, EventType.EMPLOYEE_EDITED) == 0
        assert session.scalar(select(func.count()).select_from(EmployeeFieldObservation)) == 0
    assert _tree(layout.root) == seeded["tree"]


def _fields(values: dict[str, str]) -> ProfileFields:
    return ProfileFields(
        given_names=values["given_names"],
        surname=values["surname"],
        other_names=values["other_names"] or None,
        original_script_name=values["original_script_name"] or None,
        date_of_birth=date.fromisoformat(values["date_of_birth"]),
        nationality=values["nationality"] or None,
    )


def _field_html(page: str, label: str) -> str:
    card = page.split('<dl class="profile-fields">', 1)[1].split("</dl>", 1)[0]
    match = re.search(rf"<dt>{label}</dt>\s*<dd>(.*?)</dd>", card, re.S)
    assert match is not None
    return match.group(1)


# --- profil sayfası ve form ---------------------------------------------------------------------


def test_the_profile_links_to_the_edit_form_unless_the_employee_is_merged(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, Any]
) -> None:
    link = f'href="/employees/{EMPLOYEE_ID}/fields"'
    assert link in client.get(f"/employees/{EMPLOYEE_ID}").text
    assert "Profili düzenle" in client.get(f"/employees/{EMPLOYEE_ID}").text

    with session_factory() as session:
        session.get_one(Employee, EMPLOYEE_ID).status = "merged"
        session.commit()

    assert link not in client.get(f"/employees/{EMPLOYEE_ID}").text
    response = client.get(f"/employees/{EMPLOYEE_ID}/fields")
    assert response.status_code == 409
    assert NOT_EDITABLE in response.text
    assert 'name="given_names"' not in response.text


def test_the_form_holds_the_six_fields_with_current_values_and_the_first_text(
    client: TestClient, seeded: dict[str, Any]
) -> None:
    response = client.get(f"/employees/{EMPLOYEE_ID}/fields")

    assert response.status_code == 200
    html = response.text
    assert f'<form method="post" action="/employees/{EMPLOYEE_ID}/fields/prepare"' in html
    # Sayfadaki öbür formlar (üst çubuktaki dil seçici, 10.10.2) bu formun alanı değildir.
    form = re.search(
        rf'<form method="post" action="/employees/{EMPLOYEE_ID}/fields/prepare".*?</form>',
        html,
        re.DOTALL,
    )
    assert form is not None
    names = re.findall(r'<input[^>]*name="([^"]+)"', form.group(0))
    assert names == list(CURRENT)  # başka alan yok: belge içeriği bu formla gönderilemez (K17)
    for name, value in CURRENT.items():
        assert re.search(rf'name="{name}"\s+value="{re.escape(value)}"', html), name
    assert FIRST_TEXT in html
    assert "<textarea" not in html


def test_an_unknown_employee_has_no_form(client: TestClient, seeded: dict[str, Any]) -> None:
    response = client.get("/employees/E9999/fields")

    assert response.status_code == 404
    assert 'name="given_names"' not in response.text
    assert _prepare_status(client, "/employees/E9999/fields/prepare") == 404


def _prepare_status(client: TestClient, url: str) -> int:
    return client.post(url, data=RENAMED).status_code


# --- hazırlık: ikinci metin ve belirteç, değişiklik yok ------------------------------------------


def test_prepare_shows_the_changes_and_the_second_text_and_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    response = _prepare(client)

    assert response.status_code == 200, response.text
    html = response.text
    assert SECOND_TEXT.format(n=2) in html
    assert f'<form method="post" action="/employees/{EMPLOYEE_ID}/fields"' in html
    changed = re.findall(r'<tr class="changed">\s*<th scope="row">([^<]+)</th>', html)
    assert changed == ["Soyad"]
    assert "Petrova" in html and "Petrov" in html
    for name, value in RENAMED.items():
        assert f'<input type="hidden" name="{name}" value="{value}">' in html
    token = _token(html)
    _unchanged(session_factory, layout, seeded)
    with session_factory() as session:
        row = session.scalars(select(ConfirmationToken)).one()
        assert (row.operation, row.target, row.username) == (
            Operation.EDIT_EMPLOYEE.value,
            fields_subject(EMPLOYEE_ID, _fields(RENAMED)),
            SIGNED_IN.username,
        )
        assert token not in row.target and "Petrova" not in row.target


def test_prepare_without_a_session_cookie_issues_no_token(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    client.cookies.clear()

    response = _prepare(client)

    assert response.status_code == 400
    assert "Oturum çerezi yok" in response.text
    _unchanged(session_factory, layout, seeded)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ConfirmationToken)) == 0


def test_prepare_counts_no_file_when_the_name_stays(
    client: TestClient, seeded: dict[str, Any]
) -> None:
    response = _prepare(client, CURRENT | {"date_of_birth": "1991-02-03", "nationality": "kaz"})

    assert response.status_code == 200
    assert SECOND_TEXT.format(n=0) in response.text
    assert '<input type="hidden" name="nationality" value="KAZ">' in response.text


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"given_names": "Иван"}, "Ad: Latin harfleriyle yazılmalı"),
        ({"surname": ""}, "Soyad: boş olamaz"),
        ({"date_of_birth": "1990-13-01"}, f"Doğum tarihi: {BAD_DATE}"),
        ({"nationality": "RUSS"}, "Vatandaşlık: ICAO uyruk kodu olmalı"),
    ],
)
def test_invalid_fields_are_refused_with_the_form_errors(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
    changes: dict[str, str],
    message: str,
) -> None:
    values = CURRENT | changes
    for response in (_prepare(client, values), _change(client, values, "belirtec")):
        assert response.status_code == 422
        assert INVALID_PROFILE in response.text
        assert message in response.text
        # Form girilen değerlerle yeniden çizilir.
        assert f'action="/employees/{EMPLOYEE_ID}/fields/prepare"' in response.text
    _unchanged(session_factory, layout, seeded)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ConfirmationToken)) == 0


def test_an_unchanged_form_is_refused(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    response = _prepare(client, CURRENT)

    assert response.status_code == 422
    assert NO_FIELD_CHANGES in response.text
    _unchanged(session_factory, layout, seeded)


# --- S16 kalıbı: tek onay değiştirmez, belirteç değiştirir --------------------------------------


def test_the_first_confirmation_alone_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    _prepare(client)
    response = _change(client, RENAMED, None)

    assert response.status_code == 400
    assert CONFIRMATION_REFUSED in response.text
    assert f'href="/employees/{EMPLOYEE_ID}/fields"' in response.text
    _unchanged(session_factory, layout, seeded)


def test_the_token_changes_the_fields_renames_the_files_and_logs_both_events(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    token = _token(_prepare(client).text)

    response = _change(client, RENAMED, token)

    assert response.status_code == 303, response.text
    assert response.headers["location"] == f"/employees/{EMPLOYEE_ID}?notice=fields_renamed"
    page = client.get(response.headers["location"]).text
    assert "klasör ve belge dosyaları yeni adla yeniden adlandırıldı" in page
    with session_factory() as session:
        employee = session.get_one(Employee, EMPLOYEE_ID)
        assert (employee.id, employee.surname, employee.folder_name) == (
            EMPLOYEE_ID,
            "Petrova",
            NEW_FOLDER,
        )
        paths = sorted(document.path for document in session.scalars(select(Document)))
        assert paths == [
            f"Employees/{NEW_FOLDER}/Hazir/Ivan_Petrova-Passport.pdf",
            f"Employees/{NEW_FOLDER}/Hazir/Ivan_Petrova-Residence-Card.pdf",
        ]
        confirmed, edited = session.scalars(
            select(Event)
            .where(
                Event.type.in_([EventType.USER_CONFIRMED.value, EventType.EMPLOYEE_EDITED.value])
            )
            .order_by(Event.id)
        ).all()
        assert (confirmed.type, confirmed.actor, confirmed.employee_id) == (
            EventType.USER_CONFIRMED.value,
            SIGNED_IN.username,
            EMPLOYEE_ID,
        )
        assert confirmed.data_json["operation"] == "edit_employee"
        assert confirmed.data_json["target"] == {"employee_id": EMPLOYEE_ID}
        first = datetime.fromisoformat(confirmed.data_json["first_confirmed_at"])
        assert first <= datetime.fromisoformat(confirmed.data_json["second_confirmed_at"])
        assert (edited.type, edited.actor, edited.employee_id) == (
            EventType.EMPLOYEE_EDITED.value,
            SIGNED_IN.username,
            EMPLOYEE_ID,
        )
        assert edited.data_json == {
            "fields": ["surname"],
            "renamed": True,
            "documents": sorted(seeded["documents"].values()),
        }
        logged = json.dumps([confirmed.data_json, edited.data_json], ensure_ascii=False)
        assert "Petrov" not in logged and "Ivan" not in logged
    # İçerik bayt bayt aynı; eski klasör kalmadı; profil.md yeni adla yeniden üretildi (09.1.1).
    tree = _tree(layout.root)
    assert (
        tree[f"Employees/{NEW_FOLDER}/Hazir/Ivan_Petrova-Passport.pdf"]
        == (seeded["tree"][f"Employees/{OLD_FOLDER}/Hazir/Ivan_Petrov-Passport.pdf"])
    )
    assert not layout.employee_dir(OLD_FOLDER).exists()
    profile = layout.profile_path(NEW_FOLDER).read_text(encoding="utf-8")
    assert "Petrova" in profile and "Ivan_Petrova-Passport.pdf" in profile


def test_a_field_only_change_keeps_the_folder_and_says_so(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    values = CURRENT | {"nationality": "KAZ"}
    response = _change(client, values, _token(_prepare(client, values).text))

    assert response.headers["location"] == f"/employees/{EMPLOYEE_ID}?notice=fields_changed"
    assert "Profil bilgileri değiştirildi." in client.get(response.headers["location"]).text
    with session_factory() as session:
        employee = session.get_one(Employee, EMPLOYEE_ID)
        assert (employee.nationality, employee.folder_name) == ("KAZ", OLD_FOLDER)
    assert layout.profile_path(OLD_FOLDER).read_text(encoding="utf-8") != "# Ivan Petrov\n"


def test_a_token_is_bound_to_the_prepared_values(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    token = _token(_prepare(client).text)

    response = _change(client, RENAMED | {"surname": "Petrovna"}, token)

    assert response.status_code == 400
    _unchanged(session_factory, layout, seeded)
    # Reddedilen deneme belirteci tüketmez: hazırlanan değerlerle geçer.
    assert _change(client, RENAMED, token).status_code == 303


def test_a_used_expired_or_foreign_token_is_refused(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject = fields_subject(EMPLOYEE_ID, _fields(RENAMED))
    foreign = issue_token(session_factory, Operation.MOVE, subject)
    other_session = issue_token(session_factory, Operation.EDIT_EMPLOYEE, subject, cookie="iki")
    other_employee = issue_token(
        session_factory, Operation.EDIT_EMPLOYEE, fields_subject("E0002", _fields(RENAMED))
    )
    for token in (foreign, other_session, other_employee, "uydurma"):
        assert _change(client, RENAMED, token).status_code == 400
    token = _token(_prepare(client).text)
    with session_factory() as session:
        issued = (
            session.scalars(select(ConfirmationToken).where(ConfirmationToken.target == subject))
            .all()[-1]
            .created_at
        )
    monkeypatch.setattr(confirm, "utcnow", lambda: issued + timedelta(minutes=10, seconds=1))
    assert _change(client, RENAMED, token).status_code == 400
    _unchanged(session_factory, layout, seeded)
    monkeypatch.setattr(confirm, "utcnow", utcnow)

    assert _change(client, RENAMED, token).status_code == 303
    again = _change(client, RENAMED, token)
    assert again.status_code == 400
    assert CONFIRMATION_REFUSED in again.text


def test_an_interrupted_rename_is_a_conflict_and_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _token(_prepare(client).text)
    real_rename = rename_module._rename
    calls: list[Path] = []

    def failing_rename(source: Path, target: Path) -> None:
        calls.append(source)
        if len(calls) == 2:
            raise PermissionError("açık dosya")
        real_rename(source, target)

    monkeypatch.setattr(rename_module, "_rename", failing_rename)

    response = _change(client, RENAMED, token)

    assert response.status_code == 409
    assert "geri alındı" in response.text
    _unchanged(session_factory, layout, seeded)
    monkeypatch.setattr(rename_module, "_rename", real_rename)
    # Belirteç tüketilmedi: aynı onaylanmış işlem yeniden denenebilir.
    assert _change(client, RENAMED, token).status_code == 303


# --- kart: elle kaynağı ve 05.7.3 çakışması -------------------------------------------------------


def _observe(session: Session, field: str, outcome: FieldOutcome, file_id: int) -> None:
    session.add(
        EmployeeFieldObservation(
            employee_id=EMPLOYEE_ID,
            field=field,
            outcome=outcome.value,
            file_id=file_id,
            page_index=0,
        )
    )
    session.commit()


def _upload_file(session: Session, name: str) -> int:
    upload = session.get(Upload, "u_1") or Upload(id="u_1", channel="web")
    upload_file = UploadFile(
        upload=upload,
        original_name=name,
        stored_path=f"Inbox/u_1/{name}",
        sha256="0" * 64,
        mime="application/pdf",
    )
    session.add(upload_file)
    session.flush()
    return upload_file.id


def test_the_card_names_the_manual_source_and_drops_older_conflicts(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, Any]
) -> None:
    with session_factory() as session:
        earlier, later = _upload_file(session, "eski.pdf"), _upload_file(session, "yeni.pdf")
        _observe(session, "nationality", FieldOutcome.CONFLICT, earlier)
    assert "Farklı değer" in _field_html(
        client.get(f"/employees/{EMPLOYEE_ID}").text, "Vatandaşlık"
    )

    values = CURRENT | {"nationality": "KAZ"}
    _change(client, values, _token(_prepare(client, values).text))

    # Panel zamanları UTC yazar (PLAN §C73); yerel tarih gece yarısından sonra bir gün ileride olur.
    today = datetime.now(UTC).strftime("%d.%m.%Y")
    field = _field_html(client.get(f"/employees/{EMPLOYEE_ID}").text, "Vatandaşlık")
    assert f"Kaynak: elle ({SIGNED_IN.username}, {today})" in field
    assert "Farklı değer" not in field  # önceki çakışma eski değerle karşılaştırılmıştı

    # Düzenlemeden sonra farklı okuyan belge uyarı olur; alan değişmez (05.7.3).
    with session_factory() as session:
        _observe(session, "nationality", FieldOutcome.CONFLICT, later)
    field = _field_html(client.get(f"/employees/{EMPLOYEE_ID}").text, "Vatandaşlık")
    assert "KAZ" in field
    assert "Vatandaşlık: belgede farklı değer okundu" in field
    assert "Parti u_1" in field
