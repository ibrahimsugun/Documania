"""10.5.9 — iki çalışanı birleştirme panelde: arama (birleştirilmiş kayıt ve kaydın kendisi hariç),
iki kaydın özeti ve kalan seçimi, iki aşamalı onay (§20.6 metinleri birebir, tek kullanımlık
belirteç `kalan:birleşen` çiftine bağlı, ikinci metin "geri alınamaz" der), olaylar kullanıcı
adıyla, birleştirilmiş profilin bildirimi ve kapalı işlemleri; bağlam yüklemesi, atama ve bot
araması birleştirilmiş kaydı reddeder (K16, R11; kabul senaryosu S16 kalıbı; PLAN.md §C90-d, §D61,
§D69).

Çalışanlar ve belgeleri doğrudan yazılır (`tests/fixtures/gen.py` sentetik PDF'leri); gerçek kimlik
belgesi ve ağ çağrısı yoktur. Onay belirteci oturum çerezine bağlıdır; oturum bağımlılığı testte
geçersiz kılındığı için çerez elle konur. Çekirdek `tests/matching/test_merge.py`'dedir.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import app.storage.merge as merge_module
import app.web.confirm as confirm
from app.db.models import (
    ConfirmationToken,
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    EmployeeIdentifier,
    EmployeeStatus,
    Event,
    KnownDocumentType,
    QueueItem,
    Upload,
    utcnow,
)
from app.events import EventType
from app.pipeline.route import QueueAssignmentError, assign_queue_item
from app.storage import DataLayout, sha256_file
from app.telegram.intent import find_employees, parse_person
from app.web.auth import SESSION_COOKIE
from app.web.confirm import CONFIRMATION_REFUSED, Operation
from app.web.routers.employees import (
    EMPLOYEE_NOT_FOUND,
    MERGE_BAD_KEEP,
    MERGE_CLOSED,
    MERGE_FILES_FAILED,
    MERGE_OTHER_CLOSED,
    MERGE_OTHER_NOT_FOUND,
    MERGE_SAME,
    merge_subject,
)
from app.web.routers.queue import ASSIGNEE_MERGED, _assignee
from app.web.routers.uploads import MERGED_CONTEXT_MESSAGE
from tests.fixtures.gen import make_pdf_bytes
from tests.web.conftest import SESSION, SIGNED_IN, issue_token

KEEP, MERGE, INACTIVE, CLOSED = "E0001", "E0005", "E0007", "E0009"
KEEP_FOLDER, MERGE_FOLDER = "Ivan_Petrov_E0001", "Ivan_Petrow_E0005"
CYRILLIC = "Иван Петров"
# §20.6 "İki çalışanı birleştir" — birebir; yer tutucular kayıtların adıyla dolar.
FIRST = "Ivan Petrow kaydını Ivan Petrov kaydıyla birleştirmek üzeresiniz. Emin misiniz?"
FIRST_SWAPPED = "Ivan Petrov kaydını Ivan Petrow kaydıyla birleştirmek üzeresiniz. Emin misiniz?"
SECOND = (
    "2 belge taşınacak ve birleşen kayıt kapanacaktır; bu işlem geri alınamaz. Son kararınız mı?"
)


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, SESSION)


def _employee(session: Session, employee_id: str, surname: str, **fields: Any) -> None:
    session.add(
        Employee(
            id=employee_id,
            folder_name=f"Ivan_{surname}_{employee_id}",
            given_names="Ivan",
            surname=surname,
            date_of_birth=date(1990, 1, 1),
            **fields,
        )
    )
    session.add(
        EmployeeAlias(
            employee_id=employee_id,
            raw_name=f"IVAN {surname.upper()}",
            normalized_name=f"ivan {surname.lower()}",
        )
    )


def _document(
    session: Session, layout: DataLayout, employee_id: str, path: Path, pages: int, status: str
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(make_pdf_bytes(pages))
    session.add(
        Document(
            employee_id=employee_id,
            type_slug="ru_passport",
            path=layout.relative(path),
            format="pdf",
            sequence_no=1,
            source_refs_json=[{"file_id": 3, "pages": [0]}],
            status=status,
        )
    )


@pytest.fixture
def seeded(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, str]:
    """E0001 Ivan Petrov (kalan): etkin pasaport, numara 000000001. E0005 Ivan Petrow (birleşen):
    etkin pasaport, arşivde bir belge, aynı numara, Kiril orijinal yazım, `Alinan/` kopyası. E0007
    pasif, E0009 zaten birleştirilmiş (E0001'e)."""
    with session_factory() as session:
        session.add(
            KnownDocumentType(
                slug="ru_passport",
                name="Rus Pasaportu",
                file_label="Passport",
                sides="single",
                direct=True,
                analyze=True,
                output_format="pdf",
            )
        )
        _employee(session, KEEP, "Petrov", nationality="RUS")
        _employee(session, MERGE, "Petrow", original_script_name=CYRILLIC)
        _employee(session, INACTIVE, "Petrof", status=EmployeeStatus.INACTIVE.value)
        _employee(
            session,
            CLOSED,
            "Petrovv",
            status=EmployeeStatus.MERGED.value,
            merged_into_id=KEEP,
        )
        for employee_id in (KEEP, MERGE):
            session.add(
                EmployeeIdentifier(employee_id=employee_id, kind="ru_passport", value="000000001")
            )
        ready = layout.ensure_employee_tree(KEEP_FOLDER) / "Hazir"
        _document(session, layout, KEEP, ready / "Ivan_Petrov-Passport.pdf", 1, "active")
        merge_dir = layout.ensure_employee_tree(MERGE_FOLDER)
        _document(
            session, layout, MERGE, merge_dir / "Hazir" / "Ivan_Petrow-Passport.pdf", 2, "active"
        )
        _document(
            session,
            layout,
            MERGE,
            layout.archive_dir(date(2026, 9, 1)) / "Ivan_Petrow-Passport-2.pdf",
            3,
            DocumentStatus.ARCHIVED.value,
        )
        (merge_dir / "Alinan" / "tarama.pdf").write_bytes(make_pdf_bytes(4))
        session.commit()
    for folder, name in ((KEEP_FOLDER, "Ivan Petrov"), (MERGE_FOLDER, "Ivan Petrow")):
        layout.profile_path(folder).write_text(f"# {name}\n", encoding="utf-8")
    return _tree(layout.root)


def _tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "profil.md"
    }


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def _prepare(client: TestClient, keep: str = KEEP, other: str = MERGE) -> Any:
    return client.post(f"/employees/{KEEP}/merge/prepare", data={"other": other, "keep": keep})


