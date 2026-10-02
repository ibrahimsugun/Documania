"""12.1.4 — Telegram hesabını bağlantıyla bağlama: tek kullanımlık kod (`app.telegram.link`) ve
botun `/start <kod>` işleyicisi (PLAN.md §D87).

Kod 10 dakika ve bir kez geçerlidir, yeni kod öncekini iptal eder, yalnız özeti saklanır. Bot kodu
beyaz liste kapısından önce, yalnız özel sohbette işler; kodsuz `/start` yabancıya yine yanıtsızdır.
Kimlikler ve kullanıcılar sentetiktir; Telegram aktarıcısı sahtedir (`FakeTelegram`).
"""

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker
from telegram.ext import ApplicationBuilder

import app.telegram.link as link_module
from app.db.models import Event, TelegramLinkCode, TelegramUser, User
from app.storage import prepare_data_dir
from app.telegram.bot import (
    ALREADY_LINKED_TEXT,
    INVALID_LINK_TEXT,
    LINK_BLOCKED_TEXT,
    LINK_FAILED_TEXT,
    LINK_GROUP,
    LINK_TAKEN_TEXT,
    LINKED_TEXT,
    LinkStart,
    build_application,
    help_reply,
    not_linked_reply,
    register_bot_info,
    with_number,
)
from app.telegram.link import (
    LINK_CODE_TTL,
    LINK_VIA,
    BotInfo,
    IssuedLinkCode,
    LinkAttempts,
    LinkOutcome,
    LinkTargetInactiveError,
    create_link_code,
    hash_link_code,
    link_url,
    read_bot_info,
    redeem_link_code,
    write_bot_info,
)
from app.web.auth import create_user
from tests.telegram.conftest import (
    LISTED_ID,
    OTHER_ID,
    BotHarness,
    FakeTelegram,
    message_update,
    polling_config,
)

ADMIN = "ik-yonetici"
PASSWORD = "sentetik-parola-1"
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
CODE_SHAPE = re.compile(r"[A-Za-z0-9_-]{22}")


def _user(session_factory: sessionmaker[Session], username: str, *, active: bool = True) -> int:
    with session_factory() as session:
        user = create_user(session, username, PASSWORD)
        user.active = active
        session.commit()
        return user.id


def _issue(
    session_factory: sessionmaker[Session], user_id: int, *, now: datetime | None = None
) -> IssuedLinkCode:
    with session_factory() as session:
        issued = create_link_code(session, session.get_one(User, user_id), actor=ADMIN, now=now)
        session.commit()
    return issued


def _redeem(
    session_factory: sessionmaker[Session],
    code: str,
    telegram_id: int,
    *,
    now: datetime | None = None,
) -> link_module.LinkRedemption:
    with session_factory() as session:
        result = redeem_link_code(session, code, telegram_id, now=now)
        session.commit()
    return result


def _bind(
    session_factory: sessionmaker[Session], user_id: int, telegram_id: int, *, allowed: bool = True
) -> None:
    with session_factory() as session:
        session.add(TelegramUser(telegram_id=telegram_id, user_id=user_id, allowed=allowed))
        session.commit()


def _codes(session_factory: sessionmaker[Session]) -> list[TelegramLinkCode]:
    with session_factory() as session:
        rows = list(session.scalars(select(TelegramLinkCode).order_by(TelegramLinkCode.id)))
        session.expunge_all()
    return rows


def _accounts(session_factory: sessionmaker[Session]) -> list[tuple[int, int, bool]]:
    with session_factory() as session:
        return [
            (row.telegram_id, row.user_id, row.allowed)
            for row in session.scalars(select(TelegramUser).order_by(TelegramUser.telegram_id))
        ]


def _events(session_factory: sessionmaker[Session], kind: str) -> list[Event]:
    with session_factory() as session:
        rows = list(session.scalars(select(Event).where(Event.type == kind).order_by(Event.id)))
        session.expunge_all()
    return rows


# --- kod üretimi ------------------------------------------------------------------------------


