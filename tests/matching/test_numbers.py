"""15.3.3 — kişisel numaranın karşılaştırması: olduğu gibi saklanır, boşluk, tire, nokta ve harf
büyüklüğü farkı yok sayılır; doğrulama algoritması yoktur (`app.matching.numbers`)."""

from __future__ import annotations

import pytest
from sqlalchemy import literal, select
from sqlalchemy.orm import Session

from app.matching.numbers import (
    personal_number_column,
    personal_number_key,
    same_personal_number,
    strip_separators,
)


@pytest.mark.parametrize(
    ("left", "right", "same"),
    [
        ("1204991715003", "1204-991 715.003", True),  # Sırp JMBG, ayırıcılı yazım
        ("12345678901", "123 456 789 01", True),  # Türk kimlik no
        ("ab-12.34", "AB1234", True),  # harf büyüklüğü
        ("1204991715003", "1204991715004", False),
        # Kontrol hanesi denetlenmez: geçersiz JMBG de numaradır (15.3.3).
        ("0000000000000", "0000000000000", True),
        ("12/34", "1234", False),  # yalnız boşluk, tire ve nokta yok sayılır
    ],
)
def test_two_numbers_are_the_same_apart_from_separators_and_case(
    left: str, right: str, same: bool
) -> None:
    assert same_personal_number(left, right) is same


def test_the_key_keeps_letters_and_digits_only_without_separators() -> None:
    assert strip_separators(" AB-12 .34 ") == "AB1234"
    assert personal_number_key(" AB-12 .34 ") == "ab1234"


def test_the_sql_expression_strips_the_same_separators(session: Session) -> None:
    stored = literal("AB-12 34.5")

    assert session.scalar(select(personal_number_column(stored))) == "AB12345"
    assert session.scalar(select(personal_number_column(stored).icontains("ab1234"))) == 1
