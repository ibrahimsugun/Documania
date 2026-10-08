"""12.3.4–12.3.7, 12.1.11, 12.1.12 — botla konuşma (PLAN.md §D108; tm 164).

İnsan isteğindeki konuşmanın her adımı (2026-10-08): "Ehliyet ve CV yüklemiş mi?" (birden çok tür),
"Ehliyet işte" (kişisiz devam), "kaç yaşında" (kişi bilgisi), "adres kaydı için hangi belgeleri
tamamlamalı" (eksik belgeler), sesli mesaj (yanıtsız kalmamalı) ve Türkçe yazana Türkçe yanıt.

Bot gerçek `Application` + gerçek `DocumentRequests` ile kurulur; yalnız Telegram aktarıcısı ve
yapay zekâ okuması sahtedir. Kişiler, gruplar ve belgeler sentetiktir (CONVENTIONS §6).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import EmployeePackage, Event, User
from app.groups.packages import assign_package
from app.groups.service import add_item, create_group
from app.i18n import gettext, use_language
from app.storage import DataLayout, prepare_data_dir
from app.telegram import bot as bot_module
from app.telegram import intent
from app.telegram.bot import HELP_TEXT, UNSUPPORTED_TEXT, VOICE_TEXT, help_reply
from app.telegram.intent import (
    CONTEXT_TTL_SECONDS,
    NO_PERSON_TEXT,
    Conversations,
)
from app.telegram.plain import problems
from tests.telegram.conftest import LISTED_ID, IntakeBot, callback_update, message_update
from tests.telegram.test_document_requests import (
    LICENSE,
    PASSPORT,
    QueryProvider,
    access_rows,
    add_document,
    add_employee,
    buttons,
    pdf,
)

ACTOR = "test"


def ask_for(
    *people: str,
    intent_name: str = "find_documents",
    documents: list[tuple[str, list[str]]] | None = None,
    group: str | None = None,
    group_ids: list[int] | None = None,
    language: str | None = "tr",
) -> dict[str, Any]:
    return {
        "intent": intent_name,
        "people": list(people),
        "documents": [{"kind": kind, "types": types} for kind, types in documents or []],
        "group": group,
        "group_ids": group_ids or [],
        "language": language,
    }


def raw_message(update_id: int, **content: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "message_id": update_id,
        "date": 1_700_000_000,
        "chat": {"id": LISTED_ID, "type": "private"},
        "from": {"id": LISTED_ID, "is_bot": False, "first_name": "Deneme"},
        **content,
    }
    return {"update_id": update_id, "message": body}


@pytest.fixture
def listed(whitelist: Callable[..., None]) -> None:
    whitelist(LISTED_ID)


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    """Botun veri dizini (`make_request_bot` aynı kökü kullanır)."""
    return prepare_data_dir(tmp_path / "data")


@pytest.fixture
def chat(
    make_request_bot: Callable[..., IntakeBot], listed: None
) -> Callable[..., tuple[IntakeBot, QueryProvider]]:
    """Sırayla verilen okumalarla bir bot; her metin bir mesajdır."""

    def _chat(*responses: object, clock: Callable[[], float] | None = None) -> Any:
        provider = QueryProvider(*responses)
        bot = make_request_bot(provider)
        if clock is not None:
            assert bot.requests is not None
            bot.requests.conversations = Conversations(clock=clock)
        return bot, provider

    return _chat


def say(bot: IntakeBot, *texts: str, start: int = 1) -> None:
    for offset, text in enumerate(texts):
        bot.feed(message_update(start + offset, LISTED_ID, text))


def _plain(text: str) -> None:
    assert problems(text, "tr") == [], text


# --- 12.3.4: birden çok tür ------------------------------------------------------------------


def test_two_kinds_in_one_message_are_answered_line_by_line_and_the_single_one_is_sent(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    employee = add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    license_id = add_document(session_factory, layout, employee, LICENSE, "l.pdf", pdf("l"))
    bot, _ = chat(
        ask_for("Mehmet Örnek", documents=[("Ehliyet", [LICENSE]), ("CV", [])]),
    )

    say(bot, "MEhmet ÖRnek Ehliyet ve CV yüklemiş mi ?")

    (text,) = bot.telegram.sent_texts()
    assert text == "MEHMET ÖRNEK:\n• Ehliyet: var\n• CV: bu türü bilmiyorum"
    _plain(text)
    assert bot.telegram.uploads == [("l.pdf", pdf("l"))]
    assert [row[1] for row in access_rows(session_factory)] == [license_id]


def test_a_kind_with_several_documents_is_counted_and_not_sent(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    employee = add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    add_document(session_factory, layout, employee, PASSPORT, "p1.pdf", pdf("1"))
    add_document(session_factory, layout, employee, PASSPORT, "p2.pdf", pdf("2"))
    bot, _ = chat(
        ask_for("Mehmet Örnek", documents=[("pasaport", [PASSPORT]), ("ehliyet", [LICENSE])]),
    )

    say(bot, "Mehmet Örnek pasaport ve ehliyet var mı")

    (text,) = bot.telegram.sent_texts()
    assert text.splitlines() == [
        "MEHMET ÖRNEK:",
        "• pasaport: 2 tane",
        "• ehliyet: yok",
        "Birden çok olanı görmek için yalnız o türü isteyin.",
    ]
    assert bot.telegram.uploads == []
    assert access_rows(session_factory) == []


# --- 12.3.5: önceki kişiye devam -------------------------------------------------------------


def test_a_request_without_a_name_goes_to_the_previous_person(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    employee = add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    add_employee(session_factory, 2, "AYŞE", "DENEME")
    add_document(session_factory, layout, employee, PASSPORT, "p.pdf", pdf("p"))
    add_document(session_factory, layout, employee, LICENSE, "l.pdf", pdf("l"))
    bot, provider = chat(
        ask_for("Mehmet Örnek", documents=[("pasaport", [PASSPORT])]),
        ask_for(documents=[("Ehliyet", [LICENSE])]),
    )

    say(bot, "Mehmet Örnek pasaportu yüklü mü", "Ehliyet işte")

    assert bot.telegram.uploads == [("p.pdf", pdf("p")), ("l.pdf", pdf("l"))]
    assert bot.telegram.sent_texts() == []
    assert len(provider.queries) == 2


def test_without_a_previous_person_the_name_is_asked(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
) -> None:
    add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    bot, _ = chat(ask_for(documents=[("Ehliyet", [LICENSE])]))

    say(bot, "Ehliyet işte")

    assert bot.telegram.sent_texts() == [NO_PERSON_TEXT]
    assert bot.telegram.uploads == []


def test_the_context_expires_and_is_dropped_after_an_ambiguous_or_unknown_person(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    now = [0.0]
    employee = add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    add_employee(session_factory, 2, "AHMET", "ÇAKAR")
    add_employee(session_factory, 3, "AHMET", "ÇAKAR")
    add_document(session_factory, layout, employee, LICENSE, "l.pdf", pdf("l"))
    bot, _ = chat(
        ask_for("Mehmet Örnek", documents=[("ehliyet", [LICENSE])]),
        ask_for(documents=[("ehliyet", [LICENSE])]),
        ask_for("Mehmet Örnek", documents=[("ehliyet", [LICENSE])]),
        ask_for("Ahmet Çakar", documents=[("ehliyet", [LICENSE])]),
        ask_for(documents=[("ehliyet", [LICENSE])]),
        clock=lambda: now[0],
    )

    say(bot, "Mehmet Örnek ehliyet", start=1)
    now[0] = CONTEXT_TTL_SECONDS + 1
    say(bot, "ehliyeti", start=2)  # süre geçti: bağlam yok
    say(bot, "Mehmet Örnek ehliyet", start=3)
    say(bot, "Ahmet Çakar ehliyet", start=4)  # iki Ahmet Çakar: soru, bağlam silinir
    say(bot, "ehliyeti", start=5)

    texts = bot.telegram.sent_texts()
    assert texts[0] == NO_PERSON_TEXT
    assert texts[-1] == NO_PERSON_TEXT
    assert len(bot.telegram.uploads) == 2


# --- 12.3.6: kişi bilgisi --------------------------------------------------------------------


def test_age_question_gives_a_short_summary_and_sends_nothing(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(intent, "utcnow", lambda: __import__("datetime").datetime(2026, 10, 8))
    employee = add_employee(
        session_factory, 1, "MEHMET", "ÖRNEK", date_of_birth=date(1990, 11, 2), nationality="TUR"
    )
    add_document(session_factory, layout, employee, PASSPORT, "p.pdf", pdf("p"))
    add_document(session_factory, layout, employee, LICENSE, "l.pdf", pdf("l"))
    bot, _ = chat(ask_for("Mehmet örnek", intent_name="employee_info"))

    say(bot, "MEhmet örnek kaç yaşında")

    (text,) = bot.telegram.sent_texts()
    assert text.splitlines() == [
        "MEHMET ÖRNEK",
        "• Doğum tarihi: 02.11.1990 (35 yaşında)",
        "• Uyruk: Türkiye",
        "• Belgeler: Serbian Driving License, Russian Passport",
    ]
    _plain(text)
    assert bot.telegram.uploads == []
    assert access_rows(session_factory) == []


def test_unknown_fields_are_said_to_be_unrecorded(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
) -> None:
    add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    bot, _ = chat(ask_for("Mehmet Örnek", intent_name="employee_info"))

    say(bot, "Mehmet Örnek kimdir")

    assert bot.telegram.sent_texts() == [
        "MEHMET ÖRNEK\n• Doğum tarihi: kayıtlı değil\n• Uyruk: kayıtlı değil\n• Belgeler: yok"
    ]


# --- 12.3.7: eksik belgeler ------------------------------------------------------------------


def _address_group(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        group = create_group(session, name="Adres kaydı", description=None, actor=ACTOR)
        add_item(session, group.id, match_kind="label", file_label="Passport", actor=ACTOR)
        add_item(session, group.id, match_kind="type", type_slug=LICENSE, actor=ACTOR)
        add_item(
            session,
            group.id,
            match_kind="label",
            file_label="Work Permit",
            required=False,
            actor=ACTOR,
        )
        session.commit()
        return group.id


def _counts(session_factory: sessionmaker[Session]) -> tuple[int, int]:
    with session_factory() as session:
        return (
            session.scalar(select(func.count()).select_from(EmployeePackage)) or 0,
            session.scalar(select(func.count()).select_from(Event)) or 0,
        )


def test_missing_documents_for_a_group_without_a_package_write_nothing(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    group_id = _address_group(session_factory)
    employee = add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    add_document(session_factory, layout, employee, PASSPORT, "p.pdf", pdf("p"))
    before = _counts(session_factory)
    bot, provider = chat(
        ask_for(
            "Mehmet örnek",
            intent_name="missing_documents",
            group="adres kaydı",
            group_ids=[group_id],
        )
    )

    say(bot, "Mehmet örnek adres kaydı için hangi belgeleri tamamlamalı")

    (text,) = bot.telegram.sent_texts()
    assert text.splitlines() == [
        "MEHMET ÖRNEK — Adres kaydı: 1 eksik belge.",
        "• Serbian Driving License",
        "İsteğe bağlı 1 belge de eksik.",
    ]
    _plain(text)
    assert _counts(session_factory) == before  # paket açılmadı, olay yazılmadı
    # Yapay zekâ grubu listeden seçer: istem grubu taşır, bilinen gruplar istekte.
    (request,) = provider.queries
    assert f"- {group_id} — Adres kaydı — -" in request.prompt
    assert request.known_groups == frozenset({group_id})


def test_missing_documents_use_the_package_and_say_when_nothing_is_missing(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    group_id = _address_group(session_factory)
    employee = add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    add_document(session_factory, layout, employee, PASSPORT, "p.pdf", pdf("p"))
    with session_factory() as session:
        assign_package(session, employee, group_id, actor=ACTOR)
        session.commit()
    bot, _ = chat(
        ask_for("Mehmet Örnek", intent_name="missing_documents"),
        ask_for(intent_name="missing_documents", group="adres kaydı", group_ids=[group_id]),
    )

    say(bot, "Mehmet Örnek'in eksikleri ne")
    add_document(session_factory, layout, employee, LICENSE, "l.pdf", pdf("l"))
    say(bot, "adres kaydı tamam mı", start=2)

    first, second = bot.telegram.sent_texts()
    assert first == "MEHMET ÖRNEK için eksik belgeler:\n• Adres kaydı: Serbian Driving License"
    assert second.splitlines() == [
        "MEHMET ÖRNEK — Adres kaydı: eksik belge yok.",
        "İsteğe bağlı 1 belge de eksik.",
    ]


def test_an_unknown_group_and_no_open_package_are_said(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
) -> None:
    add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    bot, _ = chat(
        ask_for("Mehmet Örnek", intent_name="missing_documents", group="vize başvurusu"),
        ask_for("Mehmet Örnek", intent_name="missing_documents"),
    )

    say(bot, "Mehmet Örnek vize başvurusu için ne eksik", "Mehmet Örnek'in eksikleri")

    assert bot.telegram.sent_texts() == [
        "“vize başvurusu” diye bir belge grubu bilmiyorum.",
        "MEHMET ÖRNEK için eksik belgesi olan paket yok.",
    ]


# --- 12.1.11: her mesaja yanıt ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ({"voice": {"file_id": "v", "file_unique_id": "uv", "duration": 3}}, VOICE_TEXT),
        (
            {"audio": {"file_id": "a", "file_unique_id": "ua", "duration": 3}},
            VOICE_TEXT,
        ),
        (
            {
                "sticker": {
                    "file_id": "s",
                    "file_unique_id": "us",
                    "type": "regular",
                    "width": 1,
                    "height": 1,
                    "is_animated": False,
                    "is_video": False,
                }
            },
            UNSUPPORTED_TEXT,
        ),
        ({"location": {"latitude": 44.8, "longitude": 20.4}}, UNSUPPORTED_TEXT),
        (
            {
                "video": {
                    "file_id": "x",
                    "file_unique_id": "ux",
                    "width": 1,
                    "height": 1,
                    "duration": 1,
                }
            },
            UNSUPPORTED_TEXT,
        ),
    ],
    ids=["sesli", "ses", "cikartma", "konum", "video"],
)
def test_messages_the_bot_cannot_handle_get_a_short_answer(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    content: dict[str, Any],
    expected: str,
) -> None:
    bot, provider = chat()

    bot.feed(raw_message(1, **content))

    assert bot.telegram.sent_texts() == [expected]
    assert provider.queries == []
    _plain(expected)


def test_an_unlisted_sender_still_gets_nothing_for_a_voice_message(
    make_request_bot: Callable[..., IntakeBot],
) -> None:
    bot = make_request_bot(QueryProvider())

    bot.feed(raw_message(1, voice={"file_id": "v", "file_unique_id": "uv", "duration": 3}))

    assert bot.telegram.methods() == []


def test_the_bot_shows_typing_while_it_reads_a_request(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
) -> None:
    add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    bot, _ = chat(ask_for("Mehmet Örnek", intent_name="employee_info"))

    say(bot, "Mehmet Örnek kimdir")

    names = [name for name, _ in bot.telegram.calls if name != "getMe"]
    assert names == ["sendChatAction", "sendMessage"]
    assert bot.telegram.sent("sendChatAction") == [{"chat_id": LISTED_ID, "action": "typing"}]


# --- 12.1.12: yazılan dilde yanıt ------------------------------------------------------------


def _english_listed(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.get_one(User, 1).language = "en"
        session.commit()


def test_a_user_with_an_english_panel_writing_turkish_gets_turkish_from_then_on(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
) -> None:
    _english_listed(session_factory)
    add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    bot, _ = chat(
        ask_for(intent_name="other", language="en"),
        ask_for("Mehmet Örnek", intent_name="employee_info", language="tr"),
    )

    say(bot, "hello there", "/yardim", "Mehmet Örnek kimdir", "/yardim")

    texts = bot.telegram.sent_texts()
    with use_language("en"):
        english_other = gettext(intent.NOT_A_REQUEST_TEXT)
        english_help = help_reply(LISTED_ID)
    with use_language("tr"):
        turkish_help = help_reply(LISTED_ID)
    assert texts[0] == english_other
    assert texts[1] == english_help
    assert texts[2].startswith("MEHMET ÖRNEK\n• Doğum tarihi: kayıtlı değil")
    assert texts[3] == turkish_help  # sonraki yanıtlar da yazdığı dilde


def test_an_unknown_language_keeps_the_panel_language(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
) -> None:
    _english_listed(session_factory)
    bot, _ = chat(ask_for(intent_name="other", language=None))

    say(bot, "Guten Tag")

    with use_language("en"):
        assert bot.telegram.sent_texts() == [gettext(intent.NOT_A_REQUEST_TEXT)]


def test_conversations_memory_is_bounded_and_ignores_unknown_languages() -> None:
    memory = Conversations(capacity=2, clock=lambda: 0.0)

    memory.remember(1, 1, "E0001")
    memory.remember(2, 2, "E0002")
    memory.remember(3, 3, "E0003")
    memory.remember_language(1, "de")
    memory.remember_language(1, "sr")

    assert memory.person(1, 1) is None  # en eskisi düştü
    assert memory.person(3, 3) == "E0003"
    assert memory.person(3, 4) is None  # aynı sohbette başka kişinin bağlamı yok
    assert memory.language(1) == "sr"
    memory.forget(3, 3)
    assert memory.person(3, 3) is None


# --- metinler ---------------------------------------------------------------------------------


NEW_TEXTS = [
    HELP_TEXT,
    VOICE_TEXT,
    UNSUPPORTED_TEXT,
    intent.NOT_A_REQUEST_TEXT,
    intent.NO_PERSON_TEXT,
    intent.MANY_PEOPLE_TEXT,
    intent.ASK_SEPARATELY_TEXT,
    intent.MANY_GROUPS_TEXT,
    intent.UNKNOWN_GROUP_TEXT,
    intent.NO_OPEN_PACKAGE_TEXT,
]


@pytest.mark.parametrize("language", ["tr", "en", "sr"])
def test_new_bot_texts_are_plain_in_every_language(language: str) -> None:
    with use_language(language):
        for message in NEW_TEXTS:
            text = gettext(message)
            assert problems(text, language) == [], (language, text)
        assert gettext(HELP_TEXT) != HELP_TEXT or language == "tr"


def test_the_bot_module_exposes_the_new_handlers() -> None:
    assert bot_module.VOICE_TEXT is VOICE_TEXT


def test_after_choosing_between_two_people_the_info_follows_and_the_choice_is_the_context(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    add_employee(session_factory, 1, "AHMET", "ÇAKAR", date_of_birth=date(1980, 1, 1))
    second = add_employee(session_factory, 2, "AHMET", "ÇAKAR", date_of_birth=date(1991, 5, 5))
    add_document(session_factory, layout, second, LICENSE, "l.pdf", pdf("l"))
    bot, _ = chat(
        ask_for("Ahmet Çakar", intent_name="employee_info"),
        ask_for(documents=[("ehliyet", [LICENSE])]),
    )

    say(bot, "Ahmet Çakar kaç yaşında")
    bot.feed(callback_update(2, LISTED_ID, buttons(bot)[1][1]))
    say(bot, "ehliyeti", start=3)

    texts = bot.telegram.sent_texts()
    assert "2 kişi var" in texts[0]
    assert texts[1].startswith("AHMET ÇAKAR\n• Doğum tarihi: 05.05.1991")
    assert bot.telegram.uploads == [("l.pdf", pdf("l"))]


# --- §D109: uzun katalogda unutulan ya da uydurulan tür -----------------------------------------


def test_an_invented_slug_is_dropped_instead_of_failing_the_request(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    caplog: pytest.LogCaptureFixture,
) -> None:
    employee = add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    add_document(session_factory, layout, employee, "turkish_passport", "p.pdf", pdf("p"))
    # Ekran görüntüsündeki okuma: pasaport listesi uydurma slug taşıyor ("Şu an olmadı" idi).
    bot, _ = chat(
        ask_for(
            "Mehmet Örnek",
            documents=[("pasaport", ["russian_passport", "martian_passport", "turkish_passport"])],
        )
    )

    say(bot, "Bu adamın pasaportnu bana ver")

    assert bot.telegram.sent_texts() == []
    assert bot.telegram.uploads == [("p.pdf", pdf("p"))]
    assert "katalog dışı 1 tür" in caplog.text and "martian" not in caplog.text


def test_a_passport_the_model_forgot_to_list_is_still_found(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    employee = add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    add_document(session_factory, layout, employee, "turkish_passport", "p.pdf", pdf("p"))
    # Ekran görüntüsü: model ~100 pasaport türünü saydı ama Türk pasaportunu unuttu → "yok" idi.
    bot, _ = chat(
        ask_for(
            "Mehmet Örnek",
            documents=[("Pasaport", ["russian_passport", "serbian_passport"]), ("CV", [])],
        )
    )

    say(bot, "Pasaport ve CV yüklemiş mi")

    (text,) = bot.telegram.sent_texts()
    assert text == "MEHMET ÖRNEK:\n• Pasaport: var\n• CV: bu türü bilmiyorum"
    assert bot.telegram.uploads == [("p.pdf", pdf("p"))]


def test_a_single_wrong_country_falls_back_to_the_same_label(
    chat: Callable[..., tuple[IntakeBot, QueryProvider]],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    employee = add_employee(session_factory, 1, "MEHMET", "ÖRNEK")
    add_document(session_factory, layout, employee, "turkish_passport", "p.pdf", pdf("p"))
    bot, _ = chat(ask_for("Mehmet Örnek", documents=[("pasaport", ["russian_passport"])]))

    say(bot, "Mehmet Örnek pasaportu")

    assert bot.telegram.uploads == [("p.pdf", pdf("p"))]
