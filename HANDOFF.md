# HANDOFF — pencereler arası köprü

Her görev penceresi kapanırken buraya bir blok ekler. Bloklar **newest-first** sıralıdır:
en yeni blok `## Task log (newest-first)` başlığının hemen altındadır.

**Bu dosyayı baştan sona okuma.** Sana gereken en üstteki birkaç bloktur: `head -60 HANDOFF.md`.
Eski bir işi arıyorsan hedefli ara: `grep -n 'tm <id>' HANDOFF.md | head -5`.

Eski kayıtlar: `docs/archive/handoff/` (`grep -rn 'tm <id>' docs/archive/handoff`). Bu dosyada yalnız son 5 görev + açık görevler durur (CONVENTIONS §3).

Blok biçimi `CONVENTIONS.md` §3'te tanımlıdır:

```markdown
## <tm-id> — <başlık> — <done|blocked> — <YYYY-MM-DD>
- Yapıldı: <tek cümle>
- Doğrulama: <hangi kapılar yeşil, kaç test>
- Varsayımlar: <yoksa "yok">
- Sonraki pencereye not: <bir sonraki işin bilmesi gereken tek şey>
```

## Task log (newest-first)

## 184 — 15.1-c Alan haritası önizleme ve onay — done — 2026-10-23
- Yapıldı: `app/output_templates/approve.py` (`approve_map`: son sürüme onay, atama doğrulama, değişen atama `store_map` ile yeni sürüm, `ready`, `TEMPLATE_MAP_APPROVED`; `approved_map`), şablon sayfasında SVG kutulu önizleme + atama tablosu (`select`/"Boş bırak", imza/kaşe seçimsiz), `POST /output-templates/{id}/maps/{version}/approve` düz form, Kullanıcı'ya yalnız onaylı harita salt okunur; `panel.css` + ARAYUZ-STANDARDI §3/§4, dört bildirim, üç dil.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0032, göç yok), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7122 geçti, 6 atlandı, kapsam %98,83 — 2 kırmızı (`…plan_d58_verbatim`, D58 bloğu PLAN'da yok) tm 180–183'teki gibi bu görevle ilgisiz.
- Varsayımlar: §D123 (m)'ye yazıldı — onay yalnız son sürüme (eski sürüm 409), atama değişmezse yerinde onay, değişirse yeni sürüm (`model` kutuları önerenin), zaten onaylıysa yazma yok; üretim onaylı en yüksek sürümü kullanır; kutular `style=` yasağı yüzünden SVG.
- Sonraki pencereye not: tm 185 haritayı `app.output_templates.approve.approved_map(template)` ile alır (`json["fields"]`, `source` = `unassigned` boş kalır); `generated_documents.map_id` o satırın `id`'si. D58 testleri için ayrı küçük görev hâlâ gerekli.

