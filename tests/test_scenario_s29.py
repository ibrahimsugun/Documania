"""S29 — hazır şablondan çıktı hazırlama (PRD §9; 15.1.2, 15.2.1, 15.2.3; PLAN.md §D123).

İK iki sayfalık sözleşme şablonunu yükler; yapay zekâ (kayıtlı yanıt) 6 boşluk (ad-soyad, doğum
tarihi, doğum yeri, anne adı, kişisel numara, tarih), bir imza ve bir kaşe alanı önerir; İK kişisel
numara kutusunu "boş bırak" yapıp onaylar; anne adı boş bir çalışanın profilinden "Çıktıya
hazırla"; sonra aynı çalışan için yeniden üretir ve çalışanı (pasife alınmış) kalıcı siler.
Beklenen: PDF `Uretilen/` altında K8 adıyla; 4 alan profil değeriyle dolu, anne adı boş ve
bildirimde "eksik: Anne adı"; imza alanı ve sabit metin değişmemiş; orijinal şablonun SHA-256'sı
aynı; `documents` tablosu değişmedi; ikinci üretim `-2`, ilki `superseded`; kalıcı silmede iki
dosya diskten kalkar, satırlar `deleted`; olaylar değer taşımaz.

Şablon ve çalışan sentetiktir; yapay zekâ canlı çağrılmaz.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.recording_provider import RecordingProvider
from app.db.models import (
    Document,
    Employee,
    EmployeeStatus,
    Event,
    GeneratedDocument,
    OutputTemplate,
    User,
)
from app.db.session import create_session_factory
from app.output_templates.examine import examine, read_source, store_examination
from app.output_templates.generate import format_date
from app.storage import DataLayout
from app.storage.atomic import sha256_file
from app.web.auth import SESSION_COOKIE
from app.web.routers.output_templates import provider_available
from tests import test_scenarios_s01_s05 as s01_s05
from tests.fixtures.gen import make_text_pdf_bytes
from tests.test_scenarios_s01_s05 import SIGNED_IN
from tests.web.flash import flashed, toasts

# Senaryo ortamı S1–S5'inkidir: geçici veritabanı, veri dizini ve panel kullanıcısıyla istemci.
engine = s01_s05.engine
layout = s01_s05.layout
client = s01_s05.client

CONTRACT_MAP = Path(__file__).parent / "fixtures" / "ai" / "template_maps" / "contract"
PAGES = ["UGOVOR O RADU", "Potpis zaposlenog"]
PERSONAL = {
    "given_names": "Ivan",
    "surname": "Petrov",
    "date_of_birth": date(1990, 3, 7),
    "place_of_birth": "Novi Sad",
    "personal_number": "0703990710012",
}


def _box_text(page: pymupdf.Page, box: list[float]) -> str:
    shown = page.rect
    x0, y0, x1, y1 = box
    clip = pymupdf.Rect(x0 * shown.width, y0 * shown.height, x1 * shown.width, y1 * shown.height)
    return page.get_text("text", clip=clip * page.derotation_matrix).strip()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture(autouse=True)
def _provider_configured(client: TestClient) -> None:
    client.app.dependency_overrides[provider_available] = lambda: True


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def test_s29_generates_a_copy_with_profile_values_only_then_regenerates_and_deletes(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    # 1) İK iki sayfalık şablonu yükler; inceleme kayıtlı yanıtla haritayı önerir.
    uploaded = client.post(
        "/output-templates",
        data={"name": "Ugovor o radu", "description": ""},
        files={"file": ("ugovor.pdf", make_text_pdf_bytes(PAGES), "application/pdf")},
        follow_redirects=False,
    )
    template_id = int(re.fullmatch(r"/output-templates/(\d+)", uploaded.headers["location"])[1])
    with session_factory() as session:
        template = session.get_one(OutputTemplate, template_id)
        provider = RecordingProvider.from_directory(CONTRACT_MAP)
        row = store_examination(
            session,
            template,
            examine(read_source(session, template), layout, provider),
            provider=provider,
        )
        session.commit()
        fields = {item["field_id"]: item for item in row.json["fields"]}
        original = layout.resolve(template.file_path)
    original_sha = sha256_file(original)

    # 2) İK kişisel numara kutusunu "boş bırak" yapıp onaylar.
    approved = client.post(
        f"/output-templates/{template_id}/maps/1/approve",
        data={
            "source-f1": "full_name",
            "source-f2": "date_of_birth",
            "source-f3": "place_of_birth",
            "source-f4": "mother_name",
            "source-f5": "unassigned",
            "source-f6": "today",
        },
        follow_redirects=False,
    )
    assert approved.status_code == 303

    # 3) Anne adı boş çalışanın profilinden "Çıktıya hazırla".
    with session_factory() as session:
        session.add(Employee(id="E0001", folder_name="Ivan_Petrov_E0001", **PERSONAL))
        session.commit()
    before = format_date(date.today())
    generated = client.post(
        "/employees/E0001/outputs", data={"template_id": str(template_id)}, follow_redirects=False
    )
    after = format_date(date.today())

    assert flashed(generated) == ("employees.output_generated_missing", {"fields": "mother_name"})
    page = client.get("/employees/E0001", cookies=generated.cookies).text
    assert toasts(page) == [
        "Çıktı hazırlandı; profilde boş olan alanlar boş bırakıldı — eksik: Anne adı."
    ]
    with session_factory() as session:
        (output,) = session.scalars(select(GeneratedDocument)).all()
        assert output.path == "Employees/Ivan_Petrov_E0001/Uretilen/Ivan_Petrov-Ugovor-o-radu.pdf"
        assert output.filled_fields_json == [
            "full_name",
            "date_of_birth",
            "place_of_birth",
            "today",
        ]
        assert output.missing_fields_json == ["mother_name"]
        assert session.scalar(select(func.count()).select_from(Document)) == 0
        events = session.scalars(select(Event)).all()

    with pymupdf.open(layout.resolve(output.path)) as document:
        first, second = document[0], document[1]
        assert _box_text(first, fields["f1"]["box"]) == "Ivan Petrov"
        assert _box_text(first, fields["f2"]["box"]) == "07.03.1990"
        assert _box_text(first, fields["f3"]["box"]) == "Novi Sad"
        assert _box_text(first, fields["f4"]["box"]) == ""
        # "Boş bırak": profilde değer olsa da kutu boş kalır.
        assert _box_text(first, fields["f5"]["box"]) == ""
        assert _box_text(second, fields["f6"]["box"]) in {before, after}
        assert _box_text(second, fields["f7"]["box"]) == ""
        assert _box_text(second, fields["f8"]["box"]) == ""
        assert PAGES[0] in first.get_text() and PAGES[1] in second.get_text()
    assert sha256_file(original) == original_sha

    # Olaylar kişisel değer taşımaz.
    recorded = " ".join(f"{event.message} {event.data_json}" for event in events)
    assert "OUTPUT_GENERATED" in {event.type for event in events}
    for value in ("Ivan", "Petrov", "Novi Sad", "0703990710012", "1990"):
        assert value not in recorded

    # 4) Aynı çalışan için yeniden üretim: `-2`, ilki eski sürüm ve dosyası yerinde.
    again = client.post(
        "/employees/E0001/outputs", data={"template_id": str(template_id)}, follow_redirects=False
    )
    assert again.status_code == 303
    with session_factory() as session:
        first, second = session.scalars(
            select(GeneratedDocument).order_by(GeneratedDocument.id)
        ).all()
        assert (first.status, second.status) == ("superseded", "active")
        assert second.path.endswith("/Uretilen/Ivan_Petrov-Ugovor-o-radu-2.pdf")
        files = [layout.resolve(first.path), layout.resolve(second.path)]
        profile_md = layout.profile_path("Ivan_Petrov_E0001").read_text(encoding="utf-8")
    assert all(path.is_file() for path in files)
    assert "## Üretilen belgeler" in profile_md and "Ivan_Petrov-Ugovor-o-radu-2.pdf" in profile_md

    # 5) Çalışan pasife alınıp iki onayla kalıcı silinir (onay belirteci oturuma bağlıdır).
    client.cookies.set(SESSION_COOKIE, "s29-oturum")
    with session_factory() as session:
        if session.get(User, SIGNED_IN.id) is None:
            session.add(
                User(
                    id=SIGNED_IN.id,
                    username=SIGNED_IN.username,
                    password_hash="sentetik",
                    role=SIGNED_IN.role,
                )
            )
        session.get_one(Employee, "E0001").status = EmployeeStatus.INACTIVE.value
        session.commit()
    prepared = client.post("/employees/E0001/delete/prepare")
    assert prepared.status_code == 200
    done = client.post(
        "/employees/E0001/delete",
        data={"confirmation": _token(prepared.text), "documents": "0"},
        follow_redirects=False,
    )
    assert done.status_code == 303, done.text

    assert not any(path.exists() for path in files)
    assert sha256_file(original) == original_sha
    with session_factory() as session:
        rows = session.scalars(select(GeneratedDocument)).all()
        assert {(row.status, row.path) for row in rows} == {("deleted", None)}
        assert session.scalar(select(func.count()).select_from(Document)) == 0
        (deleted,) = session.scalars(select(Event).where(Event.type == "EMPLOYEE_DELETED")).all()
        assert deleted.data_json["outputs"] == 2
        recorded = " ".join(
            f"{event.message} {event.data_json}" for event in session.scalars(select(Event))
        )
    for value in ("Ivan", "Petrov", "Novi Sad", "0703990710012", "1990"):
        assert value not in recorded
