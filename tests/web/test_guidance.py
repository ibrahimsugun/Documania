"""10.11.2 — bekleyen işte yol gösterme (PLAN.md §D120 d, e; tm 176).

Parti detayının "Kuyruğa alınanlar" satırı kuyruk öğesine, Unknown satırı bağlı aday türe bağlanır;
"Çözüm" sütunu "Bekliyor" yerine yapılacak işi söyler. Kuyruk öğesi sayfası kuyruk türüne göre
önerilen adımları sırayla, sayfadaki bölüme çapalı gösterir; kuyruk sekmesi tek cümlelik ipucu
taşır; boş durumlar ilk adıma bağlanır. Salt okunur Kullanıcı (10.1.8) yazma bağlantısı ve adımı
görmez, "İK'ya bildirin" ipucunu görür. Eski plan sürümünün satırı bağlantı ve ipucu almaz;
çözülmüş öğe ne yapılacağını değil çözümünü söyler.

Satırlar elle yazılan sentetik kayıtlardır (kişi ve belge yok); aday türün sayfası ve kuyruk öğesi
arasındaki bağ 11.5.3'ün ilişkisidir (ilk kaynak sayfası adayın örnek sayfası). Gerçek boru hattıyla
uçtan uca akış S28'dedir (`tests/test_scenario_s28.py`).
"""

from __future__ import annotations

import re
from html import escape, unescape
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    CandidateDocumentType,
    CandidateTypeStatus,
    Page,
    QueueItem,
    QueueKind,
    QueueResolution,
    UserRole,
)
from app.i18n import gettext, use_language
from app.web.auth import PanelUser, get_current_user
from app.web.feedback import HINTS, placeholders
from app.web.guidance import (
    TAB_HINTS,
    Step,
    candidates_of,
    first_page,
    item_steps,
    resolution_hint,
)
from tests.i18n.residue import turkish_residue
from tests.web.conftest import SIGNED_IN
from tests.web.test_queue_page import (
    _payload,
    _plan,
    _queue_item,
    _source_file,
    _upload,
)

READER = PanelUser(SIGNED_IN.id, SIGNED_IN.username, UserRole.USER.value)
UPLOAD_ID = "u_20991231_7"
PASSPORT = "russian_passport"
CANDIDATE_NAME = "Peruvian Diploma"

APPROVE = "Aday türü onaylayın ya da öğeyi kapatın."
APPROVED = "Aday tür onaylandı: partiyi yeniden analiz edin ya da öğeyi kapatın."
NO_CANDIDATE = "Türü kataloğa ekleyip partiyi yeniden analiz edin ya da öğeyi kapatın."
UNREADABLE = "Daha net bir kopyayı yeniden yükleyin, öğeyi çalışana atayın ya da kapatın."
UNRESOLVED = "Çalışana atayın ya da öğeyi kapatın."
TYPELESS = "Belgeyi uygun biçimde yeniden yükleyin ya da öğeyi kapatın."
SUPERSEDED = "Eski sürüm: işlem gerekmez."
TELL_HR = "İK'nın kararını bekliyor; bir sorun görürseniz İK'ya bildirin."
ITEM_TELL_HR = (
    "Bu öğe İK'nın kararını bekliyor. Hesabınız salt okunur; bir sorun görürseniz İK'ya bildirin."
)


def _candidate(
    session: Session, upload_id: str, page: Page, status: CandidateTypeStatus, name: str
) -> CandidateDocumentType:
    candidate = CandidateDocumentType(
        proposed_name=name,
        normalized_name=name.casefold(),
        first_seen_upload_id=upload_id,
        sample_page_ids=[page.id],
        seen_count=1,
        status=status.value,
    )
    session.add(candidate)
    session.flush()
    return candidate


def _page(session: Session, file_id: int, index: int) -> Page:
    page = session.query(Page).filter_by(file_id=file_id, index=index).one()
    return page


