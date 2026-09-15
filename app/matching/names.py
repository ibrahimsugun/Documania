"""İsim normalizasyonu — kişi eşleştirmesinin isim anahtarı (PRD 05.1.1, §20.2.1).

Aynı kişinin farklı yazılmış adı aynı anahtara iner; `employee_aliases.normalized_name` bu
anahtardır. Sıra:

1. Harf büyüklüğü katlanır ve aksanlar kaldırılır: Unicode uyumluluk katlaması (NFKD +
   casefold) sonrası birleşen işaretler atılır (`É → e`, `İ → i`, `ß → ss`, `ﬁ → fi`).
2. Türkçe harfler §20.2.1 eşlemesiyle (`ç→c`, `ş→s`, `ğ→g`, `ı→i`, `ö→o`, `ü→u`), ayrışmayan
   Latin harfleri yakın karşılığıyla (`ł → l`, `ø → o`, `æ → ae`) iner.
3. Noktalama sadeleşir: kesme işaretleri ve görünmez biçim karakterleri kelimeyi bölmeden
   silinir (`O'Brien → obrien`, MRZ yazımıyla aynı); harf ve rakam dışındaki her şey kelime
   ayırıcıdır (`Jean-Pierre → jean pierre`), çoklu boşluk tek boşluk olur.
4. Kelimeler alfabetik sıralanır; ad-soyad sırası farkı anahtarı değiştirmez. Tekrarlanan
   kelime korunur.

Kiril ve Arap yazımın Latin'e çevrilmesi 05.2'nindir. O adım yokken Latin dışı harfler olduğu
gibi kalır: farklı alfabelerdeki yazımlar eşleşmez, ama birbirine de karışmaz. Kelimesiz isim
(yalnız noktalama) `EmptyNameError` verir — boş anahtar hiçbir zaman eşleştirmeye girmez.
"""

from __future__ import annotations

import unicodedata

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


class EmptyNameError(ValueError):
    """İsimden karşılaştırılabilir tek bir kelime bile çıkmadı."""


def normalize_name(*parts: str | None) -> str:
    """İsim parçalarını tek bir eşleştirme anahtarına indirir.

    Parçalar (`given_names`, `surname`, tam ad…) birlikte tek isim sayılır; `None` parça
    atlanır. Kelimeler sıralandığı için parçaların sırası sonucu değiştirmez. Hiç kelime
    kalmazsa `EmptyNameError`.
    """
    words = sorted(word for part in parts if part is not None for word in _words(part))
    if not words:
        raise EmptyNameError("İsimden eşleştirme anahtarı çıkmadı")
    return " ".join(words)


def _words(text: str) -> list[str]:
    # Kesme işaretleri katlamadan önce de silinir: `´` ayrışınca boşluk + işaret olur ve kelimeyi
    # böler. Katlamadan sonra ortaya çıkanlar (`＇ → '`, `ŉ → ʼn`) harf tablosuyla silinir.
    folded = _fold(text.translate(_DROP_APOSTROPHES)).translate(_LETTERS)
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
