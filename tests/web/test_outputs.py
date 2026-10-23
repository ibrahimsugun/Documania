"""15.2.1, 15.2.2 — profilde "Hazır şablonlar" ve "Üretilen belgeler": düğme yetkisi (yazma
yetkisi, etkin çalışan), çıktıya hazırlama ve bildirimde eksik alan adları, aç/indir ve erişim
kaydı; üretilen belge çalışan belgesi değildir — `documents` ve paket hesabı değişmez (PLAN.md
§D123 d, f, g).

Şablon satırı, dosyası ve onaylı haritası doğrudan yazılır (`tests/output_templates/factory.py`);
çalışan sentetiktir."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AccessLog,
    Document,
    DocumentGroup,
    DocumentGroupItem,
    Employee,
    EmployeeStatus,
    GeneratedDocument,
    OutputTemplateStatus,
    UserRole,
)
from app.groups import employee_packages
from app.storage import DataLayout
from app.web.auth import PanelUser, get_current_user
from tests.output_templates.factory import ready_template
from tests.web.conftest import SIGNED_IN
from tests.web.flash import flashed, toasts

READER = PanelUser(SIGNED_IN.id, SIGNED_IN.username, UserRole.USER.value)
BUTTON = "Çıktıya hazırla"


@pytest.fixture
def template_id(session_factory: sessionmaker[Session], layout: DataLayout) -> int:
    with session_factory() as session:
        session.add(
            Employee(
                id="E0001",
                folder_name="Ivan_Petrov_E0001",
                given_names="Ivan",
                surname="Petrov",
                date_of_birth=date(1990, 3, 7),
            )
        )
        template = ready_template(session, layout)
        session.commit()
        return template.id


def _generate(client: TestClient, template_id: int, employee_id: str = "E0001"):
    return client.post(
        f"/employees/{employee_id}/outputs",
        data={"template_id": str(template_id)},
        follow_redirects=False,
    )


def _outputs(session_factory: sessionmaker[Session]) -> list[GeneratedDocument]:
    with session_factory() as session:
        return list(session.scalars(select(GeneratedDocument)))


def test_profile_lists_ready_templates_with_the_button_and_an_empty_outputs_section(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, template_id: int
) -> None:
    with session_factory() as session:
        draft = ready_template(session, layout, name="Draft form")
        draft.status = OutputTemplateStatus.DRAFT.value
        session.commit()

    page = client.get("/employees/E0001").text

    assert 'class="profile-templates"' in page
    assert f'<a href="/output-templates/{template_id}" translate="no">Work contract</a>' in page
    assert "Draft form" not in page
    assert 'action="/employees/E0001/outputs"' in page
    assert f'name="template_id" value="{template_id}"' in page
    assert BUTTON in page
    assert 'class="profile-outputs"' in page
    assert "Henüz üretilen belge yok." in page


def test_reader_and_inactive_employee_get_no_button_and_cannot_generate(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session], template_id: int
) -> None:
    app.dependency_overrides[get_current_user] = lambda: READER
    assert 'action="/employees/E0001/outputs"' not in client.get("/employees/E0001").text
    assert _generate(client, template_id).status_code == 403

    app.dependency_overrides[get_current_user] = lambda: SIGNED_IN
    with session_factory() as session:
        session.get_one(Employee, "E0001").status = EmployeeStatus.INACTIVE.value
        session.commit()
    page = client.get("/employees/E0001").text
    assert f'name="template_id" value="{template_id}"' not in page
    assert "Pasif ya da birleştirilmiş çalışana çıktı hazırlanmaz." in page
    assert _generate(client, template_id).status_code == 409
    assert _outputs(session_factory) == []


def test_generating_notifies_the_missing_field_names_and_lists_the_output(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, template_id: int
) -> None:
    response = _generate(client, template_id)

    assert response.status_code == 303
    assert response.headers["location"] == "/employees/E0001#outputs"
    assert flashed(response) == ("employees.output_generated_missing", {"fields": "mother_name"})
    (output,) = _outputs(session_factory)
    assert layout.resolve(output.path).is_file()

    page = client.get("/employees/E0001", cookies=response.cookies).text
    assert toasts(page) == [
        "Çıktı hazırlandı; profilde boş olan alanlar boş bırakıldı — eksik: Anne adı."
    ]
    assert f'href="/employees/E0001/outputs/{output.id}/file" target="_blank"' in page
    assert f'href="/employees/E0001/outputs/{output.id}/download"' in page
    assert "Ivan_Petrov-Work-contract.pdf" in page
    assert "<td>Anne adı</td>" in page
    # Üretilen belge çalışan belgesi değildir: belge listesi ve paket hesabı değişmez.
    assert "Henüz belge yok." in page
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 0


def test_generated_document_is_not_counted_by_packages(
    client: TestClient, session_factory: sessionmaker[Session], template_id: int
) -> None:
    with session_factory() as session:
        group = DocumentGroup(name="Hire", normalized_name="hire", created_by="ik")
        session.add(group)
        session.flush()
        session.add(
            DocumentGroupItem(
                group_id=group.id, position=1, match_kind="label", file_label="Work-contract"
            )
        )
        session.commit()
    client.post("/employees/E0001/packages", data={"group_id": "1"}, follow_redirects=False)

    _generate(client, template_id)

    with session_factory() as session:
        (package,) = employee_packages(session, "E0001")
        assert not package.complete
        assert [item.satisfied for item in package.items] == [False]


def test_opening_and_downloading_an_output_is_logged_and_foreign_ids_are_404(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, template_id: int
) -> None:
    _generate(client, template_id)
    (output,) = _outputs(session_factory)
    content = layout.resolve(output.path).read_bytes()

    opened = client.get(f"/employees/E0001/outputs/{output.id}/file")
    downloaded = client.get(f"/employees/E0001/outputs/{output.id}/download")

    assert opened.status_code == downloaded.status_code == 200
    assert opened.content == downloaded.content == content
    assert opened.headers["content-type"] == "application/pdf"
    assert opened.headers["content-disposition"].startswith("inline")
    assert downloaded.headers["content-disposition"].startswith("attachment")
    assert "Ivan_Petrov-Work-contract.pdf" in downloaded.headers["content-disposition"]
    with session_factory() as session:
        session.add(
            Employee(id="E0002", folder_name="Ana_Lic_E0002", given_names="Ana", surname="Lic")
        )
        session.commit()
    assert client.get(f"/employees/E0002/outputs/{output.id}/file").status_code == 404
    with session_factory() as session:
        rows = session.scalars(select(AccessLog).order_by(AccessLog.id)).all()
        assert [(row.generated_document_id, row.document_id, row.action) for row in rows] == [
            (output.id, None, "view"),
            (output.id, None, "download"),
        ]


def test_regenerating_supersedes_and_archive_restore_are_single_steps(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session], template_id: int
) -> None:
    _generate(client, template_id)
    _generate(client, template_id)
    first, second = sorted(_outputs(session_factory), key=lambda output: output.id)
    assert (first.status, second.status, second.sequence_no) == ("superseded", "active", 2)
    page = client.get("/employees/E0001").text
    assert "Eski sürüm" in page and 'class="archived-outputs"' not in page
    assert f'action="/employees/E0001/outputs/{first.id}/archive"' in page

    archived = client.post(f"/employees/E0001/outputs/{first.id}/archive", follow_redirects=False)

    assert archived.status_code == 303
    assert archived.headers["location"] == "/employees/E0001#outputs"
    assert flashed(archived) == ("employees.output_archived", {})
    page = client.get("/employees/E0001").text
    folded = page.split('<details class="archived-outputs" id="outputs-archived">', 1)[1]
    assert "Arşivdeki üretilen belgeler (1)" in folded
    assert f'action="/employees/E0001/outputs/{first.id}/restore"' in folded
    # Arşivdeki belge açılmaya devam eder.
    assert client.get(f"/employees/E0001/outputs/{first.id}/file").status_code == 200

    app.dependency_overrides[get_current_user] = lambda: READER
    assert "/restore" not in client.get("/employees/E0001").text
    assert client.post(f"/employees/E0001/outputs/{first.id}/restore").status_code == 403
    app.dependency_overrides[get_current_user] = lambda: SIGNED_IN

    restored = client.post(f"/employees/E0001/outputs/{first.id}/restore", follow_redirects=False)
    assert flashed(restored) == ("employees.output_restored", {})
    assert {output.id: output.status for output in _outputs(session_factory)} == {
        first.id: "superseded",
        second.id: "active",
    }
    assert client.post("/employees/E0001/outputs/999/archive").status_code == 404


def test_an_archived_template_is_not_selectable_and_its_outputs_stay(
    client: TestClient, session_factory: sessionmaker[Session], template_id: int
) -> None:
    _generate(client, template_id)
    assert client.post(f"/output-templates/{template_id}/archive").status_code in {200, 303}

    page = client.get("/employees/E0001").text

    assert f'name="template_id" value="{template_id}"' not in page
    assert "Ivan_Petrov-Work-contract.pdf" in page
    assert _generate(client, template_id).status_code == 409