## 183 — 15.1-b Şablon incelemesi (alan haritası) — done — 2026-10-23
- Yapıldı: `TemplateFieldMap` §8.7 şeması (`app/ai/schemas.py`), talimat `template_map.md`, `examine_template` (Anthropic/OpenAI/kayıtlı yanıt), göç 0032 (`examine_requested_at` + boş-zaman sahiplenme alanları), `app/output_templates/examine.py` (kuyruk, `TemplateExaminationJob`, harita sürümü + `map_hash`, `examine_error` kodu, `TEMPLATE_EXAMINED`), yüklemede kuyruğa alma, "Yeniden incele" (`POST …/examine`), listede/sayfada sebep, üç dil.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0032), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7115 geçti, 6 atlandı, kapsam %98,84 — 2 kırmızı (`…plan_d58_verbatim`, D58 bloğu PLAN'da yok) önceki görevlerdeki gibi bu görevle ilgisiz.
- Varsayımlar: §D123 (l)'ye yazıldı — yanıt yalnız `fields`+`notes`, `text`/`date`'te `source`/`font_size`/`max_chars` zorunlu, `examine_error` kod, şema hatası yeniden sorulmaz, sağlayıcı ayarı panelde denetlenir, yeniden inceleme durumu değiştirmez, 0032 öncesi şablonlar kendiliğinden kuyruğa girmez.
- Sonraki pencereye not: tm 184 son sürümü `template.maps[-1]` (`json["fields"]`) üzerinden önizler; onay `approved_at`/`approved_by` yazar ve `map_hash`'i yeniden hesaplamaz (sürüm değişmezse aynıdır), düzenleme `store_map` ile yeni sürüm açmalı. Yeni POST yolları `REVIEWED_MUTATING_ROUTES`'a eklenmeli; web testleri `provider_available`'ı override eder.

## 182 — 15.1-a Hazır şablon deposu — done — 2026-10-23
- Yapıldı: göç 0031 (`output_templates`, boş `output_template_maps`, `generated_documents`; `access_log` `template_id`/`generated_document_id` + CHECK), `app/output_templates/` (yükleme PDF/JPEG/PNG img2pdf kayıpsız, Word/Excel 422, SHA-256 ve ad tekrarı 409, arşiv/geri al, `TEMPLATE_UPLOADED/ARCHIVED/RESTORED`), `_sablonlar/<id>/sablon.pdf` + `pages/`, `Uretilen/` çalışan klasöründe; `/output-templates` liste/süzgeç/şablon sayfası, orijinali aç/indir erişim kaydıyla, menü "Hazır Şablonlar" simgeli, üç dil.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0031), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7085 geçti, 6 atlandı, kapsam %98,86 — 2 kırmızı (`…plan_d58_verbatim`) HEAD'de de kırmızı (D58 bloğu PLAN'da yok), bu görevle ilgisiz.
- Varsayımlar: §D123 (k)'ye yazıldı — erişim kaydı ayrı sütunlarla (`action` genişlemedi), önizleme görüntüsü kayda girmez, `sha256` saklanan PDF'in, "Etkin" süzgeci = `draft` + `ready`, `_sablonlar/` `static_dirs`'e girmez (yedek kapsamında).
- Sonraki pencereye not: tm 183 haritayı `output_template_maps`'e yazar; liste "alan sayısı" son sürümün `text`/`date` alanlarını sayar (`field_count`), geri alınan şablon onaylı harita varsa `ready`'ye döner. Yeni POST yolları `tests/web/test_access_log.py` `REVIEWED_MUTATING_ROUTES`'a eklenmeli. D58 testleri için ayrı küçük görev hâlâ gerekli.

## 181 — 15.3-b Ek alanların belgeden otomatik dolumu — done — 2026-10-23
- Yapıldı: `PagePerson` beş isteğe bağlı alan (eksikse `null`; sağlayıcı şeması hepsini `required` ister), `page_analysis.md` yalnız açıkça yazılı değer; `Mrz.personal_number` (TD1 satır 1 16–30, bileşik + belge no hanesi tutarsa; ülke = veren devlet) ve `apply_mrz_priority` önceliği/notu; `PersonKey` ek alanlar → 05.7.3 dolumu (ülke numarayla), 05.5.4 doldurmaz (test), `fill-fields` yeni alanlar; kayıtlı yanıtlar + `gen.py` (`DETAIL_PAGE_FIELDS`, oturma izni MRZ'sinde numara); PRD §20.1.3 eki; uçtan uca `tests/test_detail_fields_upload.py`.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0030, göç yok), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7073 geçti, 6 atlandı, kapsam %99,00 — 2 kırmızı (`test_training_decisions.py`/`test_training_map.py` `…plan_d58_verbatim`) temiz HEAD'de de kırmızı (tm 180 notundaki D58 sorunu), bu görevle ilgisiz.
- Varsayımlar: §D123 (j)'ye yazıldı — TD2/TD3 isteğe bağlı verisi kişisel numara sayılmaz; eski saklı analizlerden yalnız MRZ numarası dolar (analiz yeniden istenmez, K9); numara `same`/`conflict` iken kayıtlı ülke değişmez. `tests/recorded.py` değişmedi (yeni kayıtlı sistem metni yok).
- Sonraki pencereye not: tm 185 profil değerlerini `employees`'ten okur; kişisel numaranın ülkesi `personal_number_country` (MRZ'de veren devlet). D58 testleri için ayrı küçük görev hâlâ gerekli.

