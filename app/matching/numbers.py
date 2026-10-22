"""Kişisel numaranın karşılaştırılması — PRD 15.3.3 (PLAN.md §D123 e).

`employees.personal_number` çalışanın kendi ülkesinin vatandaşlık/kimlik numarasıdır (Sırp JMBG,
Türk TC kimlik no, …); ülkeden ülkeye uzunluk ve biçim değiştiği için **olduğu gibi** saklanır.
Karşılaştırma ve arama boşluk, tire ve nokta farkını yok sayar; harf büyüklüğü de fark etmez.
Sayısal doğrulama (JMBG kontrol hanesi gibi) bu sürümde yoktur. Numara hiçbir olaya, bildirime ve
loga değer olarak yazılmaz — bu modül yalnız karşılaştırma anahtarı verir.

Python tarafı (`personal_number_key`) ve SQL tarafı (`personal_number_column`) aynı ayırıcıları
siler; SQL'de harf büyüklüğünü `icontains` katlar.
"""

from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement

# `employees.personal_number` `String(64)`dür.
PERSONAL_NUMBER_MAX_LENGTH = 64
# 15.3.3: yok sayılan ayırıcılar. Denetim karakteri profil formunda reddedilir; sekme ve satır
# sonu numaraya girmez, bu yüzden SQL tarafı yalnız boşluğu siler.
SEPARATORS = (" ", "-", ".")
_SEPARATOR = re.compile(r"[ .\-]+")


def strip_separators(value: str) -> str:
    """Boşluk, tire ve nokta silinmiş numara; harf büyüklüğü korunur (SQL araması katlar)."""
    return _SEPARATOR.sub("", value)


def personal_number_key(value: str) -> str:
    """İki numaranın aynı olup olmadığının anahtarı: ayırıcısız, harf büyüklüğü katlanmış."""
    return strip_separators(value).casefold()


def same_personal_number(left: str, right: str) -> bool:
    """15.3.3 — iki kişisel numara ayırıcı ve harf büyüklüğü farkı dışında aynı mı."""
    return personal_number_key(left) == personal_number_key(right)


def personal_number_column(column: ColumnElement[str | None]) -> ColumnElement[str]:
    """SQL'de ayırıcıları silinmiş numara: aramanın (10.4.2) karşılaştırdığı ifade."""
    expression: ColumnElement[str] = column  # type: ignore[assignment]
    for separator in SEPARATORS:
        expression = func.replace(expression, separator, "")
    return expression
