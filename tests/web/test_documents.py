"""10.6.1 — belge geçmişi: bir çıktının kaynak dosyası ve sayfaları tıklanarak izlenir.

Uçtan uca sınama gerçek boru hattından geçen bir partiyle yapılır (`process_upload`, kayıtlı yanıt
sağlayıcısı; canlı yapay zekâ çağrısı yok). Köken kaydının biçimleri — sayfa aralığı, bütün dosya,
birden çok kaynak, eksik ya da bozuk kayıt — elle yazılan sentetik satırlarla sınanır. Gerçek kimlik
belgesi kullanılmaz.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    Event,
    Page,
    Plan,
    Upload,
    UploadFile,
)
from app.events import EventType
from app.pipeline.orchestrate import process_upload
from app.storage import DataLayout
from app.web.auth import get_current_user
from app.web.routers.documents import DOCUMENT_NOT_FOUND, _reference
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    SyntheticPage,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
)

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
PASSPORT = "russian_passport"
UPLOAD_ID = "u_gecmis1"


def _passport() -> SyntheticPage:
    return passport_page(
        PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1)
    )


def _section(html: str, name: str) -> str:
    match = re.search(rf'<section id="{name}".*?</section>', html, re.S)
    assert match is not None, name
    return match.group(0)


def _thumbs(section: str) -> list[str]:
    return re.findall(r'<li class="thumb">.*?</li>', section, re.S)


# --- sentetik veri -----------------------------------------------------------------------------


def _employee(session: Session, layout: DataLayout) -> Employee:
    import_catalog(session, load_seed_catalog())
    employee = Employee(
        id="E0001",
        folder_name="Test_Ornekova_E0001",
        given_names="Test",
        surname="Ornekova",
    )
    session.add(employee)
    session.add(Upload(id=UPLOAD_ID, channel="web"))
    session.flush()
    return employee


def _source_file(
    session: Session, name: str, page_count: int, *, images: set[int] | None = None
) -> UploadFile:
    """Yükleme dosyası + sayfa satırları; `images` görüntüsü olan sayfa sıraları (hepsi)."""
    upload_file = UploadFile(
        upload_id=UPLOAD_ID,
        original_name=name,
        stored_path=f"Inbox/{UPLOAD_ID}/{name}",
        sha256=hashlib.sha256(name.encode()).hexdigest(),
        mime="application/pdf",
        page_count=page_count,
    )
    session.add(upload_file)
    session.flush()
    for index in range(page_count):
        has_image = images is None or index in images
        session.add(
            Page(
                file_id=upload_file.id,
                index=index,
                image_path=f"cache/pages/{upload_file.id}-{index}.png" if has_image else None,
            )
        )
    session.flush()
    return upload_file


def _output(
    session: Session,
    layout: DataLayout,
    employee: Employee,
    refs: Any,
    *,
    name: str = "Test_Ornekova-Pasaport.pdf",
    content: bytes | None = b"%PDF-1.4 cikti",
    status: str = DocumentStatus.ACTIVE.value,
    plan: Plan | None = None,
) -> Document:
    directory = layout.ensure_employee_tree(employee.folder_name) / "Hazir"
    path = directory / name
    if content is not None:
        path.write_bytes(content)
    document = Document(
        employee_id=employee.id,
        type_slug=PASSPORT,
        path=layout.relative(path),
        format="pdf",
        plan_id=plan.id if plan is not None else None,
        source_refs_json=refs,
        status=status,
    )
    session.add(document)
    session.flush()
    return document


def _page_ids(session: Session, file_id: int) -> dict[int, int]:
    return {
        page.index: page.id for page in session.scalars(select(Page).where(Page.file_id == file_id))
    }


@pytest.fixture
def owner(session_factory: sessionmaker[Session], layout: DataLayout) -> str:
    with session_factory() as session:
        _employee(session, layout)
        session.commit()
    return "E0001"


def _history(client: TestClient, document_id: int) -> str:
    response = client.get(f"/documents/{document_id}/history")
    assert response.status_code == 200, response.text
    return response.text


# --- uçtan uca: gerçek boru hattı ---------------------------------------------------------------


def test_history_traces_the_output_back_to_its_source_file_and_page_by_clicking(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    pages = [_passport()]
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()
    uploaded = client.post(
        "/api/uploads",
        files=[("files", ("pasaport.pdf", make_document_pdf_bytes(pages), "application/pdf"))],
    )
    upload_id: str = uploaded.json()["upload_id"]
    with session_factory() as session:
        process_upload(
            session,
            layout,
            session.get_one(Upload, upload_id),
            settings=SETTINGS,
            provider=recorded_provider(tmp_path / "kayit", pages),
        )
    with session_factory() as session:
        document = session.scalars(select(Document)).one()
        source_file = session.scalars(select(UploadFile)).one()
        page_id = session.scalars(select(Page)).one().id
        document_id, file_id = document.id, source_file.id
        output_path = layout.resolve(document.path)

    html = _history(client, document_id)

    assert "<title>Belge geçmişi · Russian Passport · Documania</title>" in html
    assert re.search(
        r'<a href="/employees" class="active" aria-current="page">Çalışanlar</a>', html
    )
    # Çıktının kendisi: çalışan, tür, dosya (açılır), durum, plan sürümü.
    assert '<a href="/employees/E0001">E0001 — ' in html
    assert (
        f'<a href="/employees/E0001/documents/{document_id}/file" target="_blank" '
        f'rel="noopener">{output_path.name}</a>' in html
    )
    assert "Etkin" in html and "Sürüm 1" in html
    # Kaynak dosya: yükleme detay sayfasındaki dosya bölümüne bağlanır.
    sources = _section(html, "sources")
    assert f'<a href="/uploads/{upload_id}#file-{file_id}">pasaport.pdf</a>' in sources
    assert "s. 1" in sources
    # Kaynak sayfa: sayfanın görüntüsünü açar.
    image_url = f"/uploads/{upload_id}/pages/{page_id}/image"
    assert f'<a href="{image_url}" target="_blank" rel="noopener">' in sources
    assert "Sayfa 1" in sources
    # Bağlantılar gerçekten çözülür: dosya bölümü, plan öğesi, sayfa görüntüsü, çıktı dosyası.
    detail = client.get(f"/uploads/{upload_id}")
    assert detail.status_code == 200
    assert f'id="file-{file_id}"' in detail.text
    assert f'<a href="/uploads/{upload_id}#item-i1">plan öğesi i1</a>' in html
    assert 'id="item-i1"' in detail.text
    assert client.get(image_url).status_code == 200
    assert client.get(f"/employees/E0001/documents/{document_id}/file").content == (
        output_path.read_bytes()
    )
    # Olaylar: çıktıyı yazan olay, kaynak dosya ve sayfayla.
    timeline = _section(html, "timeline")
    assert EventType.OUTPUT_SAVED.value in timeline
    assert "pasaport.pdf · s. 1" in timeline


def test_output_row_on_the_upload_detail_page_links_to_its_history(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, owner: str
) -> None:
    with session_factory() as session:
        source = _source_file(session, "kaynak.pdf", 1)
        plan = Plan(upload_id=UPLOAD_ID, version=1, json={}, plan_hash="0" * 64)
        session.add(plan)
        session.flush()
        document = _output(
            session,
            layout,
            session.get_one(Employee, owner),
            [{"file_id": source.id, "pages": [0]}],
            plan=plan,
        )
        session.commit()
        document_id = document.id

    outputs = _section(client.get(f"/uploads/{UPLOAD_ID}").text, "outputs")

    assert f'<a href="/documents/{document_id}/history">Geçmiş</a>' in outputs


# --- köken kaydının biçimleri -------------------------------------------------------------------


def test_only_the_pages_the_output_took_are_traced_and_ranges_are_one_based(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, owner: str
) -> None:
    with session_factory() as session:
        source = _source_file(session, "coksayfa.pdf", 6)
        document = _output(
            session,
            layout,
            session.get_one(Employee, owner),
            [{"file_id": source.id, "pages": [0, 1, 2, 4]}],
        )
        session.commit()
        page_ids = _page_ids(session, source.id)
        document_id = document.id

    sources = _section(_history(client, document_id), "sources")

    thumbs = _thumbs(sources)
    assert [re.search(r"Sayfa (\d+)", thumb).group(1) for thumb in thumbs] == ["1", "2", "3", "5"]  # type: ignore[union-attr]
    for thumb, index in zip(thumbs, (0, 1, 2, 4), strict=True):
        assert f'href="/uploads/{UPLOAD_ID}/pages/{page_ids[index]}/image"' in thumb
    assert f"/pages/{page_ids[3]}/image" not in sources  # alınmayan sayfa izde yok
    assert f"/pages/{page_ids[5]}/image" not in sources
    assert "s. 1–3, 5" in sources


def test_whole_file_source_lists_every_page_of_the_file(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, owner: str
) -> None:
    with session_factory() as session:
        source = _source_file(session, "hepsi.pdf", 3)
        document = _output(
            session,
            layout,
            session.get_one(Employee, owner),
            [{"file_id": source.id, "pages": []}],
        )
        session.commit()
        document_id = document.id

    sources = _section(_history(client, document_id), "sources")

    assert "tüm dosya" in sources
    assert len(_thumbs(sources)) == 3


def test_output_from_several_sources_lists_each_in_order_with_its_own_pages(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, owner: str
) -> None:
    with session_factory() as session:
        first = _source_file(session, "birinci.pdf", 4)
        second = _source_file(session, "ikinci.pdf", 2)
        document = _output(
            session,
            layout,
            session.get_one(Employee, owner),
            [{"file_id": second.id, "pages": [1]}, {"file_id": first.id, "pages": [2, 3]}],
        )
        session.commit()
        ids = {"first": first.id, "second": second.id}
        second_pages = _page_ids(session, second.id)
        first_pages = _page_ids(session, first.id)
        document_id = document.id

    sources = _section(_history(client, document_id), "sources")

    articles = re.findall(r'<article class="file source">.*?</article>', sources, re.S)
    assert len(articles) == 2
    # Kaynaklar köken kaydının sırasıyla, her biri kendi dosyasına ve sayfalarına bağlı.
    assert f"#file-{ids['second']}" in articles[0] and "ikinci.pdf" in articles[0]
    assert f"/pages/{second_pages[1]}/image" in articles[0]
    assert f"#file-{ids['first']}" in articles[1] and "birinci.pdf" in articles[1]
    assert f"/pages/{first_pages[2]}/image" in articles[1]
    assert f"/pages/{first_pages[3]}/image" in articles[1]
    assert "s. 3–4" in articles[1]


def test_page_without_an_analysis_image_is_listed_without_a_link(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, owner: str
) -> None:
    with session_factory() as session:
        source = _source_file(session, "eksik.pdf", 2, images={0})
        document = _output(
            session,
            layout,
            session.get_one(Employee, owner),
            [{"file_id": source.id, "pages": [0, 1, 7]}],  # 7. sayfanın satırı hiç yok
        )
        session.commit()
        document_id = document.id

    thumbs = _thumbs(_section(_history(client, document_id), "sources"))

    assert len(thumbs) == 3
    assert "<img" in thumbs[0] and "Görüntü yok" not in thumbs[0]
    for thumb in thumbs[1:]:
        assert "<img" not in thumb and "<a " not in thumb and "Görüntü yok" in thumb


def test_missing_or_corrupt_source_records_do_not_break_the_page(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, owner: str
) -> None:
    with session_factory() as session:
        source = _source_file(session, "saglam.pdf", 1)
        document = _output(
            session,
            layout,
            session.get_one(Employee, owner),
            [
                {"file_id": 99999, "pages": [0]},  # dosya kaydı yok
                {"pages": [0]},  # dosya kimliği yok
                {"file_id": source.id, "pages": "ilk"},  # sayfa listesi bozuk
                "metin",
                {"file_id": source.id, "pages": [0]},
            ],
        )
        session.commit()
        document_id = document.id

    sources = _section(_history(client, document_id), "sources")

    assert "Kaynak dosya kaydı bulunamadı." in sources
    assert sources.count("Kaynak dosya ve sayfa okunamadı.") == 3
    assert "saglam.pdf" in sources  # sağlam kayıt bozuklardan etkilenmez
    assert len(_thumbs(sources)) == 1


def test_output_without_any_source_record_says_so(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, owner: str
) -> None:
    with session_factory() as session:
        document = _output(session, layout, session.get_one(Employee, owner), [])
        session.commit()
        document_id = document.id

    assert "Bu çıktı için kaynak kaydı yok." in _history(client, document_id)


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ({"file_id": 3, "pages": [0, 2]}, (3, [0, 2])),
        ({"file_id": 3, "pages": []}, (3, [])),
        ({"file_id": 3}, (3, [])),
        ({"pages": [0]}, None),
        ({"file_id": "3", "pages": []}, None),
        ({"file_id": True, "pages": []}, None),
        ({"file_id": 3, "pages": [True]}, None),
        ({"file_id": 3, "pages": ["0"]}, None),
        ({"file_id": 3, "pages": 0}, None),
        ([3, [0]], None),
        (None, None),
    ],
)
def test_source_reference_parsing(ref: object, expected: tuple[int, list[int]] | None) -> None:
    assert _reference(ref) == expected


# --- belgenin durumu ve olayları -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "label"),
    [
        (DocumentStatus.SUPERSEDED.value, "Eski sürüm"),
        (DocumentStatus.ARCHIVED.value, "Arşivlendi"),
    ],
)
def test_history_stays_readable_for_superseded_and_archived_outputs(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    owner: str,
    status: str,
    label: str,
) -> None:
    with session_factory() as session:
        source = _source_file(session, "kaynak.pdf", 1)
        plan = Plan(upload_id=UPLOAD_ID, version=2, json={}, plan_hash="0" * 64)
        session.add(plan)
        session.flush()
        document = _output(
            session,
            layout,
            session.get_one(Employee, owner),
            [{"file_id": source.id, "pages": [0]}],
            status=status,
            plan=plan,
        )
        session.commit()
        document_id = document.id

    html = _history(client, document_id)

    assert label in html
    assert "Sürüm 2" in html
    assert f'<a href="/uploads/{UPLOAD_ID}">{UPLOAD_ID}</a>' in html
    assert len(_thumbs(_section(html, "sources"))) == 1


def test_output_file_that_is_gone_is_named_but_not_linked(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, owner: str
) -> None:
    with session_factory() as session:
        source = _source_file(session, "kaynak.pdf", 1)
        document = _output(
            session,
            layout,
            session.get_one(Employee, owner),
            [{"file_id": source.id, "pages": [0]}],
            name="kayip.pdf",
            content=None,
        )
        session.commit()
        document_id = document.id

    html = _history(client, document_id)

    assert "kayip.pdf" in html and "(dosya bulunamadı)" in html
    assert f"/documents/{document_id}/file" not in html
    assert len(_thumbs(_section(html, "sources"))) == 1  # köken yine izlenir


def test_parties_link_falls_back_to_the_source_file_upload_without_a_plan(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, owner: str
) -> None:
    with session_factory() as session:
        source = _source_file(session, "kaynak.pdf", 1)
        document = _output(
            session, layout, session.get_one(Employee, owner), [{"file_id": source.id, "pages": []}]
        )
        session.commit()
        document_id = document.id

    html = _history(client, document_id)

    assert f'<a href="/uploads/{UPLOAD_ID}">{UPLOAD_ID}</a>' in html
    assert "plan öğesi" not in html  # OUTPUT_SAVED olayı yok: öğe kimliği bilinmiyor
    assert "<dt>Plan</dt>" not in html


def test_events_are_only_the_documents_own_in_time_order(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, owner: str
) -> None:
    with session_factory() as session:
        employee = session.get_one(Employee, owner)
        source = _source_file(session, "kaynak.pdf", 2)
        mine = _output(session, layout, employee, [{"file_id": source.id, "pages": [0]}])
        other = _output(
            session, layout, employee, [{"file_id": source.id, "pages": [1]}], name="diger.pdf"
        )
        for document, kind, actor in (
            (mine, "OUTPUT_SAVED", "system"),
            (other, "ARCHIVED", "baskasi"),
            (mine, "MANUAL_MOVE", "ik-yetkilisi"),
        ):
            session.add(
                Event(
                    upload_id=UPLOAD_ID,
                    file_id=source.id,
                    page_index=0,
                    document_id=document.id,
                    employee_id=employee.id,
                    actor=actor,
                    type=kind,
                )
            )
            session.flush()
        session.commit()
        document_id = mine.id

    timeline = _section(_history(client, document_id), "timeline")

    assert timeline.index("OUTPUT_SAVED") < timeline.index("MANUAL_MOVE")
    assert "ik-yetkilisi" in timeline and "kaynak.pdf · s. 1" in timeline
    assert "ARCHIVED" not in timeline and "baskasi" not in timeline


def test_document_without_events_says_so(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, owner: str
) -> None:
    with session_factory() as session:
        document = _output(session, layout, session.get_one(Employee, owner), [])
        session.commit()
        document_id = document.id

    assert "Bu belge için olay yok." in _history(client, document_id)


def test_profile_document_row_links_to_its_history(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, owner: str
) -> None:
    with session_factory() as session:
        source = _source_file(session, "kaynak.pdf", 1)
        document = _output(
            session,
            layout,
            session.get_one(Employee, owner),
            [{"file_id": source.id, "pages": [0]}],
        )
        session.commit()
        document_id = document.id

    profile = client.get("/employees/E0001").text

    assert f'<a href="/documents/{document_id}/history">Geçmiş</a>' in profile
    assert client.get(f"/documents/{document_id}/history").status_code == 200


# --- bulunamayan belge, oturum ve salt okunurluk ------------------------------------------------


def test_unknown_document_is_404_with_a_message(client: TestClient) -> None:
    response = client.get("/documents/424242/history")

    assert response.status_code == 404
    assert DOCUMENT_NOT_FOUND in response.text
    assert 'role="alert"' in response.text
    assert client.get("/documents/yok/history").status_code == 422


def test_history_needs_a_session(app: FastAPI, client: TestClient) -> None:
    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app, follow_redirects=False)

    response = anonymous.get("/documents/1/history")

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_history_is_read_only_and_leaves_the_records_untouched(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, owner: str
) -> None:
    with session_factory() as session:
        source = _source_file(session, "kaynak.pdf", 1)
        refs = [{"file_id": source.id, "pages": [0]}]
        document = _output(session, layout, session.get_one(Employee, owner), refs)
        session.commit()
        document_id = document.id
        output = layout.resolve(document.path)
    before = output.read_bytes()

    _history(client, document_id)
    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)(f"/documents/{document_id}/history")
        assert response.status_code == 405, method

    with session_factory() as session:
        stored = session.get_one(Document, document_id)
        assert stored.source_refs_json == refs
        assert stored.status == DocumentStatus.ACTIVE.value
        assert session.scalars(select(Event)).all() == []
    assert output.read_bytes() == before