def _merge(client: TestClient, token: str | None, keep: str = KEEP, other: str = MERGE) -> Any:
    data = {"other": other, "keep": keep}
    if token is not None:
        data["confirmation"] = token
    return client.post(f"/employees/{KEEP}/merge", data=data, follow_redirects=False)


def _events(session_factory: sessionmaker[Session], *types: EventType) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event)
                .where(Event.type.in_([kind.value for kind in types]))
                .order_by(Event.id)
            )
        )


def _unchanged(
    session_factory: sessionmaker[Session], layout: DataLayout, tree: dict[str, str]
) -> None:
    """Hiçbir şey olmadı: iki kayıt etkin, belgeler sahiplerinde, onay ve birleştirme olayı yok,
    dosyalar ilk hâlinde."""
    with session_factory() as session:
        assert session.get_one(Employee, MERGE).status == EmployeeStatus.ACTIVE.value
        assert session.get_one(Employee, MERGE).merged_into_id is None
        owners = session.execute(
            select(Document.employee_id, func.count()).group_by(Document.employee_id)
        ).all()
        assert dict(owners) == {KEEP: 1, MERGE: 2}
    assert _events(session_factory, EventType.USER_CONFIRMED, EventType.EMPLOYEE_MERGED) == []
    assert _tree(layout.root) == tree


# --- profil ve arama -----------------------------------------------------------------------------


def test_the_profile_links_to_the_merge_search_and_the_search_page_finds_the_other_record(
    client: TestClient, seeded: dict[str, str]
) -> None:
    profile = client.get(f"/employees/{KEEP}").text
    assert f'href="/employees/{KEEP}/merge/employees"' in profile
    assert "Başka kayıtla birleştir" in profile

    page = client.get(f"/employees/{KEEP}/merge/employees")
    assert page.status_code == 200
    assert "Aynı kişinin ikinci kaydını arayıp seçin" in page.text
    assert f'hx-get="/employees/{KEEP}/merge/employees"' in page.text
    assert "Birleştirilecek kaydı bulmak için" in page.text

    found = client.get(f"/employees/{KEEP}/merge/employees?q=ivan", headers={"HX-Request": "true"})
    assert found.status_code == 200
    assert found.headers["Vary"] == "HX-Request"
    html = found.text
    assert "<html" not in html and "3 çalışan bulundu" in html
    # Kaydın kendisi seçilemez; pasif çalışan bulunur; birleştirilmiş çalışan bulunmaz.
    assert '<span class="owner">Bu kayıt</span>' in html
    assert f'href="/employees/{KEEP}/merge/confirm?other={MERGE}"' in html
    assert f'href="/employees/{KEEP}/merge/confirm?other={INACTIVE}"' in html
    assert "(pasif)" in html
    assert CLOSED not in html
    # JavaScript kapalıyken aynı adres tam sayfa ve sonuçla gelir.
    full = client.get(f"/employees/{KEEP}/merge/employees?q=petrow").text
    assert "<html" in full and "1 çalışan bulundu" in full


