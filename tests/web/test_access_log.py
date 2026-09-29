"""10.9.1-10.9.2 — panelde belge içeriğini düzenleyen yol yoktur; her açma ve indirme kullanıcı ve
zamanla `access_log`'a yazılır.

Veri sentetiktir (`tests/fixtures/gen.py`); gerçek kimlik belgesi ya da yapay zekâ çağrısı yoktur.
10.9.1 iki yönden sınanır: sunucunun **bütün** değiştirici yolları gözden geçirilmiş bir listeden
ibarettir (yeni bir POST/PUT/PATCH/DELETE yolu bu testi kırar, gözden geçirilip listeye girer) ve
şablonlar içerik düzenleme arayüzü (`contenteditable`, tuval, PUT/PATCH/DELETE formu) taşımaz.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AccessAction,
    AccessChannel,
    AccessLog,
    Document,
    DocumentStatus,
    Employee,
    KnownDocumentType,
    User,
)
from app.storage import DataLayout
from app.web.auth import PanelUser, get_current_user
from tests.fixtures.gen import make_docx_bytes, make_pdf_bytes, make_portrait_image_bytes
from tests.web.conftest import SIGNED_IN

PASSPORT = "russian_passport"
PHOTO = "profile_picture"
TEMPLATES = Path(__file__).resolve().parents[2] / "app" / "web" / "templates"


def _catalog(session: Session) -> None:
    for slug, name, label in ((PASSPORT, "Rus Pasaportu", "Pasaport"), (PHOTO, "Foto", "Foto")):
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


def _employee(session: Session, number: int = 1) -> Employee:
    employee_id = f"E{number:04d}"
    employee = Employee(
        id=employee_id,
        folder_name=f"Dmitry_Vasiliev_{employee_id}",
        given_names="Dmitry",
        surname="Vasiliev",
    )
    session.add(employee)
    session.flush()
    return employee


def _document(
    session: Session,
    layout: DataLayout,
    employee: Employee,
    file_name: str,
    content: bytes | None,
    *,
    slug: str = PASSPORT,
    status: str = DocumentStatus.ACTIVE.value,
) -> Document:
    path = layout.ensure_employee_tree(employee.folder_name) / "Hazir" / file_name
    if content is not None:
        path.write_bytes(content)
    document = Document(
        employee_id=employee.id,
        type_slug=slug,
        path=layout.relative(path),
        format=path.suffix.removeprefix("."),
        sequence_no=1,
        source_refs_json=[],
        status=status,
    )
    session.add(document)
    session.flush()
    return document


def _access_rows(session_factory: sessionmaker[Session]) -> list[AccessLog]:
    with session_factory() as session:
        return list(session.scalars(select(AccessLog).order_by(AccessLog.id)))


@pytest.fixture
def stored(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, Any]:
    """E0001'in etkin bir pasaportu; `id` belge kimliği, `content` dosyanın baytları."""
    content = make_pdf_bytes(2)
    with session_factory() as session:
        _catalog(session)
        employee = _employee(session)
        document = _document(session, layout, employee, "Dmitry_Vasiliev-Pasaport.pdf", content)
        session.commit()
        return {
            "id": document.id,
            "content": content,
            "url": f"/employees/E0001/documents/{document.id}",
            "path": layout.resolve(document.path),
        }


# --- 10.9.2: açma ve indirme kaydı -------------------------------------------------------------


def test_opening_a_document_logs_user_document_action_channel_and_time(
    client: TestClient, session_factory: sessionmaker[Session], stored: dict[str, Any]
) -> None:
    before = datetime.now(UTC)
    response = client.get(f"{stored['url']}/file")
    after = datetime.now(UTC)

    assert response.status_code == 200
    (entry,) = _access_rows(session_factory)
    assert entry.user_id == SIGNED_IN.id
    assert entry.document_id == stored["id"]
    assert entry.action == AccessAction.VIEW.value == "view"
    assert entry.channel == AccessChannel.WEB.value == "web"
    assert entry.ts.tzinfo is not None
    assert before <= entry.ts <= after


def test_downloading_a_document_logs_a_download(
    client: TestClient, session_factory: sessionmaker[Session], stored: dict[str, Any]
) -> None:
    response = client.get(f"{stored['url']}/download")

    assert response.status_code == 200
    (entry,) = _access_rows(session_factory)
    assert (entry.user_id, entry.document_id) == (SIGNED_IN.id, stored["id"])
    assert (entry.action, entry.channel) == ("download", "web")


