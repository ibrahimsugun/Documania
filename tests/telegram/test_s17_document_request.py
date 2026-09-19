"""S17 — Telegram: iki ehliyet / tek ehliyet → seçim sorusu / dosya gönderilir (PRD §9; 12.3).

Uçtan uca: ehliyetler bota belge olarak gönderilir, web ile aynı boru hattından (12.2.1) geçip
çalışanın `Hazir/` klasörüne yazılır; sonra İK bota "Ahmet Çakar'ın ehliyetini göster" yazar.
Yapay zekâ canlı çağrılmaz: sayfa analizleri ve isteğin okunması tek kayıt dizininden, çağrı
sırasıyla gelir (`RecordingProvider`). Kişi ve belge numaraları kurgusaldır, belgeler sentetiktir
(CONVENTIONS §6).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.recording_provider import RecordingProvider
from app.db.models import AccessLog, Document, Employee, TelegramUser
from app.storage import DataLayout
from tests.fixtures.gen import (
    SyntheticPage,
    SyntheticPerson,
    batch_responses,
    driving_license_pages,
    make_document_pdf_bytes,
    write_recordings,
)
from tests.telegram.conftest import (
    LISTED_ID,
    IntakeBot,
    callback_update,
    document_update,
    message_update,
)

PERSON_CAKAR = SyntheticPerson("ÇAKAR", "AHMET", date(1988, 4, 12), "TUR", "M")
FIRST_NUMBER = "00 0000171"
SECOND_NUMBER = "00 0000172"
REQUEST = "Ahmet Çakar'ın ehliyetini göster"
# Mesajın kayıtlı okuması: tek kişi, "ehliyet" → katalogdaki tek ehliyet türü.
QUERY: dict[str, Any] = {
    "intent": "find_documents",
    "people": ["Ahmet Çakar"],
    "document_kind": "ehliyet",
    "document_types": ["serbian_driving_license"],
}


def license_pages(number: str) -> Sequence[SyntheticPage]:
    return driving_license_pages(
        PERSON_CAKAR, document_number=number, expiry_date=date(2032, 1, 31)
    )


def licenses(session_factory: sessionmaker[Session]) -> list[Document]:
    with session_factory() as session:
        return list(session.scalars(select(Document).order_by(Document.id)))


def access_rows(session_factory: sessionmaker[Session]) -> list[tuple[int, int, str, str]]:
    with session_factory() as session:
        return [
            (row.user_id, row.document_id, row.action, row.channel)
            for row in session.scalars(select(AccessLog).order_by(AccessLog.id))
        ]


def stored_bytes(layout: DataLayout | None, document: Document) -> bytes:
    assert layout is not None
    return layout.resolve(document.path).read_bytes()


def test_s17_one_license_is_sent_and_two_licenses_ask_which_one(
    make_request_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    whitelist: Callable[..., None],
    tmp_path: Path,
) -> None:
    whitelist(LISTED_ID)
    first, second = license_pages(FIRST_NUMBER), license_pages(SECOND_NUMBER)
    recordings = [*batch_responses(first), QUERY, *batch_responses(second), QUERY]
    provider = RecordingProvider.from_directory(write_recordings(tmp_path / "kayit", recordings))
    bot = make_request_bot(provider)
    bot.telegram.files.update(
        {"ehliyet-1": make_document_pdf_bytes(first), "ehliyet-2": make_document_pdf_bytes(second)}
    )
    with session_factory() as session:
        user_id = session.get_one(TelegramUser, LISTED_ID).user_id

    # Ehliyet bota belge olarak gelir, boru hattından geçer: çalışan açılır, ehliyet Hazir'da.
    bot.feed(document_update(1, LISTED_ID, "ehliyet-1", "ehliyet.pdf"))
    (only,) = licenses(session_factory)
    with session_factory() as session:
        employee = session.get_one(Employee, only.employee_id)
    assert (employee.given_names, employee.surname) == ("AHMET", "ÇAKAR")
    assert (only.type_slug, only.status) == ("serbian_driving_license", "active")

    # S17 tek ehliyet → dosya gönderilir: Hazir'daki dosyanın baytları, belge olarak.
    bot.feed(message_update(2, LISTED_ID, REQUEST))
    assert bot.telegram.uploads == [(Path(only.path).name, stored_bytes(bot.layout, only))]
    assert access_rows(session_factory) == [(user_id, only.id, "download", "telegram")]

    # İkinci ehliyet aynı kişinin (ad + doğum tarihi, K6): aynı çalışanın Hazir'ına `-2` ekiyle.
    bot.feed(document_update(3, LISTED_ID, "ehliyet-2", "ehliyet.pdf"))
    older, newer = licenses(session_factory)
    assert newer.employee_id == employee.id and newer.status == "active"
    assert Path(newer.path).name == Path(older.path).stem + "-2.pdf"

    # S17 iki ehliyet → seçim sorusu: iki seçenek, hiçbir belge gönderilmez, kayıt düşmez.
    bot.feed(message_update(4, LISTED_ID, REQUEST))
    question = bot.telegram.sent("sendMessage")[-1]
    assert question["text"].splitlines()[0] == (
        f"AHMET ÇAKAR ({employee.id}) için 2 ehliyet bulundu. Hangisini istiyorsunuz?"
    )
    options = [button for row in question["reply_markup"]["inline_keyboard"] for button in row]
    assert [button["text"] for button in options] == [
        f"1. {Path(newer.path).name}",
        f"2. {Path(older.path).name}",
    ]
    assert len(bot.telegram.uploads) == 1
    assert len(access_rows(session_factory)) == 1

    # Seçilen ehliyet (yenisi) gönderilir ve erişim loguna yazılır.
    bot.feed(callback_update(5, LISTED_ID, options[0]["callback_data"]))
    assert bot.telegram.uploads[-1] == (Path(newer.path).name, stored_bytes(bot.layout, newer))
    assert access_rows(session_factory) == [
        (user_id, only.id, "download", "telegram"),
        (user_id, newer.id, "download", "telegram"),
    ]
    # Yapay zekâ iki ehliyetin dört sayfasını analiz etti ve iki isteği okudu — hepsi kayıtlı.
    assert (len(provider.requests), len(provider.query_requests)) == (4, 2)
    assert all(REQUEST in request.prompt for request in provider.query_requests)
