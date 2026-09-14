"""İsim sadeleştirme — dosya ve klasör adı için slug (PRD 00.4.2).

Türkçe, Kiril ve Arap yazımlı metin `[A-Za-z0-9]` kelimelerine indirilir; kelimeler verilen
ayırıcıyla (`_` veya `-`) birleşir. Sıra:

1. Kesme işaretleri silinir (`O'Brien → OBrien`, `Мар'яна → Mariana`); kelimeyi bölmez.
2. Tablodaki harfler Latin karşılığına çevrilir: Türkçe harfler §20.2.1 eşlemesiyle
   (`ç→c`, `ş→s`, `ğ→g`, `ı→i`, `ö→o`, `ü→u`), Rusça Kiril ICAO Doc 9303 eşlemesiyle
   (`Юлия → Iuliia`), diğer Kiril harfleri yakın Latin karşılığıyla, Arapça sade ünsüz
   eşlemesiyle (`خ → kh`). Arapça için ICAO'nun geri çevrilebilir `X`'li biçimi dosya adında
   okunaksız olduğu için kullanılmaz.
3. Kalan aksanlar ayrıştırılıp atılır (`é → e`), her yazıdaki rakamlar ASCII rakama iner.
4. Geri kalan her şey kelime ayırıcıdır; tablo dışı yazılar (ör. Çince) düşer.

Bu slug yalnız ad üretir. Kişi eşleştirmesinin normalizasyonu (05.1, 05.2) ayrı bir iştir ve
dosya adına dayanmaz.
"""

from __future__ import annotations

import re
import unicodedata

# Kesme işareti ve benzerleri: kelimeyi bölmeden silinir.
_APOSTROPHES = str.maketrans("", "", "'`´‘’ʹʻʼˈ")

_TURKISH = {"ç": "c", "ş": "s", "ğ": "g", "ı": "i", "ö": "o", "ü": "u"}

# Ayrıştırmayla (NFKD) Latin harfine inmeyen Latin harfleri.
_LATIN_EXTRA = {
    "ß": "ss",
    "æ": "ae",
    "œ": "oe",
    "ø": "o",
    "đ": "d",
    "ð": "d",
    "ł": "l",
    "þ": "th",
    "ħ": "h",
}

# Rusça harfler ICAO Doc 9303 eşlemesiyle; Ukraynaca, Belarusça, Sırpça, Makedonca ve Orta Asya
# Kiril harfleri yakın Latin karşılığıyla. Harf tek başına dil söylemediği için `г` hep `g`dir.
_CYRILLIC = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "ґ": "g",
    "д": "d",
    "ђ": "d",
    "ѓ": "g",
    "е": "e",
    "ё": "e",
    "є": "ie",
    "ж": "zh",
    "з": "z",
    "ѕ": "dz",
    "и": "i",
    "і": "i",
    "ї": "i",
    "й": "i",
    "ј": "j",
    "к": "k",
    "л": "l",
    "љ": "lj",
    "м": "m",
    "н": "n",
    "њ": "nj",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "ћ": "c",
    "ќ": "k",
    "у": "u",
    "ў": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "џ": "dz",
    "ш": "sh",
    "щ": "shch",
    "ъ": "ie",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "iu",
    "я": "ia",
    "ә": "a",
    "ғ": "g",
    "қ": "k",
    "ң": "n",
    "ө": "o",
    "ұ": "u",
    "ү": "u",
    "һ": "h",
    "ҳ": "h",
    "ҷ": "j",
    "ӣ": "i",
    "ӯ": "u",
}