## 180 — 15.3-a Ek profil alanları (anne/baba adı, doğum yeri, kişisel numara + ülke) — done — 2026-10-23
- Yapıldı: göç 0030 (`employees` beş sütun, gözlem CHECK'i), `ProfileField` dört üye; profil kartı dört alan + pasaport numarası (`app.matching.records.passport_number`), düzenleme formu (`EMPLOYEE_FIELDS`, elle kaynağı, olaylarda yalnız alan adları), `profil.md`, arama (`app/matching/numbers.py`, 15.3.3), birleştirme (numara ülkesiyle), kalıcı silme (boşaltma + olay temizliği), en/sr çeviriler; S25 yeni alanlarla.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0030), `import app.main`, `python -m app.i18n check` exit 0; tam paralel kapı 7052 geçti, kapsam %99,01 — 2 kırmızı (`test_training_decisions.py::…plan_d58_verbatim`, `test_training_map.py::…plan_d58_verbatim`) temiz HEAD dd5b4ef'te de kırmızı (D58 bloğu PLAN'dan arşive taşınmış), bu görevle ilgisiz.
- Varsayımlar: §D123 (i)'ye yazıldı — ülke ayrı gözlem alanı değil (`personal_number` gözlemi), ülke numarasız girilmez; pasaport numarası `Passport` etiketli türlerin en son kaydedilen etkin numarası (`id` en büyük); ek alanlar onay bekleyen profil formunda (10.7.3) yok.
- Sonraki pencereye not: tm 181 (15.3.2) belgeden dolumu `app/matching/fields.py`'ye ekler — `document_field_values` artık `values.get` okuyor, `_same` kişisel numarayı `same_personal_number` ile karşılaştırıyor; ülke gözlemi yine `personal_number` adıyla yazılmalı. D58 testleri için ayrı küçük görev gerekli (testler `docs/archive/plan-kanit/`'ten okusun).

## 180, 181, 182, 183, 184, 185, 186 — FR-MOD-15 Hazır şablonlar, çıktı hazırlama ve ek profil alanları açıldı — pending — 2026-10-23 (interaktif oturum: insan isteği)
- Yapıldı: İnsan isteği (2026-10-23, PLAN §D123'te birebir) PRD FR-MOD-15 (15.1.1–15.3.3, 10 satır), §3 R3/R12 notları, §4 sözlük, §5.2 kapsam, 10.1.1 menü sırası, §8.1 üç tablo + `employees` sütunları, §8.2 `Uretilen/` ve `_sablonlar/`, §8.3 olaylar, §8.4 `person` alanları, §8.7 alan haritası şeması, §9 S29, §10 kapsam dışı; MASTER-PROMPT K11/K16/K17 istisnası (insan kararı); PLAN §0 (Faz 1: 82 ✅ · 10 ⬜, 41/49 Must, Kapanış AÇIK), §2 matris, §4.4 tablo, §D123 sözleşme, §G 8 satır; tasks.json tm 180–186 (15.3-a/b, 15.1-a/b/c, 15.2-a/b), bağımlılıklar ve etiketler. Kod değişmedi.
- Doğrulama: PRD §20.6 tablosu değişmedi (`tests/web/test_confirm.py` okur) — test yeşil; `tests/web/test_ui_standard.py`, `tests/i18n` yeşil; sayım komutları (CONVENTIONS §1.3) §0 ile eşit; `node scripts/arsiv-dondur.mjs` dry-run sonucu HANDOFF'un altında.
- Varsayımlar: (1) R3/R12/K11/K17 daraltması insan tarafından 2026-10-23'te açıkça onaylandı (§D123 a, "Onay" cümlesi); veto ihtimali kapandı. (2) Word/Excel şablonu, kutu çizme, toplu üretim, e-imza kapsam dışı bırakıldı (ayrı insan isteği). (3) Pasaport numarası ayrı sütun değil, `employee_identifiers`'tan gösterim. (4) Onay ve üretim tek adımlı (§D61 geri alınabilirlik), §20.6'ya satır yok. (5) Sıra: önce tm 180 (alanlar) ve tm 182 (depo) paralel açılabilir; 181 → 180; 183 → 182; 184 → 183; 185 → 184+180; 186 → 185; (tm 187 kapanış denetimi insan isteğiyle silindi, 2026-10-23; Faz 1 kapanışı yeniden açılacak görevle yapılır).
- Sonraki pencereye not: `task-master next` tm 180 ya da 182'yi verir; `[OPUS-XHIGH]`. Her görev `docs/ARAYUZ-STANDARDI.md`'ye uyar ve `test_ui_standard`'ı yeşil tutar. D58 testleri (tm yok) hâlâ `PLAN.md`'de olmayan D58 bloğunu arıyor — ayrı küçük görev önerisi: testler `docs/archive/plan-kanit/`'ten okusun.
