"""10.3.3 — yükleme listesi: Yüklemeler menüsü partileri en yeni üstte listeler, durum ve tarihe
göre süzer, 50'şerli sayfalar.

Partiler doğrudan veritabanına yazılır (durum, kanal, kuyruk öğeleri sınanacak değerlerle); sayfa
`TestClient` ile çizilir. Veri sentetiktir; gerçek kimlik belgesi, yapay zekâ ya da ağ çağrısı
yoktur. Dosya adları bilerek kişi adı taşır: sayfada geçmemeleri sınanır.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Employee,
    Event,
    Page,
    QueueItem,
    QueueKind,
    Upload,
    UploadFile,
    UploadStatus,
)
from app.web.auth import get_current_user
from app.web.routers.upload_page import get_clock
from app.web.routers.uploads_list import PAGE_SIZE

BASE = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
SECRET_FILE_NAME = "Ivan_Petrov-Pasaport-ozel.pdf"


@pytest.fixture(autouse=True)
def _clock(app: FastAPI) -> None:
    # 10.3.7: sayfa açılırken süresi dolan parti iptal edilir; saat sabittir ve buradaki süren
    # partiler `BASE`'ten sonra alınmıştır — süreleri dolmamıştır (iptal `test_upload_cancel.py`).
    app.dependency_overrides[get_clock] = lambda: BASE


def _rows(html: str) -> list[list[str]]:
    """Liste tablosunun gövde satırları, hücre metniyle (boş hücre boş dizge)."""
    table = re.search(r'<table class="access-log uploads-list">(.*?)</table>', html, re.S)
    assert table is not None, "liste tablosu yok"
    body = re.search(r"<tbody>(.*?)</tbody>", table.group(1), re.S)
    assert body is not None
    return [
        [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell)).strip()
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        ]
        for row in re.findall(r"<tr>(.*?)</tr>", body.group(1), re.S)
    ]


def _ids(html: str) -> list[str]:
    return [row[0] for row in _rows(html)]


def _upload(
    session_factory: sessionmaker[Session],
    upload_id: str,
    *,
    created_at: datetime = BASE,
    status: UploadStatus = UploadStatus.DONE,
    channel: str = "web",
    uploaded_by: str | None = "test-yonetici",
    context_employee_id: str | None = None,
    pages_per_file: tuple[int, ...] = (),
    queue: tuple[tuple[QueueKind, bool], ...] = (),
) -> None:
    """Partiyi yazar; her `pages_per_file` öğesi bir dosya, sayısı kadar sayfa. `queue` öğeleri
    `(tür, çözülmüş mü)` çiftidir."""
    with session_factory() as session:
        session.add(
            Upload(
                id=upload_id,
                channel=channel,
                uploaded_by=uploaded_by,
                context_employee_id=context_employee_id,
                status=status.value,
                created_at=created_at,
            )
        )
        session.flush()
        for number, pages in enumerate(pages_per_file, start=1):
            upload_file = UploadFile(
                upload_id=upload_id,
                original_name=SECRET_FILE_NAME,
                stored_path=f"Inbox/{upload_id}/{number}-{SECRET_FILE_NAME}",
                sha256=f"{upload_id}-{number}".ljust(64, "0"),
                mime="application/pdf",
                page_count=pages,
            )
            session.add(upload_file)
            session.flush()
            session.add_all(Page(file_id=upload_file.id, index=index) for index in range(pages))
        for kind, resolved in queue:
            session.add(
                QueueItem(
                    upload_id=upload_id,
                    kind=kind.value,
                    reason="Okunamadı.",
                    resolved_at=BASE if resolved else None,
                )
            )
        session.commit()


def _employee(session_factory: sessionmaker[Session], number: int, given: str, surname: str) -> str:
    employee_id = f"E{number:04d}"
    with session_factory() as session:
        session.add(
            Employee(
                id=employee_id,
                folder_name=f"{given}_{surname}_{employee_id}",
                given_names=given,
                surname=surname,
            )
        )
        session.commit()
    return employee_id


def test_uploads_are_listed_newest_first_with_a_detail_link(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(session_factory, "u_old", created_at=BASE - timedelta(days=2))
    _upload(session_factory, "u_new", created_at=BASE)
    _upload(session_factory, "u_mid", created_at=BASE - timedelta(days=1))

    page = client.get("/uploads")

    assert page.status_code == 200
    assert _ids(page.text) == ["u_new", "u_mid", "u_old"]
    assert '<a href="/uploads/u_new">u_new</a>' in page.text
    assert "3 yükleme" in page.text


def test_a_row_shows_time_channel_uploader_files_pages_status_and_open_queue_counts(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(
        session_factory,
        "u_web",
        created_at=datetime(2026, 9, 10, 8, 5, 9, tzinfo=UTC),
        channel="web",
        uploaded_by="anna-ik",
        pages_per_file=(3, 2),
        queue=(
            (QueueKind.UNKNOWN, False),
            (QueueKind.UNRESOLVED, False),
            (QueueKind.UNRESOLVED, False),
            (QueueKind.UNREADABLE, True),
        ),
    )

    header = re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", client.get("/uploads").text, re.S)
    (row,) = _rows(client.get("/uploads").text)

    assert header == [
        "Parti",
        "Tarih",
        "Kanal",
        "Yükleyen",
        "Bağlam çalışanı",
        "Dosya",
        "Sayfa",
        "Durum",
        "Tür bilinmiyor",
        "Okunamadı",
        "Sahibi belirsiz",
    ]
    # Çözülmüş Unreadable öğesi sayılmaz; sıfır boş hücredir.
    assert row == [
        "u_web",
        "2026-09-10 08:05:09 UTC",
        "Panel",
        "anna-ik",
        "—",
        "2",
        "5",
        "Tamamlandı",
        "1",
        "",
        "2",
    ]


def test_a_telegram_upload_without_uploader_or_context_shows_dashes_and_its_channel(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(session_factory, "u_bot", channel="telegram", uploaded_by=None)

    (row,) = _rows(client.get("/uploads").text)

    assert row[2:5] == ["Telegram", "—", "—"]
    assert row[5:7] == ["0", "0"]
    assert row[8:] == ["", "", ""]


def test_the_context_employee_links_to_the_profile(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    employee_id = _employee(session_factory, 7, "Ivan", "Petrov")
    _upload(session_factory, "u_ctx", context_employee_id=employee_id)

    page = client.get("/uploads")

    assert '<a href="/employees/E0007">Ivan Petrov</a>' in page.text
    assert _rows(page.text)[0][4] == "Ivan Petrov E0007"


def test_processing_statuses_keep_their_own_names_and_partial_and_failed_are_distinct(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    labels = {
        UploadStatus.RECEIVED: "Alındı",
        UploadStatus.RENDERING: "Sayfalar hazırlanıyor",
        UploadStatus.ANALYZING: "Analiz ediliyor",
        UploadStatus.PLANNING: "Plan hazırlanıyor",
        UploadStatus.EXECUTING: "Plan uygulanıyor",
        UploadStatus.DONE: "Tamamlandı",
        UploadStatus.PARTIAL: "Kısmen tamamlandı",
        UploadStatus.FAILED: "İşlenemedi",
        UploadStatus.CANCELLED: "İptal edildi",
    }
    for number, status in enumerate(labels):
        _upload(
            session_factory,
            f"u_{status.value}",
            status=status,
            created_at=BASE + timedelta(minutes=number),
        )

    rows = {row[0]: row[7] for row in _rows(client.get("/uploads").text)}

    assert rows == {f"u_{status.value}": label for status, label in labels.items()}
    assert len(set(rows.values())) == len(UploadStatus)


def test_the_status_filter_narrows_the_list_and_processing_covers_all_running_states(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    for number, status in enumerate(UploadStatus):
        _upload(
            session_factory,
            f"u_{status.value}",
            status=status,
            created_at=BASE + timedelta(minutes=number),
        )

    processing = {"u_received", "u_rendering", "u_analyzing", "u_planning", "u_executing"}
    assert set(_ids(client.get("/uploads", params={"status": "processing"}).text)) == processing
    assert _ids(client.get("/uploads", params={"status": "done"}).text) == ["u_done"]
    assert _ids(client.get("/uploads", params={"status": "partial"}).text) == ["u_partial"]
    assert _ids(client.get("/uploads", params={"status": "failed"}).text) == ["u_failed"]
    assert _ids(client.get("/uploads", params={"status": "cancelled"}).text) == ["u_cancelled"]
    assert len(_ids(client.get("/uploads", params={"status": ""}).text)) == len(UploadStatus)
    selected = client.get("/uploads", params={"status": "partial"}).text
    assert '<option value="partial" selected>Kısmi</option>' in selected


def test_the_date_range_includes_both_days_in_utc(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    edges = {
        "u_before": datetime(2026, 9, 9, 23, 59, 59, tzinfo=UTC),
        "u_first": datetime(2026, 9, 10, 0, 0, 0, tzinfo=UTC),
        "u_inside": datetime(2026, 9, 11, 13, 0, 0, tzinfo=UTC),
        "u_last": datetime(2026, 9, 12, 23, 59, 59, tzinfo=UTC),
        "u_after": datetime(2026, 9, 13, 0, 0, 0, tzinfo=UTC),
    }
    for upload_id, moment in edges.items():
        _upload(session_factory, upload_id, created_at=moment)

    both = client.get("/uploads", params={"from": "2026-09-10", "to": "2026-09-12"})
    only_from = client.get("/uploads", params={"from": "2026-09-12"})
    only_to = client.get("/uploads", params={"to": "2026-09-10"})
    one_day = client.get("/uploads", params={"from": "2026-09-10", "to": "2026-09-10"})

    assert _ids(both.text) == ["u_last", "u_inside", "u_first"]
    assert _ids(only_from.text) == ["u_after", "u_last"]
    assert _ids(only_to.text) == ["u_first", "u_before"]
    assert _ids(one_day.text) == ["u_first"]
    assert 'name="from" value="2026-09-10"' in both.text
    assert 'name="to" value="2026-09-12"' in both.text


def test_status_and_date_filters_combine(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(session_factory, "u_done_in", status=UploadStatus.DONE, created_at=BASE)
    _upload(session_factory, "u_failed_in", status=UploadStatus.FAILED, created_at=BASE)
    _upload(
        session_factory,
        "u_done_out",
        status=UploadStatus.DONE,
        created_at=BASE - timedelta(days=30),
    )

    page = client.get("/uploads", params={"status": "done", "from": "2026-09-01"})

    assert _ids(page.text) == ["u_done_in"]
    assert "Süzgeci temizle" in page.text


@pytest.mark.parametrize(
    ("params", "warning"),
    [
        ({"status": "bogus"}, "Durum süzgeci tanınmadı"),
        ({"from": "2026-13-45"}, "Başlangıç günü geçerli bir tarih değil"),
        ({"to": "yarin"}, "Bitiş günü geçerli bir tarih değil"),
        ({"from": "2026-09-12", "to": "2026-09-10"}, "tarih süzgeci yok sayıldı"),
    ],
)
def test_an_invalid_filter_is_ignored_with_a_warning_not_an_error(
    client: TestClient,
    session_factory: sessionmaker[Session],
    params: dict[str, str],
    warning: str,
) -> None:
    _upload(session_factory, "u_a", created_at=BASE)
    _upload(
        session_factory, "u_b", created_at=BASE - timedelta(days=90), status=UploadStatus.FAILED
    )

    page = client.get("/uploads", params=params)

    assert page.status_code == 200
    assert warning in page.text
    assert 'role="alert"' in page.text
    assert set(_ids(page.text)) == {"u_a", "u_b"}
    assert "Süzgeci temizle" not in page.text


def test_a_valid_filter_still_applies_next_to_an_invalid_one(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(session_factory, "u_done", status=UploadStatus.DONE)
    _upload(session_factory, "u_failed", status=UploadStatus.FAILED)

    page = client.get("/uploads", params={"status": "failed", "from": "not-a-date"})

    assert _ids(page.text) == ["u_failed"]
    assert "Başlangıç günü geçerli bir tarih değil" in page.text
    assert "Durum süzgeci tanınmadı" not in page.text


def test_the_list_is_paged_by_fifty_and_the_last_page_holds_the_rest(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    assert PAGE_SIZE == 50
    for number in range(PAGE_SIZE + 3):
        _upload(session_factory, f"u_{number:03d}", created_at=BASE + timedelta(minutes=number))

    first = client.get("/uploads")
    second = client.get("/uploads", params={"page": "2"})

    assert len(_ids(first.text)) == PAGE_SIZE
    assert _ids(first.text)[0] == f"u_{PAGE_SIZE + 2:03d}"
    assert _ids(second.text) == ["u_002", "u_001", "u_000"]
    assert "Sayfa 1 / 2" in first.text
    assert '<a href="/uploads?page=2" rel="next">' in first.text
    assert 'rel="prev"' not in first.text
    assert '<a href="/uploads" rel="prev">' in second.text
    assert 'rel="next"' not in second.text
    assert f"{PAGE_SIZE + 3} yükleme" in first.text


def test_exactly_one_full_page_has_no_pager(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    for number in range(PAGE_SIZE):
        _upload(session_factory, f"u_{number:03d}", created_at=BASE + timedelta(minutes=number))

    page = client.get("/uploads")

    assert len(_ids(page.text)) == PAGE_SIZE
    assert 'class="pager"' not in page.text


@pytest.mark.parametrize(
    ("page_value", "expected_first"),
    [
        ("99", "u_000"),
        ("2", "u_000"),
        ("100000000000000000000", "u_000"),
        ("0", "u_050"),
        ("-3", "u_050"),
        ("abc", "u_050"),
        ("", "u_050"),
    ],
)
def test_a_page_number_outside_the_range_gives_the_last_or_first_page(
    client: TestClient,
    session_factory: sessionmaker[Session],
    page_value: str,
    expected_first: str,
) -> None:
    for number in range(PAGE_SIZE + 1):
        _upload(session_factory, f"u_{number:03d}", created_at=BASE + timedelta(minutes=number))

    page = client.get("/uploads", params={"page": page_value})

    assert page.status_code == 200
    assert _ids(page.text)[0] == expected_first


def test_page_links_keep_the_valid_filters_only(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    for number in range(PAGE_SIZE + 1):
        _upload(session_factory, f"u_{number:03d}", created_at=BASE + timedelta(minutes=number))

    page = client.get("/uploads", params={"status": "done", "from": "2026-09-01", "to": "nope"})

    assert '<a href="/uploads?status=done&amp;from=2026-09-01&amp;page=2" rel="next">' in page.text
    second = client.get("/uploads", params={"status": "done", "from": "2026-09-01", "page": "2"})
    assert '<a href="/uploads?status=done&amp;from=2026-09-01" rel="prev">' in second.text


def test_page_links_keep_the_end_day_too(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    for number in range(PAGE_SIZE + 1):
        _upload(session_factory, f"u_{number:03d}", created_at=BASE + timedelta(minutes=number))

    page = client.get("/uploads", params={"from": "2026-09-01", "to": "2026-09-30"})

    assert (
        '<a href="/uploads?from=2026-09-01&amp;to=2026-09-30&amp;page=2" rel="next">' in page.text
    )


def test_an_empty_list_says_so_and_links_to_the_upload_page(client: TestClient) -> None:
    page = client.get("/uploads")

    assert page.status_code == 200
    assert "Henüz yükleme yok" in page.text
    assert '<a href="/upload">Yükle</a>' in page.text
    assert "<table" not in page.text
    assert "henüz hazır değil" not in page.text


def test_a_filter_that_matches_nothing_says_so_and_offers_to_clear_it(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(session_factory, "u_done", status=UploadStatus.DONE)

    page = client.get("/uploads", params={"status": "failed"})

    assert "Bu süzgece uyan yükleme yok" in page.text
    assert "Henüz yükleme yok" not in page.text
    assert '<a href="/upload">Yükle</a>' in page.text
    assert '<a href="/uploads">Süzgeci temizle</a>' in page.text


def test_the_page_needs_a_session(app: FastAPI, client: TestClient) -> None:
    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app, follow_redirects=False)

    response = anonymous.get("/uploads")

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_the_menu_marks_uploads_active(client: TestClient) -> None:
    page = client.get("/uploads")

    assert '<a href="/uploads" class="active" aria-current="page">Yüklemeler</a>' in page.text


def test_file_names_and_stored_paths_never_appear(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(session_factory, "u_secret", pages_per_file=(1, 1))

    page = client.get("/uploads")

    assert "Petrov" not in page.text
    assert SECRET_FILE_NAME not in page.text
    assert "Inbox/" not in page.text
    assert _rows(page.text)[0][5:7] == ["2", "2"]


def test_the_page_is_escaped(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    _upload(session_factory, "u_x", uploaded_by="<script>alert(1)</script>")

    page = client.get("/uploads", params={"status": "<script>alert(2)</script>"})

    assert "<script>alert" not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text


def test_listing_reads_only_and_writes_no_event(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(session_factory, "u_a", pages_per_file=(2,), queue=((QueueKind.UNKNOWN, False),))

    client.get("/uploads")
    client.get("/uploads", params={"status": "bogus", "page": "9"})

    with session_factory() as session:
        assert session.scalar(select(func.count(Event.id))) == 0
        assert session.scalar(select(func.count(Upload.id))) == 1
        assert session.scalar(select(func.count(QueueItem.id))) == 1


def test_the_number_of_queries_does_not_grow_with_the_number_of_rows(
    client: TestClient, session_factory: sessionmaker[Session], engine: Engine
) -> None:
    def _statements(path: str) -> int:
        seen: list[str] = []

        def _record(_conn: object, _cursor: object, statement: str, *_rest: object) -> None:
            seen.append(statement)

        event.listen(engine, "before_cursor_execute", _record)
        try:
            assert client.get(path).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", _record)
        return len(seen)

    employee_id = _employee(session_factory, 1, "Anna", "Weber")
    for number in range(3):
        _upload(
            session_factory,
            f"u_a{number}",
            created_at=BASE + timedelta(minutes=number),
            context_employee_id=employee_id,
            pages_per_file=(2, 1),
            queue=((QueueKind.UNKNOWN, False), (QueueKind.UNRESOLVED, True)),
        )
    few = _statements("/uploads")

    for number in range(30):
        _upload(
            session_factory,
            f"u_b{number}",
            created_at=BASE + timedelta(hours=1, minutes=number),
            context_employee_id=employee_id,
            pages_per_file=(2, 1, 4),
            queue=((QueueKind.UNREADABLE, False),),
        )
    many = _statements("/uploads")

    assert few == many
    # Sayım, liste ve SQLite'ın `BEGIN IMMEDIATE`'i; 10.3.7'nin süre aşımı denetimi tek sorgudur.
    assert many <= 4


# --- 10.3.4: yoksayılan partiler ------------------------------------------------------------------


def _dismiss(session_factory: sessionmaker[Session], upload_id: str) -> None:
    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        upload.dismissed_at = BASE + timedelta(hours=1)
        upload.dismissed_by = "test-yonetici"
        session.commit()


def test_a_dismissed_upload_is_hidden_by_default_and_shown_by_the_filter(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(session_factory, "u_kept", created_at=BASE)
    _upload(session_factory, "u_gone", created_at=BASE - timedelta(days=1))
    _dismiss(session_factory, "u_gone")

    default = client.get("/uploads")
    only = client.get("/uploads", params={"dismissed": "only"})
    both = client.get("/uploads", params={"dismissed": "include"})

    assert _ids(default.text) == ["u_kept"]
    assert "1 yükleme" in default.text
    assert "Yoksayıldı</span>" not in default.text
    assert '<option value="">Gizle</option>' in default.text
    assert _ids(only.text) == ["u_gone"]
    assert "Tamamlandı Yoksayıldı" in _rows(only.text)[0]
    assert '<option value="only" selected>Yalnız yoksayılanlar</option>' in only.text
    assert "Süzgeci temizle" in only.text
    assert _ids(both.text) == ["u_kept", "u_gone"]
    assert [row[7] for row in _rows(both.text)] == ["Tamamlandı", "Tamamlandı Yoksayıldı"]


def test_the_dismissed_filter_combines_with_status_and_an_invalid_value_warns(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(session_factory, "u_done", status=UploadStatus.DONE)
    _upload(session_factory, "u_failed", status=UploadStatus.FAILED)
    _upload(session_factory, "u_failed_gone", status=UploadStatus.FAILED)
    _dismiss(session_factory, "u_failed_gone")

    combined = client.get("/uploads", params={"status": "failed", "dismissed": "include"})
    invalid = client.get("/uploads", params={"dismissed": "hepsi"})

    assert set(_ids(combined.text)) == {"u_failed", "u_failed_gone"}
    assert invalid.status_code == 200
    assert "Yoksayılanlar süzgeci tanınmadı; yok sayıldı." in invalid.text
    assert set(_ids(invalid.text)) == {"u_done", "u_failed"}


def test_page_links_keep_the_dismissed_filter(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    for number in range(PAGE_SIZE + 1):
        upload_id = f"u_{number:03d}"
        _upload(session_factory, upload_id, created_at=BASE + timedelta(minutes=number))
        _dismiss(session_factory, upload_id)

    page = client.get("/uploads", params={"dismissed": "only"})

    assert '<a href="/uploads?dismissed=only&amp;page=2" rel="next">' in page.text
    assert "Henüz yükleme yok." in client.get("/uploads").text  # hepsi yoksayıldı