def test_the_search_refuses_an_unknown_or_merged_record(
    client: TestClient, seeded: dict[str, str]
) -> None:
    missing = client.get("/employees/E9999/merge/employees?q=ivan")
    closed = client.get(f"/employees/{CLOSED}/merge/employees?q=ivan")
    closed_fragment = client.get(
        f"/employees/{CLOSED}/merge/employees?q=ivan", headers={"HX-Request": "true"}
    )

    assert (missing.status_code, closed.status_code) == (404, 409)
    assert EMPLOYEE_NOT_FOUND in missing.text and MERGE_CLOSED in closed.text
    assert closed_fragment.status_code == 409 and "<html" not in closed_fragment.text


# --- birinci onay: özet ve kalan seçimi ----------------------------------------------------------


def test_the_first_step_shows_both_records_side_by_side_and_the_first_text(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
) -> None:
    response = client.get(f"/employees/{KEEP}/merge/confirm?other={MERGE}")

    assert response.status_code == 200
    html = response.text
    assert FIRST in html
    assert f"Kalan: Ivan Petrov ({KEEP})" in html and f"Birleşen: Ivan Petrow ({MERGE})" in html
    # Varsayılan kalan profildeki kayıt; radyo seçimi aynı adrese GET ile gider.
    assert f'<input type="radio" name="keep" value="{KEEP}" checked' in html
    assert f'<input type="radio" name="keep" value="{MERGE}" onchange' in html
    assert CYRILLIC in html and "kalanın boş alanı bu değerle dolacak" in html
    assert "farklı — kalanın değeri geçerli kalır" in html
    assert "kalan kayda taşınacak" in html
    assert f'<form method="post" action="/employees/{KEEP}/merge/prepare"' in html
    assert f'<input type="hidden" name="keep" value="{KEEP}">' in html
    _unchanged(session_factory, layout, seeded)


def test_choosing_the_other_record_to_keep_swaps_the_names_in_the_first_text(
    client: TestClient, seeded: dict[str, str]
) -> None:
    html = client.get(f"/employees/{KEEP}/merge/confirm?other={MERGE}&keep={MERGE}").text

    assert FIRST_SWAPPED in html
    assert f"Kalan: Ivan Petrow ({MERGE})" in html
    assert f'<input type="hidden" name="keep" value="{MERGE}">' in html


@pytest.mark.parametrize(
    ("url", "code", "text"),
    [
        (f"/employees/E9999/merge/confirm?other={MERGE}", 404, EMPLOYEE_NOT_FOUND),
        (f"/employees/{KEEP}/merge/confirm?other=E9999", 404, MERGE_OTHER_NOT_FOUND),
        (f"/employees/{KEEP}/merge/confirm?other={KEEP}", 409, MERGE_SAME),
        (f"/employees/{KEEP}/merge/confirm?other={CLOSED}", 409, MERGE_OTHER_CLOSED),
        (f"/employees/{CLOSED}/merge/confirm?other={KEEP}", 409, MERGE_CLOSED),
        (f"/employees/{KEEP}/merge/confirm?other={MERGE}&keep={INACTIVE}", 422, MERGE_BAD_KEEP),
    ],
)
def test_the_first_step_refuses_what_cannot_be_merged(
    client: TestClient, seeded: dict[str, str], url: str, code: int, text: str
) -> None:
    response = client.get(url)

    assert response.status_code == code
    assert text in response.text
    assert "merge/prepare" not in response.text


# --- hazırlık ve birleştirme ---------------------------------------------------------------------


def test_prepare_gives_the_second_text_and_a_token_bound_to_the_pair(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
) -> None:
    response = _prepare(client)

    assert response.status_code == 200, response.text
    html = response.text
    assert SECOND in html
    assert f'<form method="post" action="/employees/{KEEP}/merge"' in html
    token = _token(html)
    with session_factory() as session:
        row = session.scalars(select(ConfirmationToken)).one()
        assert (row.operation, row.target) == ("merge_employees", merge_subject(KEEP, MERGE))
        assert row.token_hash != token
    _unchanged(session_factory, layout, seeded)


