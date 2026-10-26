# ARAYÜZ STANDARDI — Documania paneli

> Bu dosya panelin **görünüm ve şablon sözleşmesidir**. Şablon (`app/web/templates/*.html`),
> stil (`app/web/static/panel.css`, `theme.css`) ya da panel betiği değiştiren her pencere önce
> bunu okur. Sözleşmenin ölçülebilir maddelerini `tests/web/test_ui_standard.py` denetler:
> standarda uymayan değişiklik DoD kapısında kırmızıdır (CONVENTIONS §1). Ölçülemeyen maddeler
> gözden geçirme ölçütüdür. Sürüm: 2026-10-26 (§D122; erişilebilirlik 10.1.12, §D126).

## 1. Katmanlar — kim neyi yapar

| Katman | Dosya | Sorumluluk | Yasak |
|---|---|---|---|
| Kabuk | `templates/base.html` | Sol gezinme (`header.topbar`), araç şeridi (`.page-tools`), bildirim alanı (`.toasts`), içerik (`main.content`) | Sayfaya özel içerik; satır içi `<script>` |
| Yerleşim + bileşenler | `static/panel.css` | Tasarım değişkenleri (boşluk, köşe, yazı, durum renkleri), kabuk yerleşimi, bütün bileşenler | Renk paleti (ink/surface/accent) — o theme.css'tedir |
| Palet | `static/theme.css` | Açık (`:root`) ve koyu (`html[data-theme="dark"]`) renkler, gölgeler, odak halkası | Yerleşim, bileşen kuralı |
| Sayfa | `templates/<sayfa>.html` | Yalnız anlam taşıyan HTML: başlık, açıklama, tablo, form, bölüm | Stil kararı (`style=`), yeni CSS dosyası, çevrilmemiş metin |
| Betik | `static/*.js` | HTMX dışı davranış (bildirim, tema, bırakma alanı, ülke seçici) | Görünen dizge (metin sunucudan `data-*` ile gelir) |

Tek stil dosyası kuralı (MASTER-PROMPT §4) korunur: yeni `.css` dosyası açılmaz, dış CSS/JS
yüklenmez (CDN yok), satır içi `style=` yazılmaz.

## 2. Sayfa anatomisi — sıra sabittir

Tam sayfa şablonu (`{% extends "base.html" %}`) `{% block content %}` içinde şu sırayı izler;
olmayan basamak atlanır, sıra değişmez:

1. `p.back` — alt sayfada üst sayfaya dönüş (`← <Üst sayfa>`).
2. `h1` — sayfanın adı, **tek**. Menü sayfasında menü etiketiyle birebir (`<h1>Çalışanlar</h1>`; test).
3. `p.profile-meta` — kimlik satırı (E numarası · durum · bağlantılar) yalnız kayıt sayfasında.
4. `p.lede` — bir-iki cümle: sayfa ne işe yarar, kullanıcı ne yapar. Liste sayfalarında zorunlu.
5. Kalıcı durum uyarıları: `div/p.notice` (sarı), `p.error` (kırmızı), `section.context-warning` (büyük kırmızı, 10.5.5).
6. Araç çubuğu: `nav.tabs` (görünümler) → `p.hint-panel` (sekmenin tek cümlelik ipucu) → `nav.states` (durum süzgeci) → `form.search` (arama/süzgeç) → `p > a.button-link` (sayfa eylemleri).
7. İçerik: `p.count` + `table`, kart ızgarası (`.package-cards`, `.thumbs`) ya da `section` kartları (`h2` ile başlar).
8. `nav.pager` — sayfalama.

HTMX parçası (`extends` etmeyen şablon) `h1` taşımaz; hedefine yazılan parçanın kökü tek öğedir.

## 3. Bileşen sözlüğü — var olanı kullan, yenisini kaydet

Aşağıdaki sınıflar `panel.css`'te tanımlıdır; yeni sayfa önce bunlarla kurulur. Yeni bileşen
gerekirse: (1) bu tabloya satır, (2) `panel.css`'te kural, (3) test. Sınıf adı kebab-case ve
anlam bildirir (`.employee-filter`), görünüm bildirmez (`.red`, `.mt-2` yok).

