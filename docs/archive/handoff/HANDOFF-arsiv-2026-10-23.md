# HANDOFF arşivi — 2026-10-23

Kaynak: HANDOFF.md (canlı dosyadan taşındı, birebir). Blok sayısı: 1.

<!-- bloklar (newest-first) -->

## 180 — 15.3-a Ek profil alanları (anne/baba adı, doğum yeri, kişisel numara + ülke) — done — 2026-10-23
- Yapıldı: göç 0030 (`employees` beş sütun, gözlem CHECK'i), `ProfileField` dört üye; profil kartı dört alan + pasaport numarası (`app.matching.records.passport_number`), düzenleme formu (`EMPLOYEE_FIELDS`, elle kaynağı, olaylarda yalnız alan adları), `profil.md`, arama (`app/matching/numbers.py`, 15.3.3), birleştirme (numara ülkesiyle), kalıcı silme (boşaltma + olay temizliği), en/sr çeviriler; S25 yeni alanlarla.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0030), `import app.main`, `python -m app.i18n check` exit 0; tam paralel kapı 7052 geçti, kapsam %99,01 — 2 kırmızı (`test_training_decisions.py::…plan_d58_verbatim`, `test_training_map.py::…plan_d58_verbatim`) temiz HEAD dd5b4ef'te de kırmızı (D58 bloğu PLAN'dan arşive taşınmış), bu görevle ilgisiz.
- Varsayımlar: §D123 (i)'ye yazıldı — ülke ayrı gözlem alanı değil (`personal_number` gözlemi), ülke numarasız girilmez; pasaport numarası `Passport` etiketli türlerin en son kaydedilen etkin numarası (`id` en büyük); ek alanlar onay bekleyen profil formunda (10.7.3) yok.
- Sonraki pencereye not: tm 181 (15.3.2) belgeden dolumu `app/matching/fields.py`'ye ekler — `document_field_values` artık `values.get` okuyor, `_same` kişisel numarayı `same_personal_number` ile karşılaştırıyor; ülke gözlemi yine `personal_number` adıyla yazılmalı. D58 testleri için ayrı küçük görev gerekli (testler `docs/archive/plan-kanit/`'ten okusun).
