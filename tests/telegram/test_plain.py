"""12.1.9 — botun mesajları sade, kısa ve teknik terimsiz (PLAN.md §D98; tm 161).

Kurallar `app.telegram.plain`'dedir: yasak sözcük 0, parti numarası (uuid ya da `u_…`) 0, `E` +
rakam çalışan numarası 0, `%` ve MB 0, liste dışı satır ≤ 4, liste öğesi ≤ 5. Bütün bot metin
sabitleri ve üretilen örnek mesajlar (özet: tamamlandı / kısmen / işlenemedi, yedi belgeli özet,
tekrar, kuyruk bildirimi, belge isteme yanıtları, bağlantı yanıtları, kimlik yanıtı, yardım) üç
dilde bu denetimden geçer.
"""

from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from typing import Any

import pytest

from app.db.models import UploadStatus
from app.i18n import gettext, use_language
from app.telegram import bot, handlers, intent, notify
from app.telegram.link import LinkOutcome, LinkRedemption
from app.telegram.plain import FORBIDDEN_WORDS, MAX_ITEMS, MAX_LINES, problems

LANGUAGES = ("tr", "en", "sr")
TELEGRAM_ID = 5_000_000_001


# --- denetimin kendisi -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("Parti u_20260101_001 işlenemedi.", ["yasak sözcük: parti", "parti numarası"]),
        ("Kuyruğa düşen 3 öğe.", ["yasak sözcük: kuyruğa"]),
        ("Sorun: 0f8fad5b-d9cb-469f-a165-70867728950e", ["parti numarası"]),
        ("Ahmet Çakar (E0001)", ["çalışan numarası"]),
        ("Disk %91 dolu.", ["yüzde işareti"]),
        ("Dosya 20 MB sınırını aşıyor.", ["yasak sözcük: MB"]),
        ("RuntimeError oluştu.", ["hata adı"]),
        (
            "Yapay zekâ sağlayıcısı kurulamadı.",
            ["yasak sözcük: yapay zekâ", "yasak sözcük: sağlayıcı"],
        ),
        ("Bitti.\n• Ehliyet — Ahmet Çakar", []),
        ("Bu belgeyi açamadım; Kanadalı mı?", []),  # sözcük içindeki "plan"/"parti" değil
    ],
)
def test_the_checker_finds_technical_content(text: str, found: list[str]) -> None:
    assert problems(text, "tr") == found


def test_the_checker_limits_lines_and_list_items() -> None:
    assert problems("\n".join(["Satır."] * MAX_LINES), "tr") == []
    assert problems("\n".join(["Satır."] * (MAX_LINES + 1)), "tr") == [
        f"liste dışı {MAX_LINES + 1} satır (en çok {MAX_LINES})"
    ]
    items = "\n".join(f"• Öğe {n}" for n in range(MAX_ITEMS + 1))
    assert problems("Bitti.\n" + items, "tr") == [
        f"listede {MAX_ITEMS + 1} öğe (en çok {MAX_ITEMS})"
    ]


def test_every_language_has_a_forbidden_word_list() -> None:
    assert set(FORBIDDEN_WORDS) == set(LANGUAGES)
    assert "batch" in FORBIDDEN_WORDS["en"] and "serija" in FORBIDDEN_WORDS["sr"]


# --- bütün metinler ve örnek mesajlar ----------------------------------------------------------

BOT_TEXTS = sorted(
    {
        value
        for module in (bot, handlers, intent)
        for name, value in vars(module).items()
        if name.endswith("_TEXT") and isinstance(value, str)
    }
)


class FakeSession:
    """`build_summary`'nin sorguları sırasıyla: belgeler, kuyruk sayısı, tekrar sayısı."""

    def __init__(self, documents: list[Any], queued: int, duplicates: int) -> None:
        self._documents = documents
        self._counts = deque([queued, duplicates])

    def scalars(self, _query: object) -> list[Any]:
        return self._documents

    def scalar(self, _query: object) -> int:
        return self._counts.popleft()


def _document(type_name: str = "Serbian Driving License") -> Any:
    return SimpleNamespace(
        document_type=SimpleNamespace(name=type_name),
        employee=SimpleNamespace(given_names="AHMET", surname="ÇAKAR"),
    )


def _summary(status: UploadStatus, documents: int, queued: int = 0, duplicates: int = 0) -> str:
    processed = SimpleNamespace(status=status, plan=SimpleNamespace(id=1))
    session = FakeSession([_document() for _ in range(documents)], queued, duplicates)
    return handlers.build_summary(session, "u_20260101_001", processed)  # type: ignore[arg-type]


def _samples() -> list[str]:
    employee = SimpleNamespace(
        id="E0001", given_names="AHMET", surname="ÇAKAR", status="active", date_of_birth=None
    )
    return [
        *(gettext(text) for text in BOT_TEXTS),
        bot.help_reply(TELEGRAM_ID),
        bot.not_linked_reply(TELEGRAM_ID),
        bot.with_number(bot.link_reply(LinkRedemption(LinkOutcome.LINKED, "ayse")), TELEGRAM_ID),
        *(bot.link_reply(LinkRedemption(outcome)) for outcome in LinkOutcome),
        handlers.received_text(1),
        handlers.received_text(7),
        _summary(UploadStatus.DONE, 1),
        _summary(UploadStatus.DONE, 7, queued=2, duplicates=1),
        _summary(UploadStatus.PARTIAL, 3, queued=12, duplicates=2),
        _summary(UploadStatus.DONE, 0),
        _summary(UploadStatus.FAILED, 0),
        notify.queue_message(1),
        notify.queue_message(23),
        gettext(intent.NO_DOCUMENT_TEXT).format(
            employee=intent._employee_label(employee), kind="ehliyet"
        ),  # type: ignore[arg-type]
    ]


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_bot_message_is_plain(language: str) -> None:
    assert len(BOT_TEXTS) >= 30
    with use_language(language):
        samples = _samples()
    for text in samples:
        assert problems(text, language) == [], text


def test_the_seven_document_summary_lists_four_and_counts_the_rest() -> None:
    with use_language("tr"):
        summary = _summary(UploadStatus.DONE, 7, queued=2, duplicates=1)

    assert summary == (
        "Bitti.\n" + "• Serbian Driving License — AHMET ÇAKAR\n" * 4 + "• ve 3 belge daha\n"
        "2 belgeye bakmanız gerekiyor; panelde kontrol edin.\n"
        "1 dosyayı daha önce göndermiştiniz, yeniden eklemedim."
    )


def test_a_partial_summary_says_some_pages_could_not_be_read() -> None:
    with use_language("tr"):
        summary = _summary(UploadStatus.PARTIAL, 1, queued=1)

    assert summary.splitlines()[0] == "Bitti."
    assert summary.endswith("Bazı sayfalar okunamadı; panelde kontrol edin.")


def test_blocked_and_taken_links_get_one_text() -> None:
    blocked = bot.link_reply(LinkRedemption(LinkOutcome.BLOCKED))
    taken = bot.link_reply(LinkRedemption(LinkOutcome.TAKEN))

    assert blocked == taken
