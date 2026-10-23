# HANDOFF arşivi — 2026-10-23

Kaynak: HANDOFF.md (canlı dosyadan taşındı, birebir). Blok sayısı: 1.

<!-- bloklar (newest-first) -->

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