def test_prepare_refuses_a_bad_pair_and_issues_no_token(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, str]
) -> None:
    assert _prepare(client, keep=INACTIVE).status_code == 422
    assert _prepare(client, other=CLOSED).status_code == 409
    client.cookies.clear()
    assert _prepare(client).status_code == 400
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ConfirmationToken)) == 0


def test_the_first_confirmation_alone_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
) -> None:
    # S16: birinci onayla gelen (belirteçsiz) istek hiçbir şey değiştirmez.
    _prepare(client)

    response = _merge(client, None)

    assert response.status_code == 400
    assert CONFIRMATION_REFUSED in response.text
    assert f"/employees/{KEEP}/merge/confirm?other={MERGE}&amp;keep={KEEP}" in response.text
    _unchanged(session_factory, layout, seeded)


def test_the_token_is_bound_to_the_keep_choice_the_operation_and_its_lifetime(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _token(_prepare(client).text)
    # Kalan seçimi değişirse belirteç geçmez.
    assert _merge(client, token, keep=MERGE).status_code == 400
    # Başka işlemin belirteci geçmez.
    other = issue_token(session_factory, Operation.MOVE, merge_subject(KEEP, MERGE))
    assert _merge(client, other).status_code == 400
    # Süresi geçmiş belirteç geçmez.
    later = utcnow() + confirm.CONFIRMATION_TTL + timedelta(seconds=1)
    monkeypatch.setattr(confirm, "utcnow", lambda: later)
    assert _merge(client, token).status_code == 400
    _unchanged(session_factory, layout, seeded)


def test_merging_moves_the_documents_logs_both_events_and_renders_both_profiles(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
) -> None:
    token = _token(_prepare(client).text)

    response = _merge(client, token)

    assert response.status_code == 303, response.text
    assert response.headers["location"] == f"/employees/{KEEP}?notice=merged"
    confirmed, merged = _events(
        session_factory, EventType.USER_CONFIRMED, EventType.EMPLOYEE_MERGED
    )
    assert (confirmed.actor, confirmed.employee_id) == (SIGNED_IN.username, KEEP)
    assert confirmed.data_json["operation"] == "merge_employees"
    assert confirmed.data_json["target"] == {"kept": KEEP, "merged": MERGE}
    first = datetime.fromisoformat(confirmed.data_json["first_confirmed_at"])
    assert first <= datetime.fromisoformat(confirmed.data_json["second_confirmed_at"])
    assert confirmed.id < merged.id
    assert (merged.actor, merged.employee_id) == (SIGNED_IN.username, KEEP)
    assert (merged.data_json["kept"], merged.data_json["merged"]) == (KEEP, MERGE)
    with session_factory() as session:
        employee = session.get_one(Employee, MERGE)
        assert (employee.status, employee.merged_into_id) == ("merged", KEEP)
        assert len(merged.data_json["documents"]) == 2
        paths = session.scalars(
            select(Document.path).where(Document.employee_id == KEEP).order_by(Document.id)
        ).all()
    assert paths == [
        f"Employees/{KEEP_FOLDER}/Hazir/Ivan_Petrov-Passport.pdf",
        f"Employees/{KEEP_FOLDER}/Hazir/Ivan_Petrov-Passport-2.pdf",
        "Archive/2026-09/Ivan_Petrow-Passport-2.pdf",
    ]
    assert (layout.received_dir(KEEP_FOLDER) / "tarama.pdf").is_file()
    assert list(layout.ready_dir(MERGE_FOLDER).iterdir()) == []
    # 09.1.1: iki profil de commit edilmiş hâlden üretildi.
    kept_profile = layout.profile_path(KEEP_FOLDER).read_text(encoding="utf-8")
    merged_profile = layout.profile_path(MERGE_FOLDER).read_text(encoding="utf-8")
    assert "Ivan_Petrov-Passport-2.pdf" in kept_profile and CYRILLIC in kept_profile
    assert f"Bu kayıt {KEEP} ile birleştirildi" in merged_profile
    # Aynı belirteçle ikinci istek reddedilir (kayıt artık birleştirilmiş); hiçbir şey değişmez.
    again = _merge(client, token)
    assert again.status_code == 409 and MERGE_OTHER_CLOSED in again.text
    assert len(_events(session_factory, EventType.EMPLOYEE_MERGED)) == 1


def test_the_kept_profile_shows_the_notice_and_the_merge_source_of_a_filled_field(
    client: TestClient, seeded: dict[str, str]
) -> None:
    _merge(client, _token(_prepare(client).text))

    page = client.get(f"/employees/{KEEP}?notice=merged").text

    assert "Kayıtlar birleştirildi; birleşen kaydın belgeleri" in page
    assert re.search(rf"Kaynak: birleştirme \({SIGNED_IN.username}, \d\d\.\d\d\.\d{{4}}\)", page), (
        page
    )
    assert "Ivan_Petrov-Passport-2.pdf" in page


def test_the_merged_profile_points_to_the_kept_one_and_offers_no_operation(
    client: TestClient, seeded: dict[str, str]
) -> None:
    _merge(client, _token(_prepare(client).text))

    response = client.get(f"/employees/{MERGE}")

    assert response.status_code == 200
    page = response.text
    notice = page.split('<div class="notice merged-notice"', 1)[1].split("</div>", 1)[0]
    assert f'<a href="/employees/{KEEP}">Ivan Petrov ({KEEP})</a>' in notice
    assert "geri açılmaz" in notice
    for link in ("/fields", "/status/confirm", "/merge/employees", "/packages"):
        assert f'action="/employees/{MERGE}{link}"' not in page
        assert f'href="/employees/{MERGE}{link}' not in page
    assert 'id="upload-form"' not in page
    assert "Birleştirilmiş kayda belge yüklenmez" in page
    assert "Birleştirilmiş kayda paket tanımlanmaz" in page


def test_the_list_shows_a_merged_record_only_under_all(
    client: TestClient, seeded: dict[str, str]
) -> None:
    _merge(client, _token(_prepare(client).text))

    default = client.get("/employees").text
    everything = client.get("/employees?status=all").text

    assert f"/employees/{MERGE}" not in default
    assert f"/employees/{MERGE}" in everything and "Birleşti" in everything


def test_a_failed_file_move_answers_409_and_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_move(source: Path, target: Path) -> None:
        raise PermissionError("dosya açık")

    monkeypatch.setattr(merge_module, "_move", failing_move)

    response = _merge(client, _token(_prepare(client).text))

    assert response.status_code == 409
    assert MERGE_FILES_FAILED in response.text
    _unchanged(session_factory, layout, seeded)


# --- birleştirilmiş kayıt başka yolda da kapalıdır -----------------------------------------------


def test_a_context_upload_to_a_merged_record_is_refused_and_opens_no_batch(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, str]
) -> None:
    response = client.post(
        "/api/uploads",
        data={"context_employee_id": CLOSED},
        files=[("files", ("tarama.pdf", make_pdf_bytes(), "application/pdf"))],
    )

    assert response.status_code == 409
    assert MERGED_CONTEXT_MESSAGE in response.text
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Upload)) == 0