def test_a_code_is_returned_once_and_only_its_hash_is_stored(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse")

    issued = _issue(session_factory, ayse, now=NOW)

    assert CODE_SHAPE.fullmatch(issued.code)
    assert issued.expires_at == NOW + timedelta(minutes=10) == NOW + LINK_CODE_TTL
    assert issued.code not in repr(issued)
    [row] = _codes(session_factory)
    assert row.code_hash == hashlib.sha256(issued.code.encode()).hexdigest()
    assert (row.user_id, row.created_by, row.created_at, row.expires_at) == (
        ayse,
        ADMIN,
        NOW,
        NOW + LINK_CODE_TTL,
    )
    assert (row.used_at, row.used_telegram_id, row.revoked_at) == (None, None, None)
    [event] = _events(session_factory, "TELEGRAM_LINK_CREATED")
    assert (event.actor, event.data_json) == (
        ADMIN,
        {"target_user_id": ayse, "expires_at": (NOW + LINK_CODE_TTL).isoformat()},
    )
    assert issued.code not in json.dumps(event.data_json) and issued.code not in (
        event.message or ""
    )


def test_codes_are_unpredictable(session_factory: sessionmaker[Session]) -> None:
    ayse = _user(session_factory, "ayse")

    codes = {_issue(session_factory, ayse).code for _ in range(20)}

    assert len(codes) == 20


def test_a_new_code_revokes_the_previous_live_one_but_not_an_expired_one(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse")
    mehmet = _user(session_factory, "mehmet")
    expired = _issue(session_factory, ayse, now=NOW - timedelta(hours=1))
    previous = _issue(session_factory, ayse, now=NOW - timedelta(minutes=1))
    of_mehmet = _issue(session_factory, mehmet, now=NOW - timedelta(minutes=1))

    latest = _issue(session_factory, ayse, now=NOW)

    revoked = {row.code_hash: row.revoked_at for row in _codes(session_factory)}
    assert revoked[hash_link_code(expired.code)] is None  # süresi zaten dolmuştu
    assert revoked[hash_link_code(previous.code)] == NOW
    assert revoked[hash_link_code(of_mehmet.code)] is None  # başka kullanıcının kodu
    assert revoked[hash_link_code(latest.code)] is None
    assert _redeem(session_factory, previous.code, LISTED_ID, now=NOW).outcome is (
        LinkOutcome.INVALID
    )
    assert _redeem(session_factory, latest.code, LISTED_ID, now=NOW).outcome is (LinkOutcome.LINKED)


def test_no_code_is_issued_for_a_passive_user(session_factory: sessionmaker[Session]) -> None:
    mehmet = _user(session_factory, "mehmet", active=False)

    with session_factory() as session, pytest.raises(LinkTargetInactiveError):
        create_link_code(session, session.get_one(User, mehmet), actor=ADMIN)

    assert _codes(session_factory) == []
    assert _events(session_factory, "TELEGRAM_LINK_CREATED") == []


def test_the_link_points_to_the_bot_with_the_code_as_start_parameter() -> None:
    assert link_url("belgeee_bot", "abc_DEF-123") == "https://t.me/belgeee_bot?start=abc_DEF-123"


# --- bağlama ----------------------------------------------------------------------------------


def test_redeeming_binds_the_sender_allowed_and_logs_it_under_the_admins_name(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse")
    issued = _issue(session_factory, ayse, now=NOW)

    result = _redeem(session_factory, issued.code, LISTED_ID, now=NOW + timedelta(minutes=9))

    assert (result.outcome, result.username) == (LinkOutcome.LINKED, "ayse")
    assert _accounts(session_factory) == [(LISTED_ID, ayse, True)]
    [row] = _codes(session_factory)
    assert (row.used_at, row.used_telegram_id) == (NOW + timedelta(minutes=9), LISTED_ID)
    [event] = _events(session_factory, "TELEGRAM_USER_CHANGED")
    assert (event.actor, event.data_json) == (
        ADMIN,
        {
            "target_user_id": ayse,
            "telegram_id": LISTED_ID,
            "allowed": True,
            "added": True,
            "via": LINK_VIA,
        },
    )


def test_a_code_works_only_once(session_factory: sessionmaker[Session]) -> None:
    ayse = _user(session_factory, "ayse")
    issued = _issue(session_factory, ayse)
    assert _redeem(session_factory, issued.code, LISTED_ID).outcome is LinkOutcome.LINKED

    again = _redeem(session_factory, issued.code, OTHER_ID)

    assert again.outcome is LinkOutcome.INVALID and again.username is None
    assert _accounts(session_factory) == [(LISTED_ID, ayse, True)]


def test_an_expired_code_does_not_work(session_factory: sessionmaker[Session]) -> None:
    ayse = _user(session_factory, "ayse")
    issued = _issue(session_factory, ayse, now=NOW)

    result = _redeem(session_factory, issued.code, LISTED_ID, now=NOW + LINK_CODE_TTL)

    assert result.outcome is LinkOutcome.INVALID
    assert _accounts(session_factory) == []
    assert _codes(session_factory)[0].used_at is None


@pytest.mark.parametrize("state", ["expired", "used"])
@pytest.mark.parametrize("bound", ["other", "blocked", "allowed"])
def test_a_dead_code_reveals_nothing_about_an_already_bound_id(
    session_factory: sessionmaker[Session], state: str, bound: str
) -> None:
    # Süresi dolmuş ya da kullanılmış kod, kimlik zaten bağlı olsa da yalnız genel yanıtı alır:
    # "başka kullanıcıya bağlı", "izni kapalı" ya da "zaten bağlı" bilgisi sızmaz.
    ayse = _user(session_factory, "ayse")
    mehmet = _user(session_factory, "mehmet")
    owner = mehmet if bound == "other" else ayse
    _bind(session_factory, owner, OTHER_ID, allowed=bound != "blocked")
    issued = _issue(session_factory, ayse, now=NOW)
    when = NOW + LINK_CODE_TTL if state == "expired" else NOW
    if state == "used":
        assert _redeem(session_factory, issued.code, LISTED_ID, now=NOW).outcome is (
            LinkOutcome.LINKED
        )

    result = _redeem(session_factory, issued.code, OTHER_ID, now=when)

    assert (result.outcome, result.username) == (LinkOutcome.INVALID, None)


@pytest.mark.parametrize(
    "code",
    ["", "yok-boyle-bir-kod-0000", "a b", "x" * 65, "kod=1", "çğüşöı" * 3],
)
def test_an_unknown_or_malformed_code_does_not_work(
    session_factory: sessionmaker[Session], code: str
) -> None:
    _issue(session_factory, _user(session_factory, "ayse"))

    assert _redeem(session_factory, code, LISTED_ID).outcome is LinkOutcome.INVALID
    assert _accounts(session_factory) == []


def test_a_sender_id_outside_the_database_range_does_not_work(
    session_factory: sessionmaker[Session],
) -> None:
    issued = _issue(session_factory, _user(session_factory, "ayse"))

    for telegram_id in (0, -5, 2**63):
        assert _redeem(session_factory, issued.code, telegram_id).outcome is LinkOutcome.INVALID
    assert _codes(session_factory)[0].used_at is None


def test_an_id_bound_to_another_user_is_refused_and_the_code_stays_usable(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse")
    mehmet = _user(session_factory, "mehmet")
    _bind(session_factory, mehmet, OTHER_ID)
    issued = _issue(session_factory, ayse)

    taken = _redeem(session_factory, issued.code, OTHER_ID)

    assert (taken.outcome, taken.username) == (LinkOutcome.TAKEN, None)
    assert _accounts(session_factory) == [(OTHER_ID, mehmet, True)]
    assert _codes(session_factory)[0].used_at is None
    # Doğru kişi aynı bağlantıyı yine kullanabilir.
    assert _redeem(session_factory, issued.code, LISTED_ID).outcome is LinkOutcome.LINKED
    assert _accounts(session_factory) == [(LISTED_ID, ayse, True), (OTHER_ID, mehmet, True)]


def test_an_id_already_allowed_on_the_same_user_uses_the_code_without_a_change(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse")
    _bind(session_factory, ayse, LISTED_ID)
    issued = _issue(session_factory, ayse)

    result = _redeem(session_factory, issued.code, LISTED_ID)

    assert (result.outcome, result.username) == (LinkOutcome.ALREADY_LINKED, "ayse")
    assert _codes(session_factory)[0].used_telegram_id == LISTED_ID
    assert _events(session_factory, "TELEGRAM_USER_CHANGED") == []


def test_a_blocked_id_is_not_reopened_by_a_link(session_factory: sessionmaker[Session]) -> None:
    ayse = _user(session_factory, "ayse")
    _bind(session_factory, ayse, LISTED_ID, allowed=False)
    issued = _issue(session_factory, ayse)

    result = _redeem(session_factory, issued.code, LISTED_ID)

    assert (result.outcome, result.username) == (LinkOutcome.BLOCKED, None)
    assert _accounts(session_factory) == [(LISTED_ID, ayse, False)]
    assert _codes(session_factory)[0].used_at is None
    assert _events(session_factory, "TELEGRAM_USER_CHANGED") == []


def test_a_code_of_a_user_deactivated_since_does_not_work(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse")
    issued = _issue(session_factory, ayse)
    with session_factory() as session:
        session.execute(update(User).where(User.id == ayse).values(active=False))
        session.commit()

    assert _redeem(session_factory, issued.code, LISTED_ID).outcome is LinkOutcome.INVALID
    assert _accounts(session_factory) == []


@pytest.mark.parametrize(
    ("owner", "expected"), [("mehmet", LinkOutcome.TAKEN), ("ayse", LinkOutcome.ALREADY_LINKED)]
)
def test_an_id_bound_meanwhile_rolls_the_code_back_and_answers_by_the_final_state(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    owner: str,
    expected: LinkOutcome,
) -> None:
    # Ön okuma kimliği boş görür, ama ekleme anında satır vardır (başka bir istek bağlamıştır).
    users = {"ayse": _user(session_factory, "ayse"), "mehmet": _user(session_factory, "mehmet")}
    _bind(session_factory, users[owner], LISTED_ID)
    issued = _issue(session_factory, users["ayse"])
    real = link_module._account
    calls: list[int] = []

    def stale_first(session: Session, telegram_id: int) -> TelegramUser | None:
        calls.append(telegram_id)
        return None if len(calls) == 1 else real(session, telegram_id)

    monkeypatch.setattr(link_module, "_account", stale_first)

    result = _redeem(session_factory, issued.code, LISTED_ID)

    assert result.outcome is expected
    assert _accounts(session_factory) == [(LISTED_ID, users[owner], True)]
    used = _codes(session_factory)[0].used_telegram_id
    assert used == (LISTED_ID if expected is LinkOutcome.ALREADY_LINKED else None)
    assert _events(session_factory, "TELEGRAM_USER_CHANGED") == []


@pytest.mark.parametrize("bound", [False, True])
def test_a_code_consumed_meanwhile_binds_nothing(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, bound: bool
) -> None:
    # Ön denetim kodu kullanılabilir görür, ama koşullu güncelleme onu başka isteğin tükettiğini
    # bulur: ikinci bağlama olmaz.
    ayse = _user(session_factory, "ayse")
    if bound:
        _bind(session_factory, ayse, OTHER_ID)
    issued = _issue(session_factory, ayse)
    assert _redeem(session_factory, issued.code, LISTED_ID).outcome is LinkOutcome.LINKED
    monkeypatch.setattr(link_module, "_usable", lambda _link, _now: True)

    result = _redeem(session_factory, issued.code, OTHER_ID)

    assert result.outcome is LinkOutcome.INVALID
    assert _codes(session_factory)[0].used_telegram_id == LISTED_ID
    assert len(_events(session_factory, "TELEGRAM_USER_CHANGED")) == 1


# --- art arda geçersiz deneme -----------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_five_invalid_attempts_silence_a_chat_for_an_hour() -> None:
    clock = Clock()
    attempts = LinkAttempts(clock=clock)

    for _ in range(4):
        attempts.failed(LISTED_ID)
        assert not attempts.silenced(LISTED_ID)
    attempts.failed(LISTED_ID)

    assert attempts.silenced(LISTED_ID)
    assert not attempts.silenced(OTHER_ID)
    clock.now += 3599
    assert attempts.silenced(LISTED_ID)
    clock.now += 1
    assert not attempts.silenced(LISTED_ID)
    attempts.failed(LISTED_ID)  # sayaç sıfırdan başlar
    assert not attempts.silenced(LISTED_ID)


def test_a_success_resets_the_count_and_old_failures_are_forgotten() -> None:
    clock = Clock()
    attempts = LinkAttempts(clock=clock)
    for _ in range(4):
        attempts.failed(LISTED_ID)
        attempts.failed(OTHER_ID)

    attempts.succeeded(LISTED_ID)
    attempts.failed(LISTED_ID)
    clock.now += 3600
    attempts.failed(OTHER_ID)

    assert not attempts.silenced(LISTED_ID)
    assert not attempts.silenced(OTHER_ID)


# --- botun adı --------------------------------------------------------------------------------


def test_the_bot_name_is_written_atomically_and_read_back(tmp_path: Path) -> None:
    layout = prepare_data_dir(tmp_path / "data")
    assert read_bot_info(layout) is None

    write_bot_info(layout, "belgeee_test_bot", now=NOW)

    assert layout.telegram_bot_info_path == tmp_path / "data" / "telegram" / "bot.json"
    assert json.loads(layout.telegram_bot_info_path.read_text(encoding="utf-8")) == {
        "username": "belgeee_test_bot",
        "updated_at": NOW.isoformat(),
    }
    assert read_bot_info(layout) == BotInfo(username="belgeee_test_bot", updated_at=NOW)
    write_bot_info(layout, "baska_bir_bot", now=NOW)  # her açılışta yeniden yazılır
    assert read_bot_info(layout) == BotInfo(username="baska_bir_bot", updated_at=NOW)


@pytest.mark.parametrize("username", ["", "ab", "bot/../x", "a" * 33, "1belgeee_bot", "çbot_bot"])
def test_an_invalid_bot_name_is_not_written(tmp_path: Path, username: str) -> None:
    layout = prepare_data_dir(tmp_path / "data")

    with pytest.raises(ValueError, match="bot kullanıcı adı"):
        write_bot_info(layout, username)

    assert not layout.telegram_bot_info_path.exists()


@pytest.mark.parametrize(
    "content",
    [
        b"bozuk",
        b"[]",
        b"{}",
        b'{"username": 5}',
        b'{"username": "x y z"}',
        b'{"username": "belgeee_bot\\"><script>"}',
    ],
)
def test_an_unreadable_bot_file_counts_as_missing(tmp_path: Path, content: bytes) -> None:
    layout = prepare_data_dir(tmp_path / "data")
    layout.telegram_bot_info_path.parent.mkdir(parents=True)
    layout.telegram_bot_info_path.write_bytes(content)

    assert read_bot_info(layout) is None


def test_a_bad_timestamp_keeps_the_name(tmp_path: Path) -> None:
    layout = prepare_data_dir(tmp_path / "data")
    layout.telegram_bot_info_path.parent.mkdir(parents=True)
    layout.telegram_bot_info_path.write_text(
        '{"username": "belgeee_bot", "updated_at": "dun"}', encoding="utf-8"
    )

    assert read_bot_info(layout) == BotInfo(username="belgeee_bot", updated_at=None)


# --- bot: `/start <kod>` ----------------------------------------------------------------------


def _link_bot(
    session_factory: sessionmaker[Session], attempts: LinkAttempts | None = None
) -> BotHarness:
    telegram = FakeTelegram()
    application = build_application(
        polling_config(),
        session_factory,
        builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
        link_attempts=attempts,
    )
    return BotHarness(application, telegram)


def test_a_stranger_opening_the_link_is_bound_and_then_served(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse")
    issued = _issue(session_factory, ayse)
    bot = _link_bot(session_factory)

    bot.feed(
        message_update(1, OTHER_ID, "/start"),  # listede değil, kodsuz: kimliği söylenir (12.1.7)
        message_update(2, OTHER_ID, f"/start {issued.code}"),
        message_update(3, OTHER_ID, "/start"),  # artık listede
    )

    assert bot.telegram.sent_texts() == [
        not_linked_reply(OTHER_ID),
        with_number(LINKED_TEXT.format(username="ayse"), OTHER_ID),
        help_reply(OTHER_ID),
    ]
    assert [p["chat_id"] for p in bot.telegram.sent("sendMessage")] == [OTHER_ID] * 3
    assert _accounts(session_factory) == [(OTHER_ID, ayse, True)]
    assert "/yardim" in LINKED_TEXT


def test_the_link_handler_runs_before_the_gate_and_stops_the_update(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse")
    _bind(session_factory, ayse, LISTED_ID)
    issued = _issue(session_factory, ayse)
    bot = _link_bot(session_factory)

    # Listedeki kişi de kodla gelirse yalnız bağlantı yanıtı gider, yardım metni gitmez.
    bot.feed(message_update(1, LISTED_ID, f"/start {issued.code}"))

    assert bot.telegram.sent_texts() == [
        with_number(ALREADY_LINKED_TEXT.format(username="ayse"), LISTED_ID)
    ]
    assert LINK_GROUP in bot.application.handlers


def test_a_link_in_a_group_chat_is_ignored(session_factory: sessionmaker[Session]) -> None:
    issued = _issue(session_factory, _user(session_factory, "ayse"))
    bot = _link_bot(session_factory)

    bot.feed(message_update(1, OTHER_ID, f"/start {issued.code}", chat_type="group"))

    assert bot.telegram.methods() == []
    assert _accounts(session_factory) == []
    assert _codes(session_factory)[0].used_at is None


@pytest.mark.parametrize(
    ("setup", "reply"),
    [("taken", LINK_TAKEN_TEXT), ("blocked", LINK_BLOCKED_TEXT)],
)
def test_refusals_are_explained_to_the_sender(
    session_factory: sessionmaker[Session], setup: str, reply: str
) -> None:
    ayse = _user(session_factory, "ayse")
    owner = _user(session_factory, "mehmet") if setup == "taken" else ayse
    _bind(session_factory, owner, OTHER_ID, allowed=setup == "taken")
    issued = _issue(session_factory, ayse)
    bot = _link_bot(session_factory)

    bot.feed(message_update(1, OTHER_ID, f"/start {issued.code}"))

    assert bot.telegram.sent_texts() == [reply]
    assert "yöneticinize başvurun" in reply


def test_invalid_codes_get_one_generic_reply_and_the_sixth_attempt_gets_none(
    session_factory: sessionmaker[Session],
) -> None:
    issued = _issue(session_factory, _user(session_factory, "ayse"))
    clock = Clock()
    bot = _link_bot(session_factory, LinkAttempts(clock=clock))

    bot.feed(
        *(message_update(n, OTHER_ID, f"/start yanlis-kod-{n}") for n in range(1, 6)),
        message_update(6, OTHER_ID, "/start yanlis-kod-6"),
        # Sessizken doğru kod da işlenmez: kaba kuvvet denemesi kodu sınayamaz.
        message_update(7, OTHER_ID, f"/start {issued.code}"),
    )

    assert bot.telegram.sent_texts() == [INVALID_LINK_TEXT] * 5
    assert _accounts(session_factory) == []
    assert _codes(session_factory)[0].used_at is None
    # Başka sohbet etkilenmez; bir saat sonra sohbet yeniden yanıt alır.
    clock.now += 3600
    bot.feed(
        message_update(8, LISTED_ID, "/start bir iki"),
        message_update(9, OTHER_ID, f"/start {issued.code}"),
    )
    assert bot.telegram.sent_texts()[5:] == [
        INVALID_LINK_TEXT,
        with_number(LINKED_TEXT.format(username="ayse"), OTHER_ID),
    ]


def test_a_link_without_a_known_sender_binds_nothing(
    session_factory: sessionmaker[Session],
) -> None:
    issued = _issue(session_factory, _user(session_factory, "ayse"))
    bot = _link_bot(session_factory)

    bot.feed(message_update(1, None, f"/start {issued.code}"))

    assert bot.telegram.methods() == []
    assert _codes(session_factory)[0].used_at is None


@pytest.mark.parametrize("text", ["/yardim", "merhaba"])
def test_a_stranger_without_a_code_still_gets_no_reply(
    session_factory: sessionmaker[Session], text: str
) -> None:
    _issue(session_factory, _user(session_factory, "ayse"))
    bot = _link_bot(session_factory)

    bot.feed(message_update(1, OTHER_ID, text))

    assert bot.telegram.methods() == []


def test_neither_code_nor_ids_nor_names_reach_the_log(
    session_factory: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    issued = _issue(session_factory, _user(session_factory, "ayse-gizli"))
    bot = _link_bot(session_factory)

    with caplog.at_level(logging.DEBUG, logger="app"):
        bot.feed(
            message_update(1, OTHER_ID, "/start yanlis-kod-123"),
            message_update(2, OTHER_ID, f"/start {issued.code}"),
        )

    assert "update_id=2" in caplog.text and "linked" in caplog.text
    for secret in (issued.code, "yanlis-kod-123", str(OTHER_ID), "ayse-gizli"):
        assert secret not in caplog.text


def test_a_database_failure_answers_briefly_and_still_stops_the_update(
    whitelist: Callable[..., None], caplog: pytest.LogCaptureFixture
) -> None:
    def broken_factory() -> Any:
        raise RuntimeError(f"veritabanı yok: {LISTED_ID} gizli-kod")

    whitelist(LISTED_ID)
    telegram = FakeTelegram()
    application = build_application(
        polling_config(),
        broken_factory,  # type: ignore[arg-type]
        builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
    )
    bot = BotHarness(application, telegram)

    with caplog.at_level(logging.ERROR):
        bot.feed(message_update(1, LISTED_ID, "/start gizli-kod"))

    assert telegram.sent_texts() == [LINK_FAILED_TEXT]
    assert "RuntimeError" in caplog.text
    assert "gizli-kod" not in caplog.text and str(LISTED_ID) not in caplog.text


def test_a_failed_reply_is_logged_and_the_update_still_stops(
    session_factory: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    ayse = _user(session_factory, "ayse")
    _bind(session_factory, ayse, LISTED_ID)
    bot = _link_bot(session_factory)
    bot.telegram.fail_send = True

    with caplog.at_level(logging.ERROR):
        bot.feed(message_update(1, LISTED_ID, "/start yanlis-kod"))

    # Yanıt gönderilemedi; yardım işleyicisine de geçilmedi (tek deneme).
    assert bot.telegram.methods() == ["sendMessage"]
    assert "Telegram bağlantısı yanıtlanamadı (BadRequest)" in caplog.text


# --- bot: açılışta adını yazar -----------------------------------------------------------------


def _start(application: Any) -> None:
    async def _run() -> None:
        await application.initialize()
        try:
            await application.post_init(application)
        finally:
            await application.shutdown()

    asyncio.run(_run())


def test_the_bot_writes_its_name_on_start_after_any_earlier_hook(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    layout = prepare_data_dir(tmp_path / "data")
    telegram = FakeTelegram()
    order: list[str] = []
    application = (
        ApplicationBuilder()
        .token(polling_config().token)
        .request(telegram)
        .get_updates_request(telegram)
        .build()
    )

    async def earlier(_app: Any) -> None:
        order.append("önceki")

    application.post_init = earlier
    register_bot_info(application, layout)

    _start(application)

    assert order == ["önceki"]
    info = read_bot_info(layout)
    assert info is not None and info.username == "belgeee_test_bot"  # FakeTelegram `getMe`
    assert "getMe" in [name for name, _ in telegram.calls]


def test_build_application_writes_the_name_only_when_given_a_data_dir(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    layout = prepare_data_dir(tmp_path / "data")
    telegram = FakeTelegram()
    without = build_application(
        polling_config(), session_factory, builder=ApplicationBuilder().request(telegram)
    )
    with_layout = build_application(
        polling_config(),
        session_factory,
        builder=ApplicationBuilder().request(telegram),
        layout=layout,
    )

    assert without.post_init is None
    _start(with_layout)
    assert read_bot_info(layout) is not None
    assert isinstance(with_layout.handlers[LINK_GROUP][0].callback, LinkStart)


def test_a_name_that_cannot_be_written_does_not_stop_the_bot(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    layout = prepare_data_dir(tmp_path / "data")
    (layout.root / "telegram").write_text("dizin değil", encoding="utf-8")
    telegram = FakeTelegram()
    application = ApplicationBuilder().token(polling_config().token).request(telegram).build()
    register_bot_info(application, layout)

    with caplog.at_level(logging.ERROR):
        _start(application)

    assert "Botun kullanıcı adı veri dizinine yazılamadı" in caplog.text
    assert read_bot_info(layout) is None
