"""İsim normalizasyonu ve harf çevirisi — kişi eşleştirmesinin isim anahtarı (PRD 05.1.1, 05.2.1,
§20.2.1).

Aynı kişinin farklı yazılmış adı aynı anahtara iner; `employee_aliases.normalized_name` bu
anahtardır. Sıra:

1. Kiril ve Arap harfleri ICAO Doc 9303 Bölüm 3 §6 tablolarıyla Latin'e çevrilir
   (`transliterate_name`, aşağıda). Tablo harfleri yazıldığı gibi görmelidir: `й`/`и`, `ё`/`е`
   ve şedde (`ّ`) aksan atılınca ayırt edilemez. Tablonun çıktısı ASCII olduğu için bu adımın
   §20.2.1'deki sırasından öne alınması başka hiçbir harfin sonucunu değiştirmez.
2. Harf büyüklüğü katlanır ve aksanlar kaldırılır: Unicode uyumluluk katlaması (NFKD +
   casefold) sonrası birleşen işaretler atılır (`É → e`, `İ → i`, `ß → ss`, `ﬁ → fi`).
3. Türkçe harfler §20.2.1 eşlemesiyle (`ç→c`, `ş→s`, `ğ→g`, `ı→i`, `ö→o`, `ü→u`), ayrışmayan
   Latin harfleri yakın karşılığıyla (`ł → l`, `ø → o`, `æ → ae`) iner.
4. Noktalama sadeleşir: kesme işaretleri ve görünmez biçim karakterleri kelimeyi bölmeden
   silinir (`O'Brien → obrien`, MRZ yazımıyla aynı); harf ve rakam dışındaki her şey kelime
   ayırıcıdır (`Jean-Pierre → jean pierre`), çoklu boşluk tek boşluk olur.
5. Kelimeler alfabetik sıralanır; ad-soyad sırası farkı anahtarı değiştirmez. Tekrarlanan
   kelime korunur.

Harf çevirisi (05.2.1) tablonun Unicode kod noktası sütununa göre yapılır:

- **Kiril** (Tablo B): varsayılan sütun (`Юлия → Iuliia`, `Васильев → Vasilev`). Belgenin dili
  (ISO 639-1) verilirse tablonun dil istisnaları uygulanır — `be`, `bg`, `mk`, `sr`, `uk`;
  Ukraynacada kelime başındaki `Є Ї Й Ю Я` `YE YI Y YU YA` olur. Tabloda satırı olmayan `Ь`
  yazılmaz, `Ћ` `C` olur; satırı olmayan ama ayrışan harf (`Ѓ`, `Ѝ`, `Ӣ`) temel harfiyle çevrilir.
  Bunların dışındaki tablo dışı harfler (Kazakça `Қ` gibi) tahminle indirilmez, olduğu gibi kalır.
- **Arap** (Tablo C, MRZ sütunu): `ح → XH`, `خ → XKH`, `ع → E`; harekeler ve tatvil yazılmaz,
  şedde önceki harfi ikiler (`عبّاس → EBBAS`), `ة` ad parçasının sonunda `XAH`, başka yerde
  `XTA` olur. Sunum biçimleri (`ﻻ`) önce temel harflere iner.

`transliterate_name` orijinal yazımı dokunmadan, Latin karşılığıyla birlikte döndürür. Kelimesiz
isim (yalnız noktalama) `EmptyNameError` verir — boş anahtar hiçbir zaman eşleştirmeye girmez.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

# Kesme işareti ve benzerleri: kelimeyi bölmeden silinir (ICAO MRZ yazımı da atar).
_APOSTROPHES = "'`´‘’‛′ʹʻʼʽʾʿˈ＇"

_TURKISH = {"ç": "c", "ş": "s", "ğ": "g", "ı": "i", "ö": "o", "ü": "u"}

# Ayrıştırmayla (NFKD) Latin harfine inmeyen Latin harfleri.
_LATIN_EXTRA = {
    "æ": "ae",
    "œ": "oe",
    "ø": "o",
    "đ": "d",
    "ð": "d",
    "ł": "l",
    "ŧ": "t",
    "ħ": "h",
    "ŋ": "n",
    "þ": "th",
}

_DROP_APOSTROPHES = str.maketrans("", "", _APOSTROPHES)
_LETTERS = str.maketrans(_TURKISH | _LATIN_EXTRA | dict.fromkeys(_APOSTROPHES))

# ICAO Doc 9303 Bölüm 3 §6 Tablo B, varsayılan sütun; anahtar büyük harftir.
_CYRILLIC = {
    "Ё": "E",
    "Ђ": "D",  # U+0402; tablo satırında glif `Ћ` basılı, kod noktası esas (C24)
    "Є": "IE",
    "Ѕ": "DZ",
    "І": "I",
    "Ї": "I",
    "Ј": "J",
    "Љ": "LJ",
    "Њ": "NJ",
    "Ќ": "K",
    "Ў": "U",
    "Џ": "DZ",
    "А": "A",
    "Б": "B",
    "В": "V",
    "Г": "G",
    "Д": "D",
    "Е": "E",
    "Ж": "ZH",
    "З": "Z",
    "И": "I",
    "Й": "I",
    "К": "K",
    "Л": "L",
    "М": "M",
    "Н": "N",
    "О": "O",
    "П": "P",
    "Р": "R",
    "С": "S",
    "Т": "T",
    "У": "U",
    "Ф": "F",
    "Х": "KH",
    "Ц": "TS",
    "Ч": "CH",
    "Ш": "SH",
    "Щ": "SHCH",
    "Ъ": "IE",
    "Ы": "Y",
    "Э": "E",
    "Ю": "IU",
    "Я": "IA",
    "Ѫ": "U",
    "Ѵ": "Y",
    "Ґ": "G",
    "Ғ": "G",
    "Һ": "C",
    # Tabloda satırı yok (C24): yumuşatma işareti ulusal ICAO uygulamalarında yazılmaz; `Ћ`
    # Sırp Latin yazısında `Ć`dir, Tablo A'da `C`.
    "Ь": "",
    "Ћ": "C",
}

# Tablo B'nin dil istisnaları (ISO 639-1). Sırpça `Г → H` tablonun yazdığı gibidir (D7).
_CYRILLIC_EXCEPTIONS = {
    "be": {"Ё": "IO", "Г": "H"},
    "bg": {"Щ": "SHT"},
    "mk": {"Ќ": "KJ", "Џ": "DJ", "Х": "H", "Ц": "C", "Ғ": "GJ"},
    "sr": {"Г": "H", "Ж": "Z", "Х": "H", "Ц": "C", "Ч": "C", "Ш": "S"},
    "uk": {"Г": "H", "И": "Y"},
}
_CYRILLIC_TABLES = {
    language: _CYRILLIC | exceptions for language, exceptions in _CYRILLIC_EXCEPTIONS.items()
}

# Ukraynaca: harf kelimenin ilk harfiyse ("if Ukrainian first character").
_UKRAINIAN_WORD_INITIAL = {"Є": "YE", "Ї": "YI", "Й": "Y", "Ю": "YU", "Я": "YA"}

# ICAO Doc 9303 Bölüm 3 §6 Tablo C, MRZ sütunu. "(Not encoded)" satırları boş karşılıktır.
_ARABIC = {
    "ء": "XE",
    "آ": "XAA",
    "أ": "XAE",
    "ؤ": "U",
    "إ": "I",
    "ئ": "XI",
    "ا": "A",
    "ب": "B",
    "ة": "XTA",  # ad parçasının sonunda XAH
    "ت": "T",
    "ث": "XTH",
    "ج": "J",
    "ح": "XH",
    "خ": "XKH",
    "د": "D",
    "ذ": "XDH",
    "ر": "R",
    "ز": "Z",
    "س": "S",
    "ش": "XSH",
    "ص": "XSS",
    "ض": "XDZ",
    "ط": "XTT",
    "ظ": "XZZ",
    "ع": "E",
    "غ": "G",
    "ـ": "",
    "ف": "F",
    "ق": "Q",
    "ك": "K",
    "ل": "L",
    "م": "M",
    "ن": "N",
    "ه": "H",
    "و": "W",
    "ى": "XAY",
    "ي": "Y",
    "ً": "",  # fathatan
    "ٌ": "",  # dammatan
    "ٍ": "",  # kasratan
    "َ": "",  # fatha
    "ُ": "",  # damma
    "ِ": "",  # kasra
    "ْ": "",  # sukun
    "ٰ": "",  # üst elif
    "ٱ": "XXA",
    "ٹ": "XXT",
    "ټ": "XRT",
    "پ": "P",
    "ځ": "XKE",
    "څ": "XXH",
    "چ": "XC",
    "ڈ": "XXD",
    "ډ": "XDR",
    "ڑ": "XXR",
    "ړ": "XRR",
    "ږ": "XRX",
    "ژ": "XJ",
    "ښ": "XXS",
    "ڜ": "",
    "ڢ": "",
    "ڧ": "",
    "ڨ": "",
    "ک": "XKK",
    "ګ": "XXK",
    "ڭ": "XNG",
    "گ": "XGG",
    "ں": "XNN",
    "ڼ": "XXN",
    "ھ": "XDO",
    "ۀ": "XYH",
    "ہ": "XXG",
    "ۂ": "XGE",
    "ۃ": "XTG",
    "ی": "XYA",
    "ۍ": "XXY",
    "ې": "Y",
    "ے": "XYB",
    "ۓ": "XBE",
}
_SHADDA = "ّ"
_TEH_MARBUTA = "ة"
_TEH_MARBUTA_FINAL = "XAH"
_TATWEEL = "ـ"


class EmptyNameError(ValueError):
    """İsimden karşılaştırılabilir tek bir kelime bile çıkmadı."""


@dataclass(frozen=True, slots=True)
class TransliteratedName:
    """Bir ismin orijinal yazımı ve ICAO Latin karşılığı (05.2.1).

    `original` verilen metnin kendisidir, hiçbir normalizasyondan geçmez. `latin` aynı metnin
    Kiril ve Arap harfleri çevrilmiş hâlidir; diğer karakterler (Latin harfler, aksanlar,
    boşluk, noktalama) olduğu gibi kalır. Latin yazılmış isimde ikisi aynı metni taşır.
    """

    original: str
    latin: str


def transliterate_name(text: str, *, language: str | None = None) -> TransliteratedName:
    """İsmi ICAO tablolarıyla Latin'e çevirir; orijinal yazım sonuçta ayrıca saklanır.

    `language` belgenin ISO 639-1 dilidir (`PageAnalysis.language`); yalnız Kiril tablosunun
    dil istisnalarını seçer, tanınmayan dil varsayılan sütunu kullanır. Kiril büyük harfin
    çok harfli karşılığı komşu harfler de büyükse büyük (`ЖУКОВ → ZHUKOV`), değilse baş harfi
    büyük (`Жуков → Zhukov`) yazılır; Arap karşılıkları tablodaki gibi büyük harftir.
    """
    return TransliteratedName(original=text, latin=_transliterate(_compose(text), language))


def normalize_name(*parts: str | None, language: str | None = None) -> str:
    """İsim parçalarını tek bir eşleştirme anahtarına indirir.

    Parçalar (`given_names`, `surname`, orijinal yazım…) birlikte tek isim sayılır; `None` parça
    atlanır. Kelimeler sıralandığı için parçaların sırası sonucu değiştirmez. `language`
    harf çevirisine gider (`transliterate_name`). Hiç kelime kalmazsa `EmptyNameError`.
    """
    words = sorted(word for part in parts if part is not None for word in _words(part, language))
    if not words:
        raise EmptyNameError("İsimden eşleştirme anahtarı çıkmadı")
    return " ".join(words)


def _words(text: str, language: str | None) -> list[str]:
    # Kesme işaretleri katlamadan önce de silinir: `´` ayrışınca boşluk + işaret olur ve kelimeyi
    # böler. Katlamadan sonra ortaya çıkanlar (`＇ → '`, `ŉ → ʼn`) harf tablosuyla silinir.
    latin = _transliterate(_compose(text.translate(_DROP_APOSTROPHES)), language)
    folded = _fold(latin).translate(_LETTERS)
    chars = [
        char if char.isalnum() else " " for char in folded if unicodedata.category(char) != "Cf"
    ]
    return "".join(chars).split()


def _fold(text: str) -> str:
    # Unicode uyumluluk katlaması (D146): NFKD(casefold(NFKD(casefold(NFD(x))))). Tek casefold
    # yetmez: `İ` katlanınca `i` + birleşen nokta, `ℌ` ayrışınca büyük `H` olur.
    folded = unicodedata.normalize("NFD", text)
    for _ in range(2):
        folded = unicodedata.normalize("NFKD", folded.casefold())
    return "".join(char for char in folded if unicodedata.category(char) not in ("Mn", "Me"))


def _compose(text: str) -> str:
    # Arap sunum biçimleri (`ﻻ`, `ﻣ`) temel harflere açılır; NFC `ا + ٓ`'yı tablodaki `آ`'ya,
    # `и + ̆`'yı `й`'ye birleştirir. Uyumluluk katlaması burada yapılmaz: `´` boşluğa ayrışırdı.
    expanded = "".join(
        unicodedata.normalize("NFKC", char) if _is_presentation_form(char) else char
        for char in text
    )
    return unicodedata.normalize("NFC", expanded)


def _is_presentation_form(char: str) -> bool:
    return "ﭐ" <= char <= "﷿" or "ﹰ" <= char <= "﻾"


def _transliterate(text: str, language: str | None) -> str:
    code = language.casefold() if language is not None else None
    cyrillic = _CYRILLIC_TABLES.get(code, _CYRILLIC)
    word_initial = _UKRAINIAN_WORD_INITIAL if code == "uk" else {}
    result: list[str] = []
    doubled: str | None = None  # şeddenin ikileyeceği son Arap harfinin karşılığı
    for index, char in enumerate(text):
        if char == _SHADDA:
            if doubled:
                result.append(doubled)
            continue
        if _is_transparent(char):
            result.append(_ARABIC.get(char, char))
            continue
        if char in _ARABIC:
            doubled = _ARABIC[char]
            if char == _TEH_MARBUTA and not _is_word_char(_neighbour(text, index, 1)):
                doubled = _TEH_MARBUTA_FINAL
            result.append(doubled)
            continue
        doubled = None
        letter, marks = char, ""
        if char.upper() not in cyrillic:
            decomposed = unicodedata.normalize("NFD", char)
            letter, marks = decomposed[0], decomposed[1:]
        key = letter.upper()
        if key not in cyrillic:
            result.append(char)
            continue
        latin = cyrillic[key]
        if key in word_initial and not _is_word_char(_neighbour(text, index, -1)):
            latin = word_initial[key]
        result.append(_cased(latin, letter, text, index) + marks)
    return "".join(result)


def _cased(latin: str, letter: str, text: str, index: int) -> str:
    if letter.islower():
        return latin.lower()
    if len(latin) < 2 or not letter.isupper():
        return latin
    neighbours = (_neighbour(text, index, -1), _neighbour(text, index, 1))
    if any(neighbour is not None and neighbour.isupper() for neighbour in neighbours):
        return latin
    return latin.capitalize()


def _neighbour(text: str, index: int, step: int) -> str | None:
    # Kesme işareti, birleşen işaret, görünmez karakter ve tatvil kelimeyi bölmez; atlanır.
    index += step
    while 0 <= index < len(text):
        if not _is_transparent(text[index]):
            return text[index]
        index += step
    return None


def _is_transparent(char: str) -> bool:
    return (
        char in _APOSTROPHES or char == _TATWEEL or unicodedata.category(char) in ("Mn", "Me", "Cf")
    )


def _is_word_char(char: str | None) -> bool:
    return char is not None and char.isalnum()