def test_a_queue_item_is_not_assigned_to_a_merged_record(
    session_factory: sessionmaker[Session], layout: DataLayout, seeded: dict[str, str]
) -> None:
    with session_factory() as session:
        with pytest.raises(HTTPException) as refused:
            _assignee(session, CLOSED)
        assert (refused.value.status_code, refused.value.detail) == (409, ASSIGNEE_MERGED)
        assert _assignee(session, INACTIVE).id == INACTIVE

        session.add(Upload(id="u_queue", channel="web"))
        item = QueueItem(upload_id="u_queue", kind="unresolved", reason="Sahibi belli değil")
        session.add(item)
        session.commit()
        with pytest.raises(QueueAssignmentError, match="birleştirildi"):
            assign_queue_item(
                session,
                layout,
                item.id,
                CLOSED,
                actor=SIGNED_IN.username,
                render_image_dpi=200,
                render_image_jpeg_quality=90,
            )
        session.rollback()
        assert session.get_one(QueueItem, item.id).resolved_at is None


def test_the_bot_does_not_find_a_merged_record_by_name_or_number(
    session_factory: sessionmaker[Session], seeded: dict[str, str]
) -> None:
    with session_factory() as session:
        assert find_employees(session, parse_person(CLOSED)) == []
        assert find_employees(session, parse_person("Ivan Petrovv")) == []
        # E0005'in orijinal yazımı da "Ivan Petrov"a iner; birleştirilmiş E0009 yine yok.
        found = find_employees(session, parse_person("Ivan Petrov"))
        assert [each.id for each in found] == [KEEP, MERGE]
