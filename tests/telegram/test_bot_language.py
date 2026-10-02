"""12.1.6 — bot yanıtları kullanıcının dilinde: izinli kimliğin bağlı olduğu panel kullanıcısının
`users.language`'i, boşsa varsayılan dil (üretimde `PANEL_DEFAULT_LANGUAGE`, varsayılan `en`);
`/start <kod>` yanıtı kodun kullanıcısının dilinde, geçersiz kod varsayılan dilde; panelde dil
değişince botun sonraki yanıtı yeni dilde (PLAN.md §D92 k, §D101; tm 158).

Ağsız: gerçek `Application`, sahte Telegram aktarıcısı (`conftest.py`). Bu dosyadaki botlar
varsayılan dili açıkça `en` verir (üretimdeki gibi); öbür bot testleri Türkçe varsayılanla koşar.
Veri sentetiktir.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session, sessionmaker
from telegram.ext import ApplicationBuilder

from app.db.models import TelegramUser, Upload, UploadStatus, User
from app.i18n import gettext, use_language
from app.pipeline.orchestrate import ProcessedUpload
from app.telegram import bot as bot_module
from app.telegram import handlers, intent
from app.telegram.bot import HELP_TEXT, INVALID_LINK_TEXT, LINKED_TEXT, build_application
from app.telegram.link import create_link_code
from app.web.auth import create_user
from tests.fixtures.gen import make_docx_bytes
from tests.telegram.conftest import (
    LISTED_ID,
    OTHER_ID,
    BotHarness,
    FakeTelegram,
    IntakeBot,
    document_update,
    message_update,
    polling_config,
)

THIRD_ID = 5_000_000_003
TURKISH_LETTERS = re.compile(r"[çğıİöşüÇĞÖŞÜ]")
# Botun doğal dil isteğini anlaması Türkçedir (12.3); yardım ve yanıtlardaki örnek istek çevrilmez.
EXAMPLE_REQUEST = "Ahmet Çakar'ın ehliyetini göster"


def _user(
    session_factory: sessionmaker[Session],
    username: str,
    language: str | None,
    telegram_id: int | None = None,
) -> int:
    with session_factory() as session:
        user = create_user(session, username, "sentetik-parola-1")
        user.language = language
        if telegram_id is not None:
            session.add(TelegramUser(telegram_id=telegram_id, user=user, allowed=True))
        session.commit()
        return user.id


def _set_language(session_factory: sessionmaker[Session], user_id: int, language: str) -> None:
    with session_factory() as session:
        session.get_one(User, user_id).language = language
        session.commit()


def _bot(session_factory: sessionmaker[Session], default_language: str = "en") -> BotHarness:
    telegram = FakeTelegram()
    application = build_application(
        polling_config(),
        session_factory,
        builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
        default_language=default_language,
    )
    return BotHarness(application, telegram)


def _in(language: str, message: str) -> str:
    with use_language(language):
        return gettext(message)


def _help(language: str, telegram_id: int) -> str:
    """Yardım yanıtı `language` dilinde, son satırda numarayla (12.1.7)."""
    with use_language(language):
        return bot_module.help_reply(telegram_id)


# --- 1: aynı mesaj üç kullanıcıya üç dilde -----------------------------------------------------


def test_the_same_message_is_answered_in_each_users_language(
    session_factory: sessionmaker[Session],
) -> None:
    _user(session_factory, "turkce", "tr", LISTED_ID)
    _user(session_factory, "srpski", "sr", OTHER_ID)
    _user(session_factory, "bos", None, THIRD_ID)
    bot = _bot(session_factory)

    bot.feed(
        message_update(1, LISTED_ID, "/yardim"),
        message_update(2, OTHER_ID, "/yardim"),
        message_update(3, THIRD_ID, "/yardim"),
    )

    english, serbian = _in("en", HELP_TEXT), _in("sr", HELP_TEXT)
    assert bot.telegram.sent_texts() == [
        _help("tr", LISTED_ID),
        _help("sr", OTHER_ID),
        _help("en", THIRD_ID),
    ]
    assert english.startswith("Hello") and serbian.startswith("Zdravo")
    assert len({HELP_TEXT, english, serbian}) == 3


def test_an_empty_preference_follows_the_configured_default(
    session_factory: sessionmaker[Session],
) -> None:
    _user(session_factory, "bos", None, THIRD_ID)
    bot = _bot(session_factory, default_language="sr")

    bot.feed(message_update(1, THIRD_ID, "/start"))

    assert bot.telegram.sent_texts() == [_help("sr", THIRD_ID)]


def test_an_unsupported_default_is_refused() -> None:
    with pytest.raises(ValueError, match="desteklenmeyen dil"):
        build_application(polling_config(), sessionmaker(), default_language="de")


def test_without_an_explicit_default_the_fallback_is_english_in_production(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Bot testleri `FALLBACK_LANGUAGE`'ı `tr` yapar (conftest); modülün kendi değeri `en`dir.
    monkeypatch.undo()
    assert bot_module.FALLBACK_LANGUAGE == "en"
    _user(session_factory, "bos", None, THIRD_ID)
    telegram = FakeTelegram()
    application = build_application(
        polling_config(),
        session_factory,
        builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
    )
    BotHarness(application, telegram).feed(message_update(1, THIRD_ID, "/start"))

    assert telegram.sent_texts() == [_help("en", THIRD_ID)]


# --- 2: `/start <kod>` -------------------------------------------------------------------------


def test_the_link_reply_is_in_the_language_of_the_codes_user(
    session_factory: sessionmaker[Session],
) -> None:
    milan = _user(session_factory, "milan", "sr")
    with session_factory() as session:
        issued = create_link_code(session, session.get_one(User, milan), actor="ik-yonetici")
        session.commit()
    bot = _bot(session_factory)

    bot.feed(
        message_update(1, OTHER_ID, f"/start {issued.code}"),
        message_update(2, THIRD_ID, "/start yanlis-kod-yanlis-kod-1"),
    )

    assert bot.telegram.sent_texts() == [
        _in("sr", LINKED_TEXT).format(username="milan")
        + f"\n\n{_in('sr', bot_module.YOUR_NUMBER_TEXT)}\n{OTHER_ID}",
        _in("en", INVALID_LINK_TEXT),
    ]
    assert bot.telegram.sent_texts()[0].startswith("Povezano: milan.")


# --- 3: panelde dil değişince sonraki yanıt yeni dilde ------------------------------------------


def test_a_language_change_in_the_panel_applies_to_the_next_reply(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse", "tr", LISTED_ID)
    bot = _bot(session_factory)

    bot.feed(message_update(1, LISTED_ID, "/yardim"))
    _set_language(session_factory, ayse, "en")
    bot.feed(message_update(2, LISTED_ID, "/yardim"))
    _set_language(session_factory, ayse, "sr")
    bot.feed(message_update(3, LISTED_ID, "/yardim"))

    assert bot.telegram.sent_texts() == [
        _help("tr", LISTED_ID),
        _help("en", LISTED_ID),
        _help("sr", LISTED_ID),
    ]


def test_a_stranger_gets_no_reply_in_any_language(session_factory: sessionmaker[Session]) -> None:
    bot = _bot(session_factory)

    bot.feed(message_update(1, OTHER_ID, "/yardim"))

    assert bot.telegram.sent_texts() == []


def test_the_language_does_not_leak_from_one_update_to_the_next(
    session_factory: sessionmaker[Session],
) -> None:
    _user(session_factory, "srpski", "sr", OTHER_ID)
    _user(session_factory, "bos", None, THIRD_ID)
    bot = _bot(session_factory)

    bot.feed(message_update(1, OTHER_ID, "/yardim"), message_update(2, THIRD_ID, "/yardim"))

    assert bot.telegram.sent_texts() == [_help("sr", OTHER_ID), _help("en", THIRD_ID)]


# --- belge alma ve belge isteği (arka plan işi dili taşır) ------------------------------------


def test_intake_messages_are_in_the_senders_language(
    make_intake_bot: Callable[..., IntakeBot], session_factory: sessionmaker[Session]
) -> None:
    _user(session_factory, "srpski", "sr", OTHER_ID)
    bot = make_intake_bot()
    bot.telegram.files["f1"] = make_docx_bytes()

    bot.feed(document_update(1, OTHER_ID, "f1", "cv.docx"))

    received, unprocessed = bot.telegram.sent_texts()
    assert received == "Primljen je 1 fajl. Obrađuje se; javiću rezultat kada završi."
    assert unprocessed.startswith("Serija ") and "1 fajl je primljen i sačuvan" in unprocessed


def test_document_request_replies_are_in_the_requesters_language(
    make_request_bot: Callable[..., IntakeBot], session_factory: sessionmaker[Session]
) -> None:
    _user(session_factory, "english", "en", OTHER_ID)
    bot = make_request_bot()

    bot.feed(message_update(1, OTHER_ID, EXAMPLE_REQUEST))

    assert bot.telegram.sent_texts() == [_in("en", intent.UNAVAILABLE_TEXT)]
    assert bot.telegram.sent_texts()[0].startswith("Document requests are not working")


def test_serbian_plurals_follow_the_count() -> None:
    with use_language("sr"):
        assert handlers.received_text(1).startswith("Primljen je 1 fajl.")
        assert handlers.received_text(3).startswith("Primljena su 3 fajla.")
        assert handlers.received_text(5).startswith("Primljeno je 5 fajlova.")
    with use_language("en"):
        assert handlers.received_text(1).startswith("1 file received.")
        assert handlers.received_text(2).startswith("2 files received.")
    with use_language("tr"):
        assert handlers.received_text(2).startswith("2 dosya alındı.")


# --- bütün bot metinleri çevrili ---------------------------------------------------------------

BOT_TEXTS = [
    value
    for module in (bot_module, handlers, intent)
    for name, value in vars(module).items()
    if name.endswith("_TEXT") and isinstance(value, str)
]
LABELS = [
    *handlers.STATUS_LABELS.values(),
    *handlers.QUEUE_LABELS.values(),
    intent.ANY_DOCUMENT,
    intent.ANY_ACTIVE_DOCUMENT,
]


@pytest.mark.parametrize("language", ["en", "sr"])
def test_every_bot_text_has_a_translation_without_turkish_residue(language: str) -> None:
    assert len(BOT_TEXTS) >= 25
    for text in [*BOT_TEXTS, *LABELS]:
        translated = _in(language, text)
        assert translated != text or text in handlers.QUEUE_LABELS.values(), text
        visible = translated.replace(EXAMPLE_REQUEST, "")
        assert not TURKISH_LETTERS.search(visible), (language, translated)


def test_admission_reads_permission_and_language_in_one_step(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse", "sr", LISTED_ID)
    _user(session_factory, "bos", None, THIRD_ID)

    assert bot_module.admission(session_factory, LISTED_ID) == bot_module.Admission("sr")
    assert bot_module.admission(session_factory, THIRD_ID) == bot_module.Admission(None)
    assert bot_module.admission(session_factory, OTHER_ID) is None
    with session_factory() as session:
        session.get_one(
            User, ayse
        ).active = False  # 12.1.3: pasif kullanıcının kimliği listede değil
        session.commit()
    assert bot_module.admission(session_factory, LISTED_ID) is None


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "en",
            "Batch u_20260101_001: could not be processed.\n"
            "The files are stored; see the batch in the panel for details.",
        ),
        (
            "sr",
            "Serija u_20260101_001: nije mogla da se obradi.\n"
            "Fajlovi su sačuvani; detalje pogledajte u seriji na panelu.",
        ),
    ],
)
def test_the_result_summary_is_in_the_language(
    session_factory: sessionmaker[Session], language: str, expected: str
) -> None:
    with session_factory() as session:
        session.add(Upload(id="u_20260101_001", channel="telegram", status="failed"))
        session.commit()
        failed = ProcessedUpload(UploadStatus.FAILED, None, failed_stage=UploadStatus.RENDERING)

        with use_language(language):
            text = handlers.build_summary(session, "u_20260101_001", failed)

    assert text == expected