def test_every_access_adds_a_row_and_none_is_merged_or_replaced(
    client: TestClient, session_factory: sessionmaker[Session], stored: dict[str, Any]
) -> None:
    for suffix in ("file", "file", "download", "file"):
        assert client.get(f"{stored['url']}/{suffix}").status_code == 200

    rows = _access_rows(session_factory)

    assert [row.action for row in rows] == ["view", "view", "download", "view"]
    assert len({row.id for row in rows}) == 4
    assert [row.ts for row in rows] == sorted(row.ts for row in rows)


def test_the_log_names_who_looked_when_several_users_do(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    stored: dict[str, Any],
) -> None:
    second = PanelUser(id=2, username="ikinci-yonetici", role="admin")
    with session_factory() as session:
        session.add(User(id=second.id, username=second.username, password_hash="x", role="admin"))
        session.commit()

    client.get(f"{stored['url']}/file")
    app.dependency_overrides[get_current_user] = lambda: second
    client.get(f"{stored['url']}/download")

    rows = _access_rows(session_factory)
    assert [(row.user_id, row.action) for row in rows] == [
        (SIGNED_IN.id, "view"),
        (second.id, "download"),
    ]


@pytest.mark.parametrize(
    "status",
    [DocumentStatus.SUPERSEDED.value, DocumentStatus.ARCHIVED.value],
)
def test_an_old_or_archived_document_is_logged_too(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    stored: dict[str, Any],
    status: str,
) -> None:
    with session_factory() as session:
        employee = session.get(Employee, "E0001")
        assert employee is not None
        document = _document(
            session, layout, employee, "Eski-Pasaport.pdf", make_pdf_bytes(), status=status
        )
        session.commit()
        document_id = document.id

    assert client.get(f"/employees/E0001/documents/{document_id}/download").status_code == 200

    (entry,) = _access_rows(session_factory)
    assert (entry.document_id, entry.action) == (document_id, "download")