def _batch(session_factory: sessionmaker[Session]) -> dict[str, int]:
    """Bir parti, iki plan sürümü; güncel planda her kuyruk türünden bekleyen öğe, çözülmüş bir öğe
    ve eski sürümde çözülmemiş bir öğe. Unknown öğesinin ilk sayfası bekleyen adayın örneğidir."""
    with session_factory() as session:
        upload = _upload(session, UPLOAD_ID)
        old, current = _plan(session, upload, 1), _plan(session, upload, 2)
        source = _source_file(session, upload, "scan.pdf", page_count=6)
        candidate = _candidate(
            session, upload.id, _page(session, source.id, 0), CandidateTypeStatus.PENDING, "Dip"
        )
        ids = {
            "candidate": candidate.id,
            "unknown": _queue_item(
                session, upload, current, QueueKind.UNKNOWN, payload=_payload(source.id, [0])
            ).id,
            "unreadable": _queue_item(
                session,
                upload,
                current,
                QueueKind.UNREADABLE,
                item_id="i2",
                payload=_payload(source.id, [1], slug=PASSPORT),
            ).id,
            "unresolved": _queue_item(
                session,
                upload,
                current,
                QueueKind.UNRESOLVED,
                item_id="i3",
                payload=_payload(source.id, [2], slug=PASSPORT),
            ).id,
            "typeless": _queue_item(
                session,
                upload,
                current,
                QueueKind.UNRESOLVED,
                item_id="i4",
                payload=_payload(source.id, [3]),
            ).id,
            "resolved": _queue_item(
                session,
                upload,
                current,
                QueueKind.UNRESOLVED,
                item_id="i5",
                payload=_payload(source.id, [4], slug=PASSPORT),
                resolved_by="test-yonetici",
            ).id,
            "superseded": _queue_item(
                session,
                upload,
                old,
                QueueKind.UNRESOLVED,
                payload=_payload(source.id, [5], slug=PASSPORT),
            ).id,
        }
        session.get_one(QueueItem, ids["resolved"]).resolution = QueueResolution.CLOSED.value
        session.get_one(QueueItem, ids["resolved"]).resolution_reason = "not_a_document"
        session.commit()
    return ids


@pytest.fixture
def batch(session_factory: sessionmaker[Session]) -> dict[str, int]:
    return _batch(session_factory)


def _row(html: str, item_id: int) -> str:
    match = re.search(rf'<tr id="queue-{item_id}".*?</tr>', html, re.S)
    assert match is not None, item_id
    return unescape(match.group(0))


def _steps(html: str) -> list[tuple[str, str]]:
    section = re.search(r'<section id="next-steps".*?</section>', html, re.S)
    if section is None:
        return []
    return [
        (url, unescape(text))
        for url, text in re.findall(r'<li><a href="([^"]+)">(.*?)</a></li>', section.group(0))
    ]


def _read_only(app: FastAPI) -> None:
    app.dependency_overrides[get_current_user] = lambda: READER


# --- parti detayı: "Kuyruğa alınanlar" ---------------------------------------------------------


def test_each_queued_row_links_to_its_item_and_says_what_to_do_by_queue_kind(
    client: TestClient, batch: dict[str, int]
) -> None:
    html = client.get(f"/uploads/{UPLOAD_ID}").text

    unknown = _row(html, batch["unknown"])
    assert f'<a href="/queues/{batch["unknown"]}">Tür bilinmiyor</a>' in unknown
    assert APPROVE in unknown
    candidate_link = (
        f'<a class="candidate-link" href="/document-types/candidate-types/{batch["candidate"]}">'
        'Aday tür: <span translate="no">Dip</span></a>'
    )
    assert candidate_link in unknown
    unreadable = _row(html, batch["unreadable"])
    assert f'<a href="/queues/{batch["unreadable"]}">Okunamadı</a>' in unreadable
    assert UNREADABLE in unreadable
    assert UNRESOLVED in _row(html, batch["unresolved"])
    assert TYPELESS in _row(html, batch["typeless"])
    table = re.search(r'<table class="queue">.*?</table>', html, re.S)
    assert table is not None and "Bekliyor" not in table.group(0)


def test_a_resolved_row_tells_its_resolution_not_what_to_do(
    client: TestClient, batch: dict[str, int]
) -> None:
    row = _row(client.get(f"/uploads/{UPLOAD_ID}").text, batch["resolved"])

    assert f'<a href="/queues/{batch["resolved"]}">' in row
    assert "test-yonetici" in row
    assert 'class="next-step"' not in row
    assert "candidate-link" not in row


def test_an_old_version_row_gets_neither_link_nor_hint(
    client: TestClient, batch: dict[str, int]
) -> None:
    row = _row(client.get(f"/uploads/{UPLOAD_ID}").text, batch["superseded"])

    assert 'class="output-superseded"' in row
    assert "<td>Sahibi belirsiz</td>" in row
    assert "/queues/" not in row
    assert SUPERSEDED in row
    assert "atayın" not in row


def test_an_approved_candidate_says_reanalyze_and_a_rejected_one_gives_no_link(
    client: TestClient, session_factory: sessionmaker[Session], batch: dict[str, int]
) -> None:
    def candidate_status(status: CandidateTypeStatus) -> str:
        with session_factory() as session:
            session.get_one(CandidateDocumentType, batch["candidate"]).status = status.value
            session.commit()
        return _row(client.get(f"/uploads/{UPLOAD_ID}").text, batch["unknown"])

    approved = candidate_status(CandidateTypeStatus.APPROVED)
    assert APPROVED in approved
    assert f'href="/document-types/candidate-types/{batch["candidate"]}"' in approved

    rejected = candidate_status(CandidateTypeStatus.REJECTED)
    assert NO_CANDIDATE in rejected
    assert "candidate-link" not in rejected