| Amaç | Sınıf | Not |
|---|---|---|
| Sayfa başlığı altı | `.lede`, `.hint`, `.hint-panel`, `.count`, `.reason`, `.placeholder` | `.placeholder` boş durumdur: bir cümle + ilk adıma bağlantı (10.11.2) |
| Düğme | `button`, `.button-link`, `.button-small`, `.button-secondary`, `.link-button`, `button.danger` | Birincil düğme formun `type="submit"`'idir ve sayfada tek asıl eylem vardır; kalıcı silme `danger` |
| Form | `.type-form` (etiket sütunu + `.field`), `.profile-edit`, `.search`, `.inline-form`, `form.inline`, `.form-actions`, `.choice`, `.choices`, `.field-error` | Çok satırlı alan yok (10.9.1); `label for` zorunlu |
| Yükleme | `.upload-form`, `.dropzone`, `.file-list`, `.progress`, `.steps`/`.step` | Bırakma alanı `label.dropzone` + gizli olmayan `input[type=file]` |
| İki aşamalı onay | `form.confirm` + `p.confirm-text` + `button[type=submit]` + `a` (Vazgeç) | Metin §20.6'dan birebir; silme adımı `.document-delete-step` / `.employee-delete-step` |
| Uyarı | `.notice`, `.error`, `.notice-success`, `.context-warning`, `.inactive-notice`, `.merged-notice`, `.deleted-notice` | `.notice`/`.error` kalıcı durumdur; işlem sonucu bildirimdir (10.11.1), sayfaya yazılmaz |
| Rozet | `.badge`, `.badge-neutral`, `.badge-missing`, `.badge.name-only`, `.status-badge` + `.status-active/.status-passive/.status-archived/.status-open`, `.counter` | Renk tek taşıyıcı değildir: metin kalır |
| Durum | `p.status.status-<durum>`, `td.status-<durum>`, `.check-ok/.check-fail`, `.proposal-*`, `.manual-check` | Parti/çalıştırma durumları |
| Sekme / süzgeç | `nav.tabs a(.active)`, `nav.states a(.active)`, `nav.pager` | `aria-current` seçili öğede |
| Tablo | `table.<ad>` + `th.num/td.num`, `.cell-nowrap`, `.cell-break`, `.doc-actions`, `.record-actions`, `.reason-text` | Her tablo bir ad sınıfı taşır (test ve genişlik kuralları için) |
| Kart ve bölüm | `section` (kart), `article.file`, `.thumbs/.thumb`, `.timeline/.event`, `dl.meta`, `dl.record-summary`, `.profile-card`, `.package-card` | `section` doğrudan `main.content` altında karttır, `h2` ile başlar |
| Alan haritası önizlemesi | `.map-layout` > `figure.map-page` (`img` + `svg.map-boxes` > `a.map-box` + `.map-box-unassigned/.map-box-locked`) + `table.map-fields` | Kutular SVG'dir (`viewBox` = sayfa görüntüsünün ölçüsü), `style=` yok; kutu bağlantısı tablodaki satırına gider (`#map-row-<id>`), odakta kenar kalınlaşır; her `select`'in `label for`'u satırdadır (15.1.3) |
| Kabuk | `.skip-link`, `.content-start`, `.topbar`, `.brand`, `.menu`, `.tool-link`, `.session`, `.page-tools`, `.global-search`, `.text-toggle`, `.theme-toggle`, `.language-selector`, `.toasts/.toast` | Yalnız `base.html` |

## 4. Anlam sınıfları (hook) — stil taşımaz, kayıtlıdır

Bazı sınıflar görünüm için değil, **bölümü, formu ya da tabloyu adlandırmak** için vardır:
testler, HTMX hedefleri ve betikler onları bulur. Şablonda kullanılan her sınıf ya §3'teki
gibi `panel.css`'te tanımlıdır ya da **bu listede** kayıtlıdır; ikisinde de olmayan sınıf testte
kırmızıdır. Yeni hook eklerken buraya yaz (alfabetik):

`accepted-photos`, `access-log`, `action-done`, `actions`, `ai-provider`, `ai-settings`, `archive-selection`, `archive-summary`,
`archive-types`, `archived-types`, `brand-name`, `candidates`, `close-item`, `close-summary`,
`current`, `document-archive-step`, `document-groups`, `document-unarchive`, `employee-fields-step`,
`employee-merge`, `employee-merge-step`, `employee-status-step`, `employees`, `entry-summary`,
`examples`, `files`, `generate-output`, `generated-description`, `generated-documents`, `group-archive`, `group-items`, `group-items-table`,
`group-meta`, `item-title`, `items`, `login-log`, `login-summary`, `map-preview`, `map-skip-reasons`, `map-skip-rows`, `map-skipped`,
`map-start`, `map-upload`, `merge-candidates`, `merge-search`, `move-example`, `output-templates`,
`output-archive`, `output-restore`, `outputs`, `prefill`, `prefill-conflict`, `prefill-state`, `prefill-suggested`, `prefill-unfilled`,
`profile-documents`, `profile-outputs`, `profile-packages`, `profile-record`, `profile-record-step`,
`profile-records`, `profile-template-list`, `profile-templates`, `profile-upload`, `queue`, `queue-close-step`, `queue-items`, `reader-hint`, `reanalysis-results`,
`reanalysis-targets`, `record-aliases`, `record-contacts`, `record-numbers`, `record-remove`,
`record-warning`, `records`, `rejected-candidates`, `select-assignee`, `select-target`, `source`,
`telegram-bot-missing`, `telegram-delete`, `telegram-delete-help`, `telegram-help`,
`telegram-link-help`, `telegram-own-help`, `template-archive`, `template-details`, `template-map`,
`template-map-approve`, `template-pages`, `template-upload`, `training-form`, `training-results`, `training-runs`,
`unregistered`, `user-role`.

## 5. Kurallar

