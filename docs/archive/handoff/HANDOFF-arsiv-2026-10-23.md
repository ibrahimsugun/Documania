# HANDOFF arşivi — 2026-10-23

Kaynak: HANDOFF.md (canlı dosyadan taşındı, birebir). Blok sayısı: 1.

<!-- bloklar (newest-first) -->

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