def test_a_read_only_user_sees_no_approval_link_and_is_told_to_tell_hr(
    app: FastAPI, client: TestClient, batch: dict[str, int]
) -> None:
    _read_only(app)

    html = client.get(f"/uploads/{UPLOAD_ID}").text

    unknown = _row(html, batch["unknown"])
    assert TELL_HR in unknown
    assert "/document-types/candidate-types" not in html
    assert APPROVE not in html and UNRESOLVED not in html
    # Okuma bağlantısı kalır: kuyruk öğesi Kullanıcı'ya açıktır.
    assert f'<a href="/queues/{batch["unknown"]}">' in unknown
    assert SUPERSEDED in _row(html, batch["superseded"])


# --- kuyruk öğesi: önerilen adımlar --------------------------------------------------------------


def test_the_item_page_lists_ordered_anchored_steps_by_queue_kind(
    client: TestClient, batch: dict[str, int]
) -> None:
    candidate = f"/document-types/candidate-types/{batch['candidate']}"
    close = ("#close", "Belge değilse ya da sistemde zaten varsa öğeyi gerekçeyle kapatın.")

    unknown = client.get(f"/queues/{batch['unknown']}").text
    assert _steps(unknown) == [
        (candidate, "Önerilen aday türü inceleyip onaylayın."),
        (candidate, "Onaydan sonra aday türün sayfasından bu partiyi yeniden analiz edin."),
        close,
    ]
    assert '<h2 id="next-steps-title">Önerilen adımlar</h2>' in unknown

    unreadable = client.get(f"/queues/{batch['unreadable']}").text
    assert _steps(unreadable) == [
        ("#sources", "Gerekçede okunamayan alan yazar; kaynak sayfalara bakın."),
        ("#assign", "Belgenin sahibi kayıtlı bir çalışansa ona atayın."),
        ("/upload", "Daha net ya da uygun biçimde bir kopya gerekiyorsa yeniden yükleyin."),
        close,
    ]
    for anchor in ('id="sources"', 'id="assign"', 'id="close"'):
        assert anchor in unreadable

    unresolved = client.get(f"/queues/{batch['unresolved']}").text
    assert _steps(unresolved) == [
        ("#assign", "Belgenin sahibi kayıtlı bir çalışansa ona atayın."),
        close,
    ]
    typeless = client.get(f"/queues/{batch['typeless']}").text
    assert _steps(typeless) == [
        ("/upload", "Daha net ya da uygun biçimde bir kopya gerekiyorsa yeniden yükleyin."),
        close,
    ]


def test_an_unknown_item_without_a_candidate_points_to_the_catalog_and_its_batch(
    client: TestClient, session_factory: sessionmaker[Session], batch: dict[str, int]
) -> None:
    with session_factory() as session:
        session.get_one(
            CandidateDocumentType, batch["candidate"]
        ).status = CandidateTypeStatus.REJECTED.value
        session.commit()

    steps = _steps(client.get(f"/queues/{batch['unknown']}").text)

    assert [url for url, _ in steps] == [
        "/document-types/new",
        f"/uploads/{UPLOAD_ID}#actions",
        "#close",
    ]


def test_resolved_and_old_version_items_say_no_steps(
    client: TestClient, batch: dict[str, int]
) -> None:
    for key in ("resolved", "superseded"):
        html = client.get(f"/queues/{batch[key]}").text
        assert 'id="next-steps"' not in html, key
        assert "Önerilen adımlar" not in html, key


def test_a_read_only_user_gets_no_steps_but_the_tell_hr_hint(
    app: FastAPI, client: TestClient, batch: dict[str, int]
) -> None:
    _read_only(app)

    html = client.get(f"/queues/{batch['unknown']}").text

    assert _steps(html) == []
    assert ITEM_TELL_HR in unescape(html)
    assert "/document-types/candidate-types" not in html
    assert ITEM_TELL_HR not in unescape(client.get(f"/queues/{batch['resolved']}").text)


# --- kuyruk listesi ve boş durumlar ------------------------------------------------------------


@pytest.mark.parametrize("kind", list(QueueKind))
def test_each_queue_tab_opens_with_a_one_sentence_hint_for_its_role(
    app: FastAPI, client: TestClient, kind: QueueKind
) -> None:
    writer, reader = (unescape(escape(text)) for text in TAB_HINTS[kind.value])
    for text in (writer, reader):
        assert text.count(". ") == 0 and text.endswith(".")

    assert writer in unescape(client.get(f"/queues?tab={kind.value}").text)
    _read_only(app)
    html = unescape(client.get(f"/queues?tab={kind.value}").text)
    assert reader in html and writer not in html
    assert "İK'ya bildirin" in reader


