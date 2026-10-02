"""10.10.3 gösterim anında çeviri — `Translatable` ve `translate` (PLAN.md §D95; tm 154).

Çekirdek modüllerin metni kaynak dilde kalır (aynı metin `profil.md`'ye, olay loguna, bota ve
komut satırına gider; onlar çevrilmez). Değer taşıyan metin `Translatable`'dır: dizge olarak bugünkü
Türkçe metnin aynısıdır, panel onu `translate` ile isteğin dilinde gösterir.
"""

from __future__ import annotations

import contextvars
from datetime import UTC, datetime

import pytest

from app.groups.packages import OPEN_LABEL, PackageItemView, PackageView
from app.i18n import N_, Translatable, translate, use_language
from app.matching.records import ContactFormError, normalized_contact
from app.matching.status import StatusReasonError, normalized_reason
from app.web.auth import UserCreationError, normalize_username


def test_translatable_is_the_source_text_itself() -> None:
    text = Translatable(N_("Not en çok {limit} karakter olabilir."), limit=120)
    assert text == "Not en çok 120 karakter olabilir."
    assert isinstance(text, str)
    assert str(text) == "Not en çok 120 karakter olabilir."
    assert text.template == "Not en çok {limit} karakter olabilir."
    assert text.values == {"limit": 120}


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("tr", "Not en çok 120 karakter olabilir."),
        ("en", "The note can be at most 120 characters long."),
        ("sr", "Napomena može imati najviše 120 znakova."),
    ],
)
def test_translate_formats_the_translated_template(language: str, expected: str) -> None:
    text = Translatable(N_("Not en çok {limit} karakter olabilir."), limit=120)
    with use_language(language):
        assert translate(text) == expected


def test_translate_looks_up_plain_text_and_keeps_unknown_text() -> None:
    with use_language("en"):
        assert translate("Paket bulunamadı.") == "Package not found."
        assert translate("Dmitry Vasiliev") == "Dmitry Vasiliev"


@pytest.mark.parametrize("empty", [None, ""])
def test_translate_of_nothing_is_empty_not_the_catalog_header(empty: str | None) -> None:
    with use_language("en"):
        assert translate(empty) == ""


def test_nested_translatable_values_are_translated_and_plain_values_are_not() -> None:
    inner = Translatable(N_("belge numarası"))
    text = Translatable(N_("Belgede görülen {label} kaldırılmış bir kayda uyuyor"), label=inner)
    assert text == "Belgede görülen belge numarası kaldırılmış bir kayda uyuyor"
    with use_language("en"):
        assert translate(text) == "A document number seen in a document matches a removed record"
    data = Translatable(
        "{name} · {pages}", name="belge numarası", pages=Translatable(N_("tüm dosya"))
    )
    with use_language("en"):
        # Düz değer veridir (dosya adı): msgid'le aynı yazılsa da çevrilmez.
        assert translate(data) == "belge numarası · whole file"


def test_translate_of_an_exception_uses_its_message() -> None:
    with pytest.raises(StatusReasonError) as caught:
        normalized_reason("x" * 201)
    assert str(caught.value) == "Not en çok 200 karakter olabilir."
    with use_language("sr"):
        assert translate(caught.value) == "Napomena može imati najviše 200 znakova."


def test_core_messages_stay_in_the_source_language_outside_a_request() -> None:
    """İstek dışında (bot, komut satırı, işçi) dil varsayılanı İngilizcedir; çekirdeğin metni yine
    Türkçedir — gösterimde çeviren paneldir."""

    def messages() -> tuple[str, str, str]:
        with pytest.raises(ContactFormError) as contact:
            normalized_contact("address", "x" * 501)
        with pytest.raises(UserCreationError) as username:
            normalize_username("ab")
        package = PackageView(
            id=1,
            employee_id="E0001",
            group_id=1,
            group_name="Work permit file",
            group_archived=False,
            status="open",
            note=None,
            requested_by="ik",
            requested_at=datetime(2026, 10, 2, tzinfo=UTC),
            completed_at=None,
            cancelled_at=None,
            cancelled_by=None,
            cancel_note=None,
            items=(PackageItemView(1, 1, "label", "Passport", True, None, None),),
        )
        return contact.value.problems["value"][0], str(username.value), package.state_label

    contact, username, state = contextvars.Context().run(messages)
    assert contact == "Değer en çok 500 karakter olabilir."
    assert username == "Kullanıcı adı en az 3 karakter olmalı."
    assert state == OPEN_LABEL.format(met=0, total=1) == "Açık — 0/1 zorunlu kalem"
    with use_language("en"):
        assert translate(contact) == "The value can be at most 500 characters long."
        assert translate(state) == "Open — 0/1 required items"
