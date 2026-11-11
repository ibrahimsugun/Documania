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

## 201 — 11.9-k Önizlemeyle yaşayan örnek: kalıcı örnek dizini ve kalıcı önizleme — done — 2026-11-11
- Yapıldı: göç 0036 `example_index` (ad, boyut, SHA-256, tür, sayfa, SHA'dan önizleme anahtarı, `present`/`removed`, `archived_at`); örnek önizlemeleri `cache/previews` yerine kalıcı `KnownDocuments/_onizlemeler/<slug>/` (gece yedeğine girer); oturumlu `list_examples`/`find_example`/`store_example` dizini okur-yazar, `sync_example_index` kayıtsız dosyaları ekler ve ham dosyası kalkanı `removed` yapar; ham yokken tür sayfaları ad + kayıt + önizleme gösterir, "İndir" yerine "Ham dosya silindi", dosya ucu 404, `/previews/thumbs` dizinden, tür açıklaması ve recheck büyük önizlemeyle, aynı SHA tekrar sayılır, taşı/çıkar dizin satırı + önizlemeyi taşır; `python -m app.training previews` önce dizini eşitler.
- Doğrulama: ruff check/format, compileall, `import app.main`, `git diff --check`, `python -m app.i18n check`, temiz SQLite'ta `alembic upgrade head` (→0036) exit 0; tests/web + storage + training + catalog + db + i18n + scripts + worker + pipeline + ai + test_events + S20 + S23 (-n 6) 5236 geçti, 9 atlandı; yeni `tests/storage/test_example_index.py` 9, `tests/web/test_example_raw_removed.py` 7, +7 (decisions, pair_review, describe, migrations, backup). Tam kapı (`--cov`, ~50 dk) koşulmadı (insan kuralı).
- Varsayımlar: dizin satırı ham dosyanın yerine yalnız `removed` işaretliyse geçer (habersiz kaybolan dosya taşınamaz, "bulunamadı"); dizine henüz girmemiş örneğin adres sürümü eski ad/boyut/zaman anahtarıdır ve o da `immutable` sayılır (ham varken davranış değişmez). Ölçüm (yerel `data/`, 200 örneklem): 2209 örnek için kalıcı önizleme ≈ 349 MB (küçük ~11 KB, büyük ~147 KB), üretilemeyen 0. Eski `cache/previews/<slug>/` örnek önizlemeleri artık okunmaz (önbellek; elle silinebilir).
- Sonraki pencereye not: YanPC'ye DAĞITILMADI (göç 0036). tm 202 `purge-originals`: `sync_example_index` + `warm_previews(layout, session)` (oturumda bekleyen yazma olmamalı; okuyup işlemi bırakır) hazır; silmeden sonra `mark_original_removed`/sync çağrılır.

## 200 — 15.1-d Arşivdeki şablonu kalıcı sil: iki aşamalı onay, üretilmiş belge varsa engel — done — 2026-10-27
- Yapıldı: Hazır Şablonlar › Arşivde satırında ve arşivdeki şablonun sayfasında `button.danger` "Sil" (yazma yetkisi) → `GET …/{id}/delete/confirm` (ad, sayfa/alan sayısı, birinci metin ya da "bu şablondan N üretilmiş belge var") → `POST …/delete/prepare` (ikinci metin "geri alınamaz", belirteç) → `POST …/delete`: önce `cache/previews` + `_sablonlar/<id>/`, sonra alan haritası sürümleri; satır `deleted` iskeleti (göç 0035), `USER_CONFIRMED` + `OUTPUT_TEMPLATE_DELETED`; etkin/taslak/hazır 409, dosya silinemezse kayıt kalır (500, yeniden denenebilir); en/sr.
- Doğrulama: ruff check/format, compileall, `import app.main`, `git diff --check`, `python -m app.i18n check`, temiz SQLite'ta `alembic upgrade head` (→0035) exit 0; tests/web + i18n + catalog + db + output_templates + worker + profiles + test_events + S29 (-n 6) 2620 geçti, 5 atlandı (PostgreSQL); yeni `tests/web/test_output_template_delete.py` 5 test, `test_migrations.py` +1. Tam kapı (`--cov`, ~50 dk) koşulmadı (insan kuralı).
- Varsayımlar: İNSAN KARARI 2026-10-27 — `access_log.template_id` şablona bağlı ve erişim logu silinmez; bu yüzden şablon satırı tamamen silinmez, dosyaları ve haritası silinip `deleted` iskeleti kalır (§D134 c'deki "kayıt silinir"in uygulanışı). İskelette ad korunur, `normalized_name`/`sha256` `deleted:<id>` olur (aynı ad ve dosya yeniden yüklenebilir); `get_template` ve listeler iskeleti görmez (404). Üretilmiş belge sayısı her durumdakileri sayar.
- Sonraki pencereye not: YanPC'ye DAĞITILMADI; dağıtımda göç 0035 koşar. Faz 1 tablosunda açık satır kalmadı; KF1 yeniden denetimi ayrı iştir, tablo `AÇIK` bırakıldı.

## 199 — 11.1-h Reddedilen aday türü kalıcı sil: iki aşamalı onay, olay kaydı — done — 2026-10-27
- Yapıldı: Aday türler › Reddedilenler satırında "Geri al" yanında `button.danger` "Sil" (yalnız yazma yetkisi) → `GET …/candidate-types/{id}/delete/confirm` (aday adı, görülme sayısı, birinci metin) → `POST …/delete/prepare` (ikinci metin "geri alınamaz", belirteç aday + görülme sayısına bağlı) → `POST …/delete` koşullu silme (yalnız `rejected`; bekleyen/onaylı 409, yok 404), `USER_CONFIRMED` + `CANDIDATE_TYPE_DELETED` {aday, ad, görülme}; sayfalar/yüklemeler/belgeler değişmez, aynı ad yeniden önerilirse yeni aday doğar; en/sr çeviri.
- Doğrulama: ruff check/format, compileall, `import app.main`, `git diff --check`, `python -m app.i18n check`, temiz SQLite'ta `alembic upgrade head` exit 0; tests/web + i18n + catalog + db + test_events (-n 6) 2392 geçti, 4 atlandı (ilk koşuda kırmızı `test_there_is_no_way_to_delete_a_type` aday istisnasını tanıyacak şekilde güncellendi, dosya yeniden 91/91); yeni `tests/web/test_candidate_delete.py` 6 test. Tam kapı (`--cov`, ~50 dk) koşulmadı (insan kuralı).
- Varsayımlar: onay metinleri §20.6 dışı (§D134), `app/web/routers/catalog.py`'de; "görülme kaydı" ayrı tablo değil, adayın `sample_page_ids`/`seen_count` alanlarıdır — kayıtla gider. Onay sayfası `catalog_candidate_step.html` içinde `step == "delete"` (yeni sınıf yok). PRD §8.3 olay listesine `CANDIDATE_TYPE_DELETED` eklendi.
- Sonraki pencereye not: YanPC'ye DAĞITILMADI. Faz 1'de açık: 15.1.5 (tm 200).

## 198 — 11.1-g Belge Türleri: ülke süzgecinin yanına arama kutusu ve Ara düğmesi — done — 2026-10-27
- Yapıldı: `GET /document-types?q=` (≤100) türün adında, dosya etiketinde ve slug'ında harf büyüklüğü/aksan/Türkçe ı-İ duyarsız alt dize arar, ülke süzgeciyle AND birleşir, arşiv görünümünde de çalışır; ülke seçiminin yanında etiketli arama alanı + "Ara" (Enter da), sonuç satırında "Temizle", boş sonuçta "Eşleşen tür yok."; `q` bağlantılarda, toplu işlemde, tekil işlemlerde, arşiv adımlarında, tür formunda (`list_q`) ve yönlendirmelerde korunur.
- Doğrulama: ruff check/format, compileall, `import app.main`, `git diff --check`, `python -m app.i18n check`, temiz SQLite'ta `alembic upgrade head` exit 0; tests/web + tests/i18n (-n 6) 1801 geçti, yeni `tests/web/test_catalog_search.py` 21 test. Tam kapı (`--cov`) koşulmadı (insan kuralı).
- Varsayımlar: "Temizle" formda değil sonuç satırında (htmx yalnız `#catalog-results`'ı değiştirir; formda dursa arama sonrası güncellenmezdi). Yalnız noktalamadan oluşan arama süzmez. JS kapalıyken "Uygula" (noscript) yerinde kaldı; "Ara" her zaman görünür. Form `aria-label`'ı "Türleri ülkeye göre süz ve ara" oldu.
- Sonraki pencereye not: YanPC'ye DAĞITILMADI. Faz 1'de açık: 11.1.9 (tm 199), 15.1.5 (tm 200).

## 197 — 11.9-j Tüm belgeler için genel önizleme katmanı — done — 2026-10-27
- Yapıldı: her belge kaynağı (çalışan belgesi, profil fotoğrafı, yükleme/kuyruk/geçmiş/aday sayfası, üretilen belge, şablon sayfası) `PreviewSource` ile aynı 320/1280 px JPEG üretiminden geçer; listeler yalnız küçük JPEG (`loading=lazy decoding=async`), ada/küçük resme tıklayınca büyük önizleme (çok sayfalıda `…/preview` sayfası, sayfa sayfa ≤20), orijinal yalnız İndir; çalışan verisi kademe 2 (`private, max-age=900` + ETag/304), şablon kademe 1 (`immutable`, `?v=`); her uç kaynağın mevcut 404 kuralını kullanır.
- Doğrulama: ruff check/format, compileall, `import app.main`, `python -m app.i18n check`, temiz SQLite'ta `alembic upgrade head` exit 0; tests/web + storage + scripts + i18n + training + pipeline (-n 6) 3596 geçti, 4 atlandı. Tam kapı (`--cov`) koşulmadı (insan kuralı).
- Varsayımlar: erişim logu kuralı — önizleme sayfası (`…/documents/<id>/preview`, `…/outputs/<id>/preview`) açılışı `view`; küçük/büyük JPEG uçları kayıt yazmaz (ön yükleme ve liste N satır yazmasın). Doğrudan büyük JPEG adresini açan kullanıcı kayda girmez — bilinçli boşluk, gerekirse ayrı görev. Yükleme sayfası önizlemesi orijinal dosyanın o sayfasından, orijinal yoksa analiz görüntüsünden üretilir. Şablon sayfasında "Yeni sekmede aç" kalktı (İndir kaldı); alan haritası tam sayfa görüntüsünü kullanmaya devam eder. Silinen belgelerin eski önizleme dosyaları önbellekte kalır (yedeğe girmez).
- Sonraki pencereye not: YanPC'ye DAĞITILMADI. `/file` uçları duruyor (bot ve eski yer imleri için) ama arayüz bağlanmıyor. Faz 1'de açık satır kalmadı; KF1 yeniden denetimi ayrı iştir, tablo `AÇIK` bırakıldı.