**Metin.** Görünen her dizge `_()` / `{% trans %}` ile işaretlidir ve üç dilde çevrilidir
(`python -m app.i18n check`); veri (ad, dosya, tür adı, kayıtlı gerekçe) çevrilmez ve
`translate="no"` taşır (10.10.3). Betikte görünen dizge yoktur. Sayı ve tarih biçimi dilden
bağımsızdır.

**Renk.** `panel.css`'te renk yalnız `var(--…)` ile yazılır; altı haneli hex yalnız `:root`
bloğunda (durum renkleri) durur. Palet `theme.css`'tedir, koyu temada her değişkenin karşılığı
vardır. Durum rozeti metninin zemine kontrastı ≥ 4,5:1 (test).

**Hiyerarşi.** Sayfada tek `h1`; bölümler `h2`, alt bölümler `h3`. Birincil düğme sayfanın
asıl eylemidir (yükle, kaydet, onayla); tablo içi işlemler ikincil (`.inline-form` / bağlantı).
Kalıcı silme kırmızıdır ve yalnız iki aşamalı onayın son adımındadır.

**Yol gösterme.** Boş durum (`.placeholder`) ilk adıma bağlantı verir; bekleyen iş ipucu taşır
(10.11.2); salt okunur Kullanıcı yazma bağlantısı görmez (`user.can_write`).

**Erişilebilirlik.** Her `input`'un `label for`'u, her simge düğmesinin `aria-label`'ı, her
bölümün `aria-labelledby` ya da görünür başlığı vardır; seçili sekme `aria-current`; odak halkası
(`--focus` gölgesi + `--focus-ring` kalın düz halka) kapatılmaz; `prefers-reduced-motion`'da animasyon yoktur.

**Yaşlı ve az gören kullanıcı (PRD 10.1.12).** Gövde yazısı 16 px (`--text-base: 1rem`), en küçük
metin 13 px (`--text-xs`); küçük büyük harfli (`uppercase`) etiket kullanılmaz. Her düğme, alan,
sekme ve sayfalama bağlantısı en az 40 px yüksektir (`--target`; satır içi küçük form 36 px,
`--target-sm`); onay kutusu ve radyo 20 px. Metin içindeki bağlantı altı çizilidir (renk tek
taşıyıcı değildir). Soluk metin (`--muted-ink`) zeminine ≥ 5:1. Araç şeridindeki "Büyük yazı"
düğmesi (`.text-toggle`, `data-text-toggle`) `html[data-text="large"]` ile kökü %120 büyütür;
seçim tarayıcıda hatırlanır ve ilk boyamadan önce uygulanır. Kabuğun ilk odağı "İçeriğe atla"
bağlantısıdır (`.skip-link` → `#content-start`). `prefers-contrast: more`'da cam zemin ve ince
çizgi yerine düz zemin ve kalın kenar vardır. Tablo başlığı normal yazıdır, gövde zebra satırlıdır.
Denetim: `tests/web/test_theme.py` (10.1.12 bölümü).

**Duyarlılık.** Kabuk 64rem altında tek sütuna iner (gezinme üstte, yatay kayar); tablo kendi
içinde yatay kayar; form ızgaraları tek sütun olur. Yeni bileşen bu kırılımda bozulmaz.

**Dokunulmazlar.** Testlerin sabitlediği işaretler değişmez: `<header class="topbar">`,
`<nav class="menu" aria-label=…>` içindeki çıplak `<a href="/…">Etiket</a>` (etkin: `class="active"
aria-current="page"`), `<a class="tool-link" href="/access-log">` (yalnız root; ardından yine yalnız root için `href="/ai-settings"`), `<form class="session" …
action="/logout">` + `<button type="submit">Çıkış</button>`, `<div class="page-tools">` içindeki
`class="text-toggle" data-text-toggle aria-pressed="false"` ve `class="theme-toggle" data-theme-toggle aria-pressed="false"`, `<main class="content">` + `<span id="content-start" class="content-start" tabindex="-1">`, bildirim
`<div class="toast toast-<tür>" role=… data-kind=…><span class="toast-icon"…></span><p class="toast-text">`,
`.catalog-types th:nth-child(n) { width: …%; }` on sütun = %100, `.status-active/.status-passive`
rengi `var(--success|--danger)` + `-soft`. Menü sırası PRD 10.1.1'dir; simge `panel.css`'te
`.menu a[href="/yol"]` kuralıyla verilir — yeni menü girdisi simgesiz kalamaz (test).

## 6. Yeni sayfa / değişiklik kontrol listesi

- [ ] §2 sırası; tek `h1`; liste sayfasında `.lede`; boş durum bağlantılı.
- [ ] Yalnız §3 bileşenleri; yeni sınıf §3 tablosuna + `panel.css`'e ya da §4 listesine.
- [ ] `style=` yok, satır içi `<script>` yok, yeni `.css` yok, dış kaynak yok.
- [ ] Metinler `_()`; `python -m app.i18n extract|update|compile|check` yeşil.
- [ ] Yazma düğmeleri `user.can_write` ile; iki aşamalı onay §20.6 metniyle.
- [ ] Açık ve koyu temada bakıldı; 64rem altında bakıldı.
- [ ] `pytest tests/web/test_ui_standard.py` ve ilgili sayfa testleri yeşil.