def test_empty_states_link_to_the_first_step_by_permission(
    app: FastAPI, client: TestClient
) -> None:
    queue = client.get("/queues").text
    assert '<a href="/uploads">Yüklemelere bakın</a>' in queue
    assert '<a href="/upload">İlk belgeleri yükleyin</a>' in client.get("/employees").text
    assert '<a href="/document-types/new">Yeni tür</a>' in client.get("/document-types").text
    candidates = client.get("/document-types/candidate-types").text
    assert '<a href="/queues?tab=unknown">Unknown kuyruğuna bakın</a>' in candidates

    _read_only(app)
    assert '<a href="/uploads">Yüklemelere bakın</a>' in client.get("/queues").text
    assert 'href="/upload"' not in client.get("/employees").text
    assert 'href="/document-types/new"' not in client.get("/document-types").text


# --- kayıt ve bağ ---------------------------------------------------------------------------


def test_hints_carry_no_placeholder_and_never_suggest_editing_content() -> None:
    # R12, K17: ipucu belge içeriğini değiştiren yol önermez; root'a özel erişim logu ipucunda yok.
    forbidden = ("düzenle", "düzelt", "doldur", "girin", "değiştir", "erişim log")
    for key, text in HINTS.items():
        assert not placeholders(text), key
        assert not any(word in text.casefold() for word in forbidden), key


@pytest.mark.parametrize("language", ["en", "sr"])
def test_every_hint_speaks_the_chosen_language(language: str) -> None:
    failures = []
    with use_language(language):
        for key, text in HINTS.items():
            shown = gettext(text)
            residue = turkish_residue(f"<p>{escape(shown)}</p>", language)
            if shown == text or residue:
                failures.append(f"{key}: {residue or 'çevrilmedi'}")
    assert not failures, "\n".join(failures)


def test_the_link_prefers_a_pending_candidate_and_ignores_a_rejected_one(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        upload = _upload(session, UPLOAD_ID)
        plan = _plan(session, upload, 1)
        source = _source_file(session, upload, "scan.pdf", page_count=2)
        first, second = _page(session, source.id, 0), _page(session, source.id, 1)
        approved = _candidate(session, upload.id, first, CandidateTypeStatus.APPROVED, "A")
        pending = _candidate(session, upload.id, first, CandidateTypeStatus.PENDING, "B")
        _candidate(session, upload.id, second, CandidateTypeStatus.REJECTED, "C")
        items = [
            _queue_item(session, upload, plan, QueueKind.UNKNOWN, payload=payload)
            for payload in (
                _payload(source.id, [0, 1]),
                _payload(source.id, [1]),
                {"sources": "bozuk"},
            )
        ]
        unreadable = _queue_item(
            session, upload, plan, QueueKind.UNREADABLE, payload=_payload(source.id, [0])
        )

        linked = candidates_of(session, [*items, unreadable])

        assert {item_id: row.id for item_id, row in linked.items()} == {items[0].id: pending.id}
        session.get_one(CandidateDocumentType, pending.id).status = "rejected"
        session.flush()
        assert candidates_of(session, items)[items[0].id].id == approved.id
        assert resolution_hint(items[0], approved) == HINTS["resolve.unknown_approved"]
        assert resolution_hint(items[1], None) == HINTS["resolve.unknown"]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"sources": [{"file_id": 4, "pages": [2, 3]}]}, (4, 2)),
        ({"sources": [{"file_id": 4, "pages": []}]}, None),
        ({"sources": [{"file_id": True, "pages": [1]}]}, None),
        ({"sources": [{"file_id": 4, "pages": ["1"]}]}, None),
        ({"sources": []}, None),
        (None, None),
    ],
    ids=["ilk", "sayfasiz", "bool", "metin", "bos", "yok"],
)
def test_first_page_reads_only_a_well_formed_first_source(payload: Any, expected: object) -> None:
    assert first_page(payload) == expected


def test_a_pending_profile_comes_first_and_the_close_step_last() -> None:
    item = QueueItem(
        id=1, upload_id=UPLOAD_ID, kind=QueueKind.UNRESOLVED.value, reason="", payload_json={}
    )

    steps = item_steps(item, None, can_profile=True, can_assign=True, can_close=True)
    assert [step.url for step in steps] == ["#new-profile", "#assign", "#close"]
    assert item_steps(item, None, can_profile=False, can_assign=False, can_close=False) == [
        Step(HINTS["step.reupload"], "/upload")
    ]
    profile = QueueItem(
        id=2,
        upload_id=UPLOAD_ID,
        kind=QueueKind.UNRESOLVED.value,
        reason="",
        payload_json=_payload(
            1,
            [0],
            slug=PASSPORT,
            guess={"action": "pending", "employee_id": None, "matched_by": None},
        ),
    )
    assert resolution_hint(profile, None) == HINTS["resolve.unresolved_profile"]