# Arapça (ve Farsça/Urduca ek harfler) — sade ünsüz eşlemesi. Harekeler işaret olarak düşer.
_ARABIC = {
    "ء": "",
    "آ": "a",
    "أ": "a",
    "ؤ": "u",
    "إ": "i",
    "ئ": "i",
    "ا": "a",
    "ٱ": "a",
    "ب": "b",
    "ة": "a",
    "ت": "t",
    "ث": "th",
    "ج": "j",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "dh",
    "ر": "r",
    "ز": "z",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "d",
    "ط": "t",
    "ظ": "z",
    "ع": "a",
    "غ": "gh",
    "ـ": "",
    "ف": "f",
    "ق": "q",
    "ك": "k",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "ه": "h",
    "و": "w",
    "ى": "a",
    "ي": "y",
    "پ": "p",
    "چ": "ch",
    "ژ": "zh",
    "ڤ": "v",
    "ک": "k",
    "گ": "g",
    "ی": "y",
    "ٹ": "t",
    "ڈ": "d",
    "ڑ": "r",
    "ں": "n",
    "ھ": "h",
    "ہ": "h",
    "ۃ": "a",
    "ے": "e",
}


def _build_table() -> dict[int, str]:
    table: dict[int, str] = {ord("İ"): "I"}
    for mapping in (_TURKISH, _LATIN_EXTRA, _CYRILLIC):
        for lower, latin in mapping.items():
            table[ord(lower)] = latin
            upper = lower.upper()
            # `ß.upper()` iki harftir; tek karşılığı olmayan büyük harf tabloya girmez.
            if len(upper) == 1 and upper != lower and upper.isalpha() and not upper.isascii():
                table[ord(upper)] = latin.capitalize()
    for letter, latin in _ARABIC.items():
        table[ord(letter)] = latin
    return table


_TRANSLITERATION = _build_table()
_NON_WORD = re.compile(r"[^A-Za-z0-9]+")


class SlugError(ValueError):
    """Metinden `[A-Za-z0-9]` kümesinde tek bir karakter bile kalmadı."""


def transliterate(text: str) -> str:
    """Metni ASCII'ye indirir; tabloda karşılığı olmayan ASCII dışı karakter boşluk olur."""
    # NFKC: Arapça sunum biçimleri (`ﻻ`), tam genişlik ve bağ harfleri önce temel harfe iner.
    translated = unicodedata.normalize("NFKC", text.translate(_APOSTROPHES))
    translated = translated.translate(_TRANSLITERATION)
    result: list[str] = []
    for char in unicodedata.normalize("NFKD", translated):
        if unicodedata.combining(char):
            continue
        if char.isascii():
            result.append(char)
        elif char.isdecimal():
            result.append(str(unicodedata.decimal(char)))
        else:
            result.append(" ")
    return "".join(result)


def slugify(
    text: str,
    separator: str = "_",
    *,
    capitalize: bool = False,
    max_length: int | None = None,
) -> str:
    """`[A-Za-z0-9]` kelimelerini `separator` ile birleştirir; boş sonuçta `SlugError`.

    `capitalize` her kelimeyi büyük harfle başlatıp gerisini küçültür (`VASILEV → Vasilev`);
    kapalıyken harf büyüklüğü korunur. `max_length` verilirse sonuç o uzunluğa kelime
    sınırından kısaltılır, ilk kelime tek başına uzunsa kesilir. Sonuç hiçbir zaman ayırıcıyla
    başlamaz veya bitmez.
    """
    if separator not in ("_", "-"):
        raise ValueError(f"Ayırıcı '_' veya '-' olmalı: {separator!r}")
    if max_length is not None and max_length < 1:
        raise ValueError(f"max_length 1 veya büyük olmalı: {max_length}")
    words = [word for word in _NON_WORD.split(transliterate(text)) if word]
    if not words:
        raise SlugError("Metinden dosya adına uygun karakter çıkmadı")
    if capitalize:
        words = [word.capitalize() for word in words]
    if max_length is None:
        return separator.join(words)
    result = words[0][:max_length]
    for word in words[1:]:
        candidate = f"{result}{separator}{word}"
        if len(candidate) > max_length:
            break
        result = candidate
    return result
