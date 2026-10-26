# PLAN arşivi — 2026-10-26

Kaynak: PLAN.md (K blokları, C ve D bölümleri; canlı dosyadan taşındı, birebir).

## D. Sapmalar

- **D122 — Panel görünümü yeniden tasarlandı; arayüz standardı ve denetimi (10.1.1, 10.1.7; insan isteği 2026-10-22).** İnsan isteği: "Sistemin template ve görünümünü beğenmiyorum… SaaS kalitesinde olsun… Template kalitesini bir standarda bağla, sisteme bundan sonra yapılacak değişimleri AI algılayabilsin ve kaliteyi bozmadan sistem genişlemeleri yapabilelim." **(a) Kabuk:** `base.html` sol gezinme sütunu (`header.topbar`: marka, menü, erişim logu, oturum kartı), içerik sütununun üst şeridi (`.page-tools`: çalışan araması `/employees?q=`, dil seçici, tema düğmesi) ve `main.content`; 64rem altında gezinme üst şeride iner. Testlerin sabitlediği işaretler (menü bağlantısının çıplak biçimi, `tool-link`, `session`/`Çıkış`, `page-tools`, bildirim alanı) aynen kaldı; menü sırası PRD 10.1.1, simgeler CSS'ten (`.menu a[href=…]` maskesi). **(b) Stil:** `panel.css` baştan yazıldı — tasarım değişkenleri, kabuk, bileşenler (düğme hiyerarşisi, form ızgaraları, bırakma alanı, tablo kartı, bölüm kartı, iki aşamalı onay kartı, zaman çizelgesi, rozet, sekme, bildirim); `theme.css` yalnız palet (açık `:root`, koyu `html[data-theme=dark]`). Şablonların işaretlemesi değişmedi (yalnız `base.html`); i18n kataloğuna yeni msgid girmedi. 10.1.7'nin "degrade zemin / cam üst çubuk" tarifi yerine sade SaaS yüzeyi seçildi; kabul kriterinin ölçülen maddeleri (tek tema dosyası, açık/koyu, yanıp sönme yok, hareket azaltma, giriş sayfası zemini) korunur. **(c) Standart:** `docs/ARAYUZ-STANDARDI.md` — katmanlar, sayfa anatomisi, bileşen sözlüğü, anlam sınıfı (hook) kaydı, kurallar, kontrol listesi. `tests/web/test_ui_standard.py` ölçülebilir maddeleri denetler: şablondaki her sınıf ya `panel.css`'te tanımlı ya §4'te kayıtlı; `style=`, satır içi `<script>`, dış kaynak yok; tam sayfada tek `h1` (dallar hariç), parçada yok; her `button` `type` taşır, her `table` ad sınıfı taşır; `panel.css`'te `:root` dışında altı haneli renk yok; her `var(--x)` tanımlı; koyu tema açık temanın her değişkenini ezer; her menü girdisinin simgesi var; kabuk işaretleri. Standart `CLAUDE.md`'ye bağlandı: şablon/stil değiştiren her pencere önce onu okur. **(d) Kapsam dışı:** yönlendiriciler, veri modeli, i18n kataloğu, betikler (`toast.js`, `theme.js`, `upload.js`, `country-select.js`) değişmedi.



## K. Kanıt Geçmişi (arşiv)

#### K10.1 — 10.1.1, 10.1.2, 10.1.3, 10.1.4, 10.1.5, 10.1.6 · Panel iskeleti, giriş, kullanıcı yönetimi ve ülke verisi
- ✅ Panel görünümü yeniden tasarlandı (§D122): kabuk `app/web/templates/base.html`, stil `app/web/static/panel.css` + `theme.css`, standart `docs/ARAYUZ-STANDARDI.md` · test `tests/web/test_ui_standard.py` (21) · tests/web 1538 geçti (3 kırmızı: 2 D58 arşiv kırığı bu değişiklikten önce vardı, 1 düzeltildi) · insan isteği 2026-10-22

