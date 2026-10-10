"""PRD §5.3 — Faz 2 yeniden kapanış denetimi (tm 172): KF2'den sonra gelen bot değişiklikleri
kapanış ölçütünü bozmuyor.

- Beyaz liste ↔ her mesaja yanıt (12.1.11, 12.1.13, 12.1.10, 12.1.12): listede olmayan, izni
  kapalı, kaydı silinen ve panel kullanıcısı pasif olan hesaba hiçbir mesaj türü için yanıt,
  `typing` eylemi, dosya indirme ya da yapay zekâ çağrısı gitmez; dil ve sayaç belleğine de
  yazılmaz.
- Konu dışı sayaçla susturulan kişinin gönderdiği belge yine boru hattından Hazir'a girer
  (PLAN.md §D110 "Profil sorusu" d).
- Salt okunur Kullanıcı (10.1.8, §D115 f, §D118 h) belge isteyebilir — S17'nin tek ehliyet kolu
  Hazir'daki baytları gönderir ve erişim loguna yazar — ama belge gönderemez.

Yapay zekâ canlı çağrılmaz (`QueryProvider`, `RecordingProvider`); belgeler sentetiktir.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.recording_provider import RecordingProvider
from app.db.models import Employee, TelegramUser, Upload, User
from app.i18n import gettext
from app.telegram import intent
from app.telegram.handlers import READ_ONLY_TEXT
from app.telegram.whitelist import remove_telegram_id
from tests.fixtures.gen import batch_responses, make_document_pdf_bytes, write_recordings
from tests.telegram.conftest import (
    LISTED_ID,
    OTHER_ID,
    IntakeBot,
    callback_update,
    document_update,
    message_update,
)
from tests.telegram.test_document_requests import QueryProvider, query
from tests.telegram.test_s17_document_request import (
    FIRST_NUMBER,
    QUERY,
    REQUEST,
    access_rows,
    license_pages,
    licenses,
    stored_bytes,
)

OFF_TOPIC: dict[str, Any] = {
    "intent": "off_topic",
    "people": [],
    "documents": [],
    "group": None,
    "group_ids": [],
    "language": "tr",
}


def _media(update_id: int, **content: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "message_id": update_id,
        "date": 1_700_000_000,
        "chat": {"id": LISTED_ID, "type": "private"},
        "from": {"id": LISTED_ID, "is_bot": False, "first_name": "Deneme"},
        **content,
    }
    return {"update_id": update_id, "message": body}


# KF2'den sonra yanıt yolu kazanan bütün mesaj türleri (12.1.11 yedekleri, 12.1.13 konu dışı
# metin, 12.3 istekleri ve `typing`, düğme) ve belge gönderimi.
EVERY_KIND: list[dict[str, Any]] = [
    _media(1, voice={"file_id": "v", "file_unique_id": "uv", "duration": 3}),
    _media(2, audio={"file_id": "a", "file_unique_id": "ua", "duration": 3}),
    _media(
        3,
        sticker={
            "file_id": "s",
            "file_unique_id": "us",
            "type": "regular",
            "width": 1,
            "height": 1,
            "is_animated": False,
            "is_video": False,
        },
    ),
    _media(4, location={"latitude": 44.8, "longitude": 20.4}),
    _media(
        5,
        video={"file_id": "x", "file_unique_id": "ux", "width": 1, "height": 1, "duration": 1},
    ),
    _media(6, contact={"phone_number": "000", "first_name": "Deneme"}),
    message_update(7, LISTED_ID, "/bilinmeyen"),
    message_update(8, LISTED_ID, "/yardim"),
    message_update(9, LISTED_ID, "hava nasıl"),
    message_update(10, LISTED_ID, "Ahmet Çakar'ın ehliyetini göster"),
    message_update(11, LISTED_ID, "How old is Ahmet Çakar?"),
    callback_update(12, LISTED_ID, "sec:abcdefghijkl:0"),
    document_update(13, LISTED_ID, "f1", "pasaport.pdf"),
]


def _not_listed(session_factory: sessionmaker[Session], whitelist: Callable[..., None]) -> None:
    whitelist(OTHER_ID)  # liste boş değil; gönderenin kaydı yok


def _allowed_false(session_factory: sessionmaker[Session], whitelist: Callable[..., None]) -> None:
    whitelist(LISTED_ID, allowed=False)


def _deleted(session_factory: sessionmaker[Session], whitelist: Callable[..., None]) -> None:
    # 12.1.10: kayıt panelden silinir (listeden çıkarılan hesap kolu).
    whitelist(LISTED_ID)
    with session_factory() as session:
        owner_id = session.get_one(TelegramUser, LISTED_ID).user_id
        remove_telegram_id(session, owner_id, LISTED_ID, actor="test")
        session.commit()
    with session_factory() as session:
        assert session.get(TelegramUser, LISTED_ID) is None


def _inactive_panel_user(
    session_factory: sessionmaker[Session], whitelist: Callable[..., None]
) -> None:
    whitelist(LISTED_ID)
    with session_factory() as session:
        session.get_one(TelegramUser, LISTED_ID).user.active = False
        session.commit()


@pytest.mark.parametrize(
    "setup",
    [_not_listed, _allowed_false, _deleted, _inactive_panel_user],
    ids=["listede-yok", "izin-kapali", "kaydi-silindi", "panel-kullanicisi-pasif"],
)
def test_no_kind_of_message_from_an_account_off_the_list_gets_anything_back(
    make_request_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    whitelist: Callable[..., None],
    setup: Callable[..., None],
) -> None:
    setup(session_factory, whitelist)
    provider = QueryProvider(*(query("Ahmet Çakar") for _ in EVERY_KIND))
    bot = make_request_bot(provider)
    bot.telegram.files["f1"] = b"%PDF-1.4 sentetik"

    bot.feed(*EVERY_KIND)

    # Ne yanıt, ne `typing`, ne düğme yanıtı, ne dosya indirme.
    assert bot.telegram.methods() == []
    assert provider.queries == []
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Upload)) == 0
    assert bot.requests is not None
    conversations = bot.requests.conversations
    assert conversations.language(LISTED_ID) is None
    assert not conversations.muted(LISTED_ID)


def test_a_muted_senders_license_still_goes_through_the_pipeline_into_hazir(
    make_request_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    whitelist: Callable[..., None],
    tmp_path: Path,
) -> None:
    whitelist(LISTED_ID)
    pages = license_pages(FIRST_NUMBER)
    recordings = [OFF_TOPIC, OFF_TOPIC, OFF_TOPIC, *batch_responses(pages)]
    provider = RecordingProvider.from_directory(write_recordings(tmp_path / "kayit", recordings))
    bot = make_request_bot(provider)
    bot.telegram.files["ehliyet"] = make_document_pdf_bytes(pages)

    for update_id, text in enumerate(("hava nasıl", "bir fıkra anlat", "maç kaç kaç"), 1):
        bot.feed(message_update(update_id, LISTED_ID, text))
    assert bot.telegram.sent_texts()[-1] == gettext(intent.MUTED_TEXT)
    assert bot.requests is not None and bot.requests.conversations.muted(LISTED_ID)
    texts_before = len(bot.telegram.sent_texts())

    # Susturulmuşken metin kapıda durur ve yapay zekâya gitmez …
    bot.feed(message_update(4, LISTED_ID, REQUEST))
    assert len(bot.telegram.sent_texts()) == texts_before
    assert len(provider.query_requests) == 3

    # … ama dosya yine alınır: web ile aynı boru hattından geçip çalışanın Hazir'ına yazılır.
    bot.feed(document_update(5, LISTED_ID, "ehliyet", "ehliyet.pdf"))
    (license_,) = licenses(session_factory)
    assert (license_.type_slug, license_.status) == ("serbian_driving_license", "active")
    assert "Hazir" in Path(license_.path).parts
    assert stored_bytes(bot.layout, license_) == bot.telegram.files["ehliyet"]
    with session_factory() as session:
        employee = session.get_one(Employee, license_.employee_id)
        upload = session.scalars(select(Upload)).one()
    assert (employee.given_names, employee.surname) == ("AHMET", "ÇAKAR")
    assert (upload.channel, upload.uploaded_by) == ("telegram", f"ik-{LISTED_ID}")
    assert len(provider.requests) == len(pages)


def test_a_read_only_user_can_request_a_document_but_cannot_send_one(
    make_request_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    whitelist: Callable[..., None],
    tmp_path: Path,
) -> None:
    whitelist(LISTED_ID)
    pages = license_pages(FIRST_NUMBER)
    recordings = [*batch_responses(pages), QUERY]
    provider = RecordingProvider.from_directory(write_recordings(tmp_path / "kayit", recordings))
    bot = make_request_bot(provider)
    bot.telegram.files["ehliyet"] = make_document_pdf_bytes(pages)

    # İK (`hr`) gönderir: ehliyet Hazir'da.
    bot.feed(document_update(1, LISTED_ID, "ehliyet", "ehliyet.pdf"))
    (only,) = licenses(session_factory)
    assert only.status == "active"

    # Hesap Kullanıcı rolüne alınır (§D115 f): belge isteği yine çalışır — S17 tek ehliyet kolu.
    with session_factory() as session:
        account = session.get_one(TelegramUser, LISTED_ID)
        account.user.role = "user"
        user_id = account.user_id
        session.commit()
    bot.feed(message_update(2, LISTED_ID, REQUEST))
    assert bot.telegram.uploads == [(Path(only.path).name, stored_bytes(bot.layout, only))]
    assert access_rows(session_factory) == [(user_id, only.id, "download", "telegram")]
    with session_factory() as session:
        assert session.get_one(User, user_id).role == "user"

    # Belge gönderemez: dosya indirilmez, parti açılmaz, tek cümle.
    downloads = bot.telegram.methods().count("getFile")
    bot.feed(document_update(3, LISTED_ID, "ehliyet", "ehliyet-2.pdf"))
    assert bot.telegram.sent_texts()[-1] == READ_ONLY_TEXT
    assert bot.telegram.methods().count("getFile") == downloads
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Upload)) == 1
    assert len(licenses(session_factory)) == 1
    assert bot.requests is not None and not bot.requests.conversations.muted(LISTED_ID)
