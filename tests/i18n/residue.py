"""Türkçe kalıntı taraması — test yardımcısı (PRD 10.10.3; PLAN.md §D92 g).

İngilizce (ya da Sırpça) çizilmiş bir sayfanın görünen metninde Türkçe arayüz metni kalmış mı
diye bakar: Türkçeye özgü harfler (`çğıİöşüÇĞÖŞÜ`) ve Türkçe harf taşımadığı için harf
denetiminden kaçan, sözlükteki Türkçe sözcükler.

Görünen metin: `<script>` ve `<style>` dışındaki metin düğümleri (`<title>` dahil), `title`, `alt`,
`placeholder`, `aria-label` öznitelikleri ve düğme değerleri. Veri taşıyan öğeler —
`translate="no"`, alt ağacıyla birlikte — taranmaz: kullanıcı adı, çalışan adı, belge türü adı
çevrilmez (§D92 f). Testlerin sentetik verisi bu harfleri taşımaz; taşıyan veri `translate="no"`
öğesinde durur.

Her çeviri görevi kendi sayfalarını kendi testinde bu yardımcıdan geçirir; 10.10-d bütün panel
yollarını dolaşır.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

TURKISH_LETTERS = frozenset("çğıİöşüÇĞÖŞÜ")
# Türkçe harf taşımayan, İngilizcede sözcük olmayan Türkçe arayüz sözcükleri (tam sözcük, büyük
# küçük harf duyarsız). Sırpçada da sözcük olanlar `SERBIAN_WORDS`'te: Sırpça sayfada aranmaz.
TURKISH_WORDS = frozenset(
    {
        "aday",
        "arama",
        "bekleyen",
        "belge",
        "belgeler",
        "belgesi",
        "belgeyi",
        "bilgi",
        "devam",
        "dosya",
        "dosyalar",
        "durum",
        "ekle",
        "evet",
        "geri",
        "hata",
        "hepsi",
        "ile",
        "iptal",
        "kapat",
        "kaydet",
        "kaynak",
        "kuyruk",
        "kuyruklar",
        "neden",
        "numara",
        "onay",
        "onayla",
        "oturum",
        "parola",
        "parti",
        "partiler",
        "sahip",
        "sayfa",
        "sonra",
        "soyad",
        "sunucu",
        "tamam",
        "tarih",
        "uyruk",
        "veya",
        "yeni",
        "yeniden",
        "yok",
    }
)
SERBIAN_WORDS = frozenset({"parola"})
VISIBLE_ATTRIBUTES = frozenset({"title", "alt", "placeholder", "aria-label"})
BUTTON_INPUT_TYPES = frozenset({"submit", "button", "reset"})
HIDDEN_ELEMENTS = frozenset({"script", "style"})
VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)
_WORD = re.compile(r"[^\W\d_]+")


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self._skipped_tag: str | None = None
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skipped_tag is not None:
            self._skip_depth += tag == self._skipped_tag
            return
        attributes = {name: value or "" for name, value in attrs}
        if tag in HIDDEN_ELEMENTS or attributes.get("translate", "").lower() == "no":
            if tag not in VOID_ELEMENTS:
                self._skipped_tag, self._skip_depth = tag, 1
            return
        self.chunks += [value for name, value in attributes.items() if name in VISIBLE_ATTRIBUTES]
        if tag == "input" and attributes.get("type", "").lower() in BUTTON_INPUT_TYPES:
            self.chunks.append(attributes.get("value", ""))

    def handle_endtag(self, tag: str) -> None:
        if self._skipped_tag == tag:
            self._skip_depth -= 1
            if self._skip_depth == 0:
                self._skipped_tag = None

    def handle_data(self, data: str) -> None:
        if self._skipped_tag is None:
            self.chunks.append(data)


def visible_text(html: str) -> list[str]:
    """Sayfanın görünen metin parçaları (boşluklar sadeleşmiş, boş parçalar atılmış)."""
    parser = _VisibleText()
    parser.feed(html)
    parser.close()
    return [text for text in (" ".join(chunk.split()) for chunk in parser.chunks) if text]


def turkish_residue(html: str, language: str = "en") -> list[str]:
    """`language` dilinde çizilmiş sayfada Türkçe kalmış görünen metin parçaları."""
    words = TURKISH_WORDS - SERBIAN_WORDS if language == "sr" else TURKISH_WORDS
    return [
        text
        for text in visible_text(html)
        if TURKISH_LETTERS & set(text) or any(word.lower() in words for word in _WORD.findall(text))
    ]


def assert_no_turkish(html: str, language: str = "en") -> None:
    residue = turkish_residue(html, language)
    assert not residue, f"{language} sayfasında Türkçe metin kaldı: {residue}"