def test_a_word_attachment_opened_through_the_open_path_is_logged_as_a_view(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    with session_factory() as session:
        _catalog(session)
        employee = _employee(session)
        document = _document(
            session, layout, employee, "Dmitry_Vasiliev-CV.docx", make_docx_bytes()
        )
        session.commit()
        document_id = document.id

    response = client.get(f"/employees/E0001/documents/{document_id}/file")

    # Tarayıcıda açılamayan biçim indirme olarak gider; log kullanıcının istediği eylemi tutar.
    assert response.headers["content-disposition"].startswith("attachment")
    (entry,) = _access_rows(session_factory)
    assert entry.action == "view"


def test_a_document_that_is_not_served_is_not_logged(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    stored: dict[str, Any],
) -> None:
    with session_factory() as session:
        other = _employee(session, number=2)
        lost = _document(session, layout, other, "Kayip.pdf", None)
        session.commit()
        lost_id = lost.id

    responses = [
        client.get("/employees/E0001/documents/9999/file"),  # belge yok
        client.get(f"/employees/E0002/documents/{stored['id']}/file"),  # başka çalışanın belgesi
        client.get(f"/employees/E0002/documents/{lost_id}/download"),  # dosyası yok
        client.get(f"/employees/E0009/documents/{stored['id']}/download"),  # çalışan yok
    ]

    assert [response.status_code for response in responses] == [404] * 4
    assert _access_rows(session_factory) == []


def test_looking_at_pages_is_not_opening_a_document(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    stored: dict[str, Any],
) -> None:
    with session_factory() as session:
        employee = session.get(Employee, "E0001")
        assert employee is not None
        _document(
            session,
            layout,
            employee,
            "Dmitry_Vasiliev-Foto.png",
            make_portrait_image_bytes(),
            slug=PHOTO,
        )
        session.commit()

    for url in (
        "/employees",
        "/employees/E0001",
        "/employees/E0001/photo",
        f"/documents/{stored['id']}/history",
    ):
        assert client.get(url).status_code == 200, url

    assert _access_rows(session_factory) == []


def test_the_document_is_not_served_when_the_log_cannot_be_written(
    app: FastAPI,
    session_factory: sessionmaker[Session],
    stored: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("log yazılamadı")

    monkeypatch.setattr("app.web.routers.employees.record_access", broken)
    quiet = TestClient(app, raise_server_exceptions=False)

    responses = [quiet.get(f"{stored['url']}/file"), quiet.get(f"{stored['url']}/download")]

    assert [response.status_code for response in responses] == [500, 500]
    assert all(stored["content"][:20] not in response.content for response in responses)
    assert _access_rows(session_factory) == []


def test_serving_never_touches_the_stored_file(client: TestClient, stored: dict[str, Any]) -> None:
    digest = hashlib.sha256(stored["path"].read_bytes()).hexdigest()

    client.get(f"{stored['url']}/file")
    client.get(f"{stored['url']}/download")

    assert hashlib.sha256(stored["path"].read_bytes()).hexdigest() == digest
    assert stored["path"].read_bytes() == stored["content"]


def test_an_access_changes_only_the_access_log(
    client: TestClient, session_factory: sessionmaker[Session], stored: dict[str, Any]
) -> None:
    """Erişim satırı belgeyi ya da başka tabloyu değiştirmez: yalnız `access_log` büyür."""
    with session_factory() as session:
        before = session.scalar(select(func.count()).select_from(Document))

    client.get(f"{stored['url']}/file")

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == before
        assert session.scalar(select(func.count()).select_from(AccessLog)) == 1


# --- 10.9.1: içerik düzenleme yolu yok ----------------------------------------------------------

# Sunucunun bütün değiştirici (POST/PUT/PATCH/DELETE) yolları ve neyi değiştirdikleri. Hiçbiri bir
# belgenin **içeriğini** yazmaz: yükleme yeni dosya alır, taşıma/arşiv yalnız yeri ve adı değiştirir
# (K11, K16), kuyruk/onay/profil akışları kayıt alanı yazar, yeniden analiz yeni plan sürümü üretir
# (K18), geri kalanı oturum ve onay belirtecidir. Yeni bir yol eklenirse bu liste bilerek
# genişletilir; içerik yazan bir yol buraya girmez (K17).
REVIEWED_MUTATING_ROUTES: dict[tuple[str, str], str] = {
    ("POST", "/login"): "oturum",
    ("POST", "/logout"): "oturum",
    ("POST", "/upload"): "yeni dosya yükleme",
    ("POST", "/api/uploads"): "yeni dosya yükleme",
    ("POST", "/uploads/{upload_id}/rerun"): "planı yeniden yürütme",
    ("POST", "/api/uploads/{upload_id}/rerun"): "planı yeniden yürütme",
    ("POST", "/uploads/{upload_id}/reanalyze"): "yeni plan sürümü (K18)",
    ("POST", "/uploads/{upload_id}/reanalyze/prepare"): "onay belirteci",
    ("POST", "/api/uploads/{upload_id}/reanalyze"): "yeni plan sürümü (K18)",
    ("POST", "/uploads/{upload_id}/dismiss"): "taramayı yoksayma: kayıt alanı, silme yok (10.3.4)",
    ("POST", "/uploads/{upload_id}/dismiss/prepare"): "onay belirteci",
    ("POST", "/queues/{queue_item_id}/assign"): "kuyruk ataması (K16)",
    ("POST", "/queues/{queue_item_id}/assign/prepare"): "onay belirteci",
    ("POST", "/queues/{queue_item_id}/profile"): "profil onayı (K16)",
    ("POST", "/queues/{queue_item_id}/profile/confirm"): "onay metni",
    ("POST", "/queues/{queue_item_id}/profile/prepare"): "onay belirteci",
    ("POST", "/queues/{queue_item_id}/close/prepare"): "onay belirteci",
    ("POST", "/queues/{queue_item_id}/close"): (
        "kuyruk öğesini kapatma: çözüm alanları; kopya ve reason.json yerinde, silme yok "
        "(10.7.4, K16, R11)"
    ),
    ("POST", "/queues/{queue_item_id}/reopen"): (
        "kapatılan kuyruk öğesini yeniden açma: çözüm alanları temizlenir (10.7.4, §D61)"
    ),
    ("POST", "/uploads/{upload_id}/undismiss"): (
        "yoksaymayı geri alma: kayıt alanı, yoksaymayla kapanan öğeler açılır (10.3.5, §D61)"
    ),
    ("POST", "/api/queue/{queue_item_id}/assign"): "kuyruk ataması (K16)",
    ("POST", "/api/queue/{queue_item_id}/assign/prepare"): "onay belirteci",
    ("POST", "/api/queue/documents/{document_id}/archive"): "arşive taşıma (K16)",
    ("POST", "/api/queue/documents/{document_id}/archive/prepare"): "onay belirteci",
    ("POST", "/documents/{document_id}/move"): "başka çalışana taşıma (K16)",
    ("POST", "/documents/{document_id}/move/prepare"): "onay belirteci",
    ("POST", "/documents/{document_id}/archive"): "profilden arşive taşıma (08.4.1, K16)",
    ("POST", "/documents/{document_id}/archive/prepare"): "onay belirteci",
    ("POST", "/documents/{document_id}/unarchive"): (
        "arşivden geri alma: Hazir'a K8 adıyla taşıma, içerik değişmez (10.5.10, K16, §D61)"
    ),
    ("POST", "/documents/{document_id}/unarchive/prepare"): "onay belirteci",
    ("POST", "/document-types"): "katalog kaydı: tür oluşturma (11.1.1)",
    ("POST", "/document-types/{slug}"): "katalog kaydı: tür düzenleme (11.1.1)",
    ("POST", "/document-types/{slug}/deactivate"): "katalog kaydı: pasifleştirme (11.1.1)",
    ("POST", "/document-types/{slug}/activate"): "katalog kaydı: etkinleştirme (11.1.1)",
    # 11.1.6 (tm 132, §D62): tür arşivi ve toplu seçim; tür silinmez, belge içeriği değişmez.
    ("POST", "/document-types/{slug}/archive/prepare"): "onay belirteci",
    ("POST", "/document-types/{slug}/archive"): "katalog kaydı: tür arşivi (11.1.6)",
    ("POST", "/document-types/{slug}/restore"): "katalog kaydı: arşivden geri alma (11.1.6)",
    ("POST", "/document-types/bulk"): (
        "katalog kaydı: toplu pasifleştirme, etkinleştirme ve iki aşamalı arşiv (11.1.6)"
    ),
    ("POST", "/document-types/bulk/prepare"): "onay belirteci",
    (
        "POST",
        "/document-types/{slug}/examples",
    ): "örnek belge yükleme ve example_files kaydı, çalışan verisi değil (11.2.1, 11.9.6)",
    ("POST", "/document-types/{slug}/description"): "tür açıklaması önerisi, kaydetmez (11.3.1)",
    ("POST", "/document-types/{slug}/photo-rules"): "katalog kaydı: fotoğraf kural seti (11.6.1)",
    ("POST", "/document-types/criteria/add"): "kabul kriteri listesi, kaydetmez (11.1.3)",
    ("POST", "/document-types/criteria/remove"): "kabul kriteri listesi, kaydetmez (11.1.3)",
    ("POST", "/document-types/candidate-types/{candidate_id}/approve/confirm"): "onay metni",
    ("POST", "/document-types/candidate-types/{candidate_id}/approve/prepare"): "onay belirteci",
    ("POST", "/document-types/candidate-types/{candidate_id}/approve"): (
        "katalog kaydı: aday türün onayı (11.5.2, K16)"
    ),
    ("POST", "/document-types/candidate-types/{candidate_id}/reject"): "aday türün reddi (11.5.4)",
    ("POST", "/document-types/candidate-types/{candidate_id}/restore"): (
        "aday türü retten geri alma (11.5.7)"
    ),
    ("POST", "/document-types/candidate-types/{candidate_id}/examine"): (
        "aday türün tür taslağı, kaydetmez ve onaylamaz (11.5.6)"
    ),
    ("POST", "/document-types/candidate-types/{candidate_id}/reanalyze/prepare"): "onay belirteci",
    ("POST", "/document-types/candidate-types/{candidate_id}/reanalyze"): (
        "yeni plan sürümleri (11.5.3, K18)"
    ),
    ("POST", "/document-groups"): "belge grubu kaydı: grup açma (14.1.1)",
    ("POST", "/document-groups/{group_id}"): "belge grubu kaydı: ad ve açıklama (14.1.1)",
    ("POST", "/document-groups/{group_id}/items"): "belge grubu kaydı: kalem ekleme (14.1.2)",
    ("POST", "/document-groups/{group_id}/items/{item_id}/remove"): (
        "belge grubu kaydı: kalemi kaldırma, satır kalır (14.1.1, R11)"
    ),
    ("POST", "/document-groups/{group_id}/archive"): (
        "belge grubu kaydı: arşivleme, silme yok (14.1.1, R11)"
    ),
    ("POST", "/document-groups/{group_id}/restore"): (
        "belge grubu kaydı: arşivden geri alma (14.1.1)"
    ),
    ("POST", "/employees/{employee_id}/packages"): (
        "belge paketi kaydı: gruptan paket tanımlama, belgeye dokunmaz (14.2.1)"
    ),
    ("POST", "/employees/{employee_id}/packages/{package_id}/cancel"): (
        "belge paketi kaydı: iptal, silme yok (14.2.3, R11)"
    ),
    ("POST", "/employees/{employee_id}/packages/{package_id}/reopen"): (
        "belge paketi kaydı: iptali geri alma (14.2.3)"
    ),
    ("POST", "/employees/{employee_id}/status/prepare"): "onay belirteci",
    ("POST", "/employees/{employee_id}/status"): (
        "çalışan kaydı: pasife alma / yeniden etkinleştirme, klasör ve belgeler yerinde "
        "(10.5.7, K16, R11)"
    ),
    ("POST", "/employees/{employee_id}/records/{kind}/{record_id}/remove/prepare"): (
        "onay belirteci"
    ),
    ("POST", "/employees/{employee_id}/records/{kind}/{record_id}/remove"): (
        "çalışanın alt kaydı: kaldırıldı işareti, silme yok; belgeye dokunmaz (10.5.8, K16, R11)"
    ),
    ("POST", "/employees/{employee_id}/records/{kind}/{record_id}/restore"): (
        "çalışanın alt kaydı: kaldırmayı geri alma (10.5.8)"
    ),
    ("POST", "/employees/{employee_id}/contacts"): (
        "çalışanın iletişim bilgisi: elle ekleme, belge içeriği değişmez (10.5.8, 05.8.2)"
    ),
    ("POST", "/employees/{employee_id}/fields/prepare"): "onay belirteci",
    ("POST", "/employees/{employee_id}/merge/prepare"): "onay belirteci",
    ("POST", "/employees/{employee_id}/merge"): (
        "iki çalışanı birleştirme: belgeler K8 adıyla taşınır, alt kayıtlar bağlanır, birleşen "
        "kayıt kapanır; silme yok, belge içeriği değişmez (10.5.9, K11, K16, R11)"
    ),
    ("POST", "/employees/{employee_id}/fields"): (
        "çalışan kaydı: profil alanları ve K8 yeniden adlandırma; belge içeriği değişmez "
        "(10.5.6, K16)"
    ),
    ("POST", "/training"): "eğitim yüklemesi: örneklere kopya, çalışan verisi değil (11.9.1)",
    ("POST", "/training/items/{item_id}/place"): (
        "eğitim öğesini türe yerleştirme: örneğe kopya ve kayıt (11.9.1, K11)"
    ),
    ("POST", "/training/items/{item_id}/dismiss"): (
        "eğitim öğesini yoksayma: durum ve not, dosya yerinde kalır (11.9.6, R11)"
    ),
    (
        "POST",
        "/training/items/{item_id}/restore",
    ): "eğitim öğesinin yoksaymasını geri alma (11.9.6)",
    ("POST", "/training/runs/{run_id}/archive"): (
        "eğitim çalıştırmasını arşivleme: öğeler ve örnekler değişmez (11.9.6, R11)"
    ),
    (
        "POST",
        "/training/runs/{run_id}/restore",
    ): "eğitim çalıştırmasını arşivden geri alma (11.9.6)",
    ("POST", "/training/examples/verify"): "etiket kararı: AI kararı → doğrulandı (11.9.4)",
    ("POST", "/training/examples/{example_id}/move/confirm"): "birinci onay metni (11.9.4)",
    ("POST", "/training/examples/{example_id}/move/prepare"): "onay belirteci",
    ("POST", "/training/examples/{example_id}/move"): (
        "eğitim örneğini başka türün klasörüne taşıma (11.9.4, K11)"
    ),
    ("POST", "/training/examples/{example_id}/remove/confirm"): "birinci onay metni (11.9.4)",
    ("POST", "/training/examples/{example_id}/remove/prepare"): "onay belirteci",
    ("POST", "/training/examples/{example_id}/remove"): (
        "eğitim örneğini arşive taşıma; silinmez (11.9.4, R11)"
    ),
    ("POST", "/training/maps"): "harita önizlemesi: hiçbir şey yazmaz (11.9.5)",
    ("POST", "/training/maps/confirm"): "birinci onay metni (11.9.5)",
    ("POST", "/training/maps/prepare"): "onay belirteci",
    ("POST", "/training/maps/start"): (
        "toplu tarama: eğitim öğeleri ve haritanın kopyası, çalışan verisi değil (11.9.5)"
    ),
    ("POST", "/users"): "panel kullanıcısı açma (10.1.4)",
    ("POST", "/users/{user_id}/password"): "yöneticinin parola sıfırlaması (10.1.4)",
    ("POST", "/users/{user_id}/status"): (
        "kullanıcıyı pasife alma ve etkinleştirme; silinmez (10.1.4, R11)"
    ),
    ("POST", "/account/password"): "kullanıcının kendi parolası (10.1.4)",
}

# "assign" içindeki "sign" düzenleme sayılmasın: sözcük başı ve sonu harf olmayan sınırdır.
EDITING_WORDS = re.compile(
    r"(?<![a-z])(edit|crop|rotate|contrast|annotate|stamp|redact|overwrite|replace|fill|sign"
    r"|write|save)(?![a-z])",
    re.IGNORECASE,
)
EDITING_MARKUP = re.compile(
    r"contenteditable|<canvas|<textarea|hx-(put|patch|delete)|method=[\"']?(put|patch|delete)",
    re.IGNORECASE,
)


def _mutating_routes(app: FastAPI) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method.upper() not in {"GET", "HEAD", "OPTIONS"}
    }


def test_the_panel_has_no_put_patch_or_delete_route(app: FastAPI) -> None:
    assert {method for method, _ in _mutating_routes(app)} == {"POST"}


def test_every_mutating_route_is_a_reviewed_one_and_none_writes_content(app: FastAPI) -> None:
    assert _mutating_routes(app) == set(REVIEWED_MUTATING_ROUTES)


def test_no_route_is_named_after_editing_content(app: FastAPI) -> None:
    paths = app.openapi()["paths"]
    # Önce eşleşmenin gerçekten çalıştığını göster; sonra yolların hiçbiri düzenleme adı taşımaz.
    assert EDITING_WORDS.search("/documents/1/crop")
    assert [path for path in paths if EDITING_WORDS.search(path)] == []


def test_the_only_document_routes_that_change_anything_move_or_archive_it(app: FastAPI) -> None:
    # 10.5.10 (tm 130, §D62): arşivden geri alma da yalnız taşır; liste bilerek genişledi.
    document_mutations = {
        (method, path)
        for method, path in _mutating_routes(app)
        if "/documents/" in path or path.startswith("/documents")
    }

    assert document_mutations == {
        ("POST", "/documents/{document_id}/move"),
        ("POST", "/documents/{document_id}/move/prepare"),
        ("POST", "/api/queue/documents/{document_id}/archive"),
        ("POST", "/api/queue/documents/{document_id}/archive/prepare"),
        ("POST", "/documents/{document_id}/archive"),
        ("POST", "/documents/{document_id}/archive/prepare"),
        ("POST", "/documents/{document_id}/unarchive"),
        ("POST", "/documents/{document_id}/unarchive/prepare"),
    }


def test_templates_offer_no_content_editing_and_post_only_to_reviewed_routes(
    app: FastAPI,
) -> None:
    reviewed = [
        re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path)) + "$")
        for method, path in REVIEWED_MUTATING_ROUTES
        if method == "POST"
    ]
    templates = sorted(TEMPLATES.glob("*.html"))
    assert templates, "şablon dizini bulunamadı"

    for template in templates:
        html = template.read_text(encoding="utf-8")
        assert EDITING_MARKUP.search(html) is None, template.name
        targets = re.findall(r"hx-post=\"([^\"]+)\"", html)
        targets += re.findall(r"method=\"post\"\s+action=\"([^\"]+)\"", html)
        for target in targets:
            path = re.sub(r"\{\{[^}]*\}\}", "X", target)
            assert any(pattern.match(path) for pattern in reviewed), (template.name, target)


@pytest.mark.parametrize("suffix", ["file", "download", "photo"])
def test_document_content_paths_refuse_every_write_method(
    client: TestClient,
    session_factory: sessionmaker[Session],
    stored: dict[str, Any],
    suffix: str,
) -> None:
    url = "/employees/E0001/photo" if suffix == "photo" else f"{stored['url']}/{suffix}"

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = client.request(method, url, content=b"yeni icerik")
        assert response.status_code == 405, (method, url)

    assert stored["path"].read_bytes() == stored["content"]
    assert _access_rows(session_factory) == []


def test_history_page_refuses_every_write_method(
    client: TestClient, stored: dict[str, Any]
) -> None:
    url = f"/documents/{stored['id']}/history"

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, url).status_code == 405, method
    assert stored["path"].read_bytes() == stored["content"]
