# Ülke verisi ve bayrak simgeleri — kaynaklar

İndirme tarihi: **2026-09-30** (PRD 10.1.6, tm 142; insan onayıyla indirildi). Dosyalar depoda
durur, çalışma zamanında ağdan bir şey çekilmez. Güncellemek için aynı kaynaklardan yeni sürüm
indirilir, bu dosya ve ilgili test güncellenir.

## Bayraklar — `app/web/static/flags/<alfa2>.svg`

- Paket: `flag-icons` **7.5.0** (Panayiotis Lipiridis), lisans **MIT** — metin `app/web/static/flags/LICENSE`.
- Adres: `https://registry.npmjs.org/flag-icons/-/flag-icons-7.5.0.tgz`
- Bütünlük (npm `dist.integrity`, indirilen dosyayla eşleşti):
  `sha512-kd+MNXviFIg5hijH766tt+3x76ele1AXlo4zDdCxIvqWZhKt4T83bOtxUOOMlTx/EcFdUMH5yvQgYlFh1EqqFg==`
- Alınan: paketin `flags/4x3/` klasöründeki **iki harfli** dosyalar (257 SVG; ISO 3166-1 alfa-2,
  küçük harf; `eu`, `un`, `xk` ve bilinmeyen için `xx` dahil). Bölge ve birlik bayrakları
  (`gb-eng`, `es-ct`, `arab`, `asean` …) ve `flags/1x1/` alınmadı.
- Dosyalar değiştirilmedi. `<script>`, olay özniteliği ve dış bağlantı taraması temiz.

## Türkçe ülke adları ve kod eşlemesi — `app/countries/data/`

- Kaynak: Unicode **CLDR 48.2.0**, lisans **Unicode License v3** — metin `app/countries/data/LICENSE-CLDR`.
- `cldr-tr-territories.json` ← `https://cdn.jsdelivr.net/npm/cldr-localenames-full@48.2.0/main/tr/territories.json`
  (Türkçe bölge adları; ör. `RU` → "Rusya", `RS` → "Sırbistan", `XK` → "Kosova").
  SHA-256 `4b9b52e756c79f8b4c81e7c2c5bd2c2ba9338f0c80f2dceeee53ba4561d872b5`.
- `cldr-codeMappings.json` ← `https://cdn.jsdelivr.net/npm/cldr-core@48.2.0/supplemental/codeMappings.json`
  (alfa-2 → `_alpha3`, `_numeric`; ör. `RU` → `RUS`).
  SHA-256 `0d1ef50b92c1140e5847d22d96faf1a9c35543b0dedf8e9a2fcb87e4c51b9ed6`.

## İngilizce ve Sırpça (Latin) ülke adları — `app/countries/data/`

İndirme tarihi: **2026-10-02** (PRD 10.10.5, tm 157; §D92 i). Türkçe adlarla aynı sürüm ve lisans:
Unicode **CLDR 48.2.0**, **Unicode License v3** (`LICENSE-CLDR`). Dosyalar değiştirilmedi.

- Paket: `cldr-localenames-full` **48.2.0** ← `https://registry.npmjs.org/cldr-localenames-full/-/cldr-localenames-full-48.2.0.tgz`
  (npm `dist.integrity`, indirilen dosyayla eşleşti:
  `sha512-4o0paYDz0UXhfhChAVFkmVl2CP0YTSEqE6WrC0fNafaSC5u5DAXphxH3SZ1Ujczarikr8DToKZfiok6EqWLdNQ==`).
  Aynı dosyalar `https://cdn.jsdelivr.net/npm/cldr-localenames-full@48.2.0/main/<yerel>/territories.json`
  adresinde de durur.
- `cldr-en-territories.json` ← paketin `main/en/territories.json` (ör. `RU` → "Russia",
  `DE` → "Germany"). SHA-256 `158c1d575308f7e46912edbeda435c8fe2ef5dad280798231f3a432e406b1807`.
- `cldr-sr-Latn-territories.json` ← paketin `main/sr-Latn/territories.json` (ör. `RU` → "Rusija",
  `DE` → "Nemačka", `CZ` → "Češka"). SHA-256 `afc92126a8b29a72a115e9ef3efeeec69ad197f717d3ea9dd8ea759cbbdf03ff`.
- Ülke kümesi Türkçe dosyadan gelir; iki dosya da 250 ülkenin her birine ad verir (test denetler).

## Bu kaynaklarda olmayanlar (tm 142 elle ekler, kaynak: ICAO Doc 9303 Part 3)

MRZ uyruk kodları ISO alfa-3'ten ayrılır: `D` → DE; `GBD`, `GBN`, `GBO`, `GBP`, `GBS` → GB;
Kosova MRZ'de `RKS` (CLDR alfa-3'ü `XKK`); ülke olmayan kodlar (`UNO`, `UNA`, `UNK`, `XXA`, `XXB`,
`XXC`, `XXX`, `XOM`, `XPO`, `XES`, `XMP`, `XCC`, `XBA`, `XIM`) bayraksız gösterilir; açıklamaları
üç dilde (`NON_COUNTRY_CODES`, `_EN`, `_SR`) elle tutulur (tm 157).
