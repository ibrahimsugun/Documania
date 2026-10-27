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

## 196 — 11.9-i Önizleme ön yükleme: giriş sonrası küçükler, sayfaya girince o sayfanın büyükleri — done — 2026-10-27
- Yapıldı: `preview-prefetch.js` (yalnız girişli sayfada) boşta `/previews/thumbs` listesinden bütün küçük önizlemeleri 2 eşzamanlı + 150 ms arayla, `priority: "low"` ile HTTP önbelleğine indirir, bitince `localStorage`'a yalnız sürüm yazar; sayfadaki `data-preview-large` (tür, katalog örnekleri, `/uploads/<id>` sayfa görüntüleri) önce iner; tıklama/HTMX/çıkışta iptal, gizli sekme/saveData/2g'de durur, 429/503'te `Retry-After` geri çekilme. Sunucu: en çok 2 önizleme üretimi + tek üretim kilidi, ön yükleme beklemez (`503 Retry-After: 2`), liste ucu oturum başına 30/dk; sayfa görüntüsü `private, max-age=900` + ETag/304; çıkışta `Clear-Site-Data: "cache"`.
- Doğrulama: ruff check/format, compileall, `import app.main`, `python -m app.i18n check`, temiz SQLite'ta `alembic upgrade head` exit 0; tests/web + storage + scripts + i18n + training (-n 6) 2431 geçti, 4 atlandı; headless Chrome + CDP ile ağ günlüğü (en çok 2 eşzamanlı, orijinal yok, ikinci açılışta yalnız liste + sayfa büyükleri, tıklamada iptal). Tam kapı (`--cov`) koşulmadı (insan kuralı).
- Varsayımlar: liste yalnız eğitim tür sayfası adreslerini verir (`/training/known/<slug>/previews/small/…`); katalog sayfası küçükleri ayrı adreste olduğundan ısıtılmaz, büyükleri aşama 2 ile iner. İmleç sayısal sıra (belge adı saklanmaz). Ön yükleme isteği `X-Preview-Prefetch: 1` başlığıyla ayrılır; kullanıcı isteği sırasını bekler. `asyncio.Semaphore` yerine `threading` (uçlar eşzamanlı değil, Starlette iş parçacığı havuzunda koşar).
- Sonraki pencereye not: YanPC'ye DAĞITILMADI. `Clear-Site-Data` yalnız HTTPS'te (belge.siyahkus.com) ya da localhost'ta etkilidir. Faz 1'de açık satır kalmadı; faz kapanışı (KF1 yeniden denetimi) ayrı iştir, tablo `AÇIK` bırakıldı.

## 195 — 11.9-h Örnek önizlemeleri: küçük türetilmiş önizleme, orijinal yalnız İndir — done — 2026-10-27
- Yapıldı: `app/storage/previews.py` örnekten bir kez 320/1280 px JPEG üretir (`cache/previews/<slug>/<anahtar>-<boyut>.jpg`; PDF'te ilk sayfa; EXIF/ICC yok; piksel sınırı/bomba/bozuk → yer tutucu); eğitim ve katalog sayfaları küçük resmi `…/previews/small/<ad>?v=<anahtar>` ile `loading=lazy decoding=async` alır, ad büyük önizlemeyi açar, orijinal yalnız "İndir" (`attachment`); önizleme `private, max-age=31536000, immutable` + ETag/304 + `nosniff`; `python -m app.training previews` toplu ısıtır; `backup.sh` `cache/previews`'ı hiç arşivlemez; YEDEKLEME, `.env.example`, i18n (en, sr).
- Doğrulama: ruff check/format, compileall, `import app.main`, temiz SQLite'ta `alembic upgrade head`, `python -m app.i18n check` exit 0; tests/web + storage + scripts + i18n + training (-n 6) yeşil. Tam kapı (`--cov`) koşulmadı (insan kuralı: uzun kapı beklenmez).
- Varsayımlar: anahtar içerik özeti yerine ad+boyut+mtime (§D130 izin verir; listeleme dosya okumaz); büyük önizleme yeni sekmede JPEG olarak açılır (iletişim kutusu/JS yok); sürümsüz ya da eski `?v=` isteği aynı baytları `private, no-cache` ile verir; eski anahtarlı önizleme dosyaları silinmez (önbellek, yedeğe girmez).
- Sonraki pencereye not: YanPC'ye DAĞITILMADI. Dağıtımdan sonra `docker compose exec app python -m app.training previews` ile ~2.200 örneği önceden ısıtmak ilk açılış beklemesini önler. tm 196 (ön yükleme, §D131) bu uçların üzerine kurulur.

## 194 — 13.4-b Eğitim malzemesi ayrı hacimlerde ve gece arşivinin dışında — done — 2026-10-27
- Yapıldı: Compose `examples` ve `_egitim` için ayrı hacimler bağlar, `backup.sh` eğitim malzemesini gece arşivine almaz, yeni `scripts/backup-material.sh` onu rsync ile artımlı ve silmeden yedekler/geri koyar.
- Doğrulama: ruff check/format, `tests/scripts` + `tests/deploy` geçti (rsync'li 4 test geliştirme makinesinde rsync yok diye atlandı); tam kapı (`--cov`) koşulmadı (insan kuralı: 50 dk'lık kapıyı bekleme).
- Varsayımlar: §D129 — `_referans` data hacminde kalır ama arşivden çıkar; `--delete` yok; `gelen` tekilleştirme kapsam dışı.
- Sonraki pencereye not: YanPC'ye DAĞITILMADI. Geçiş (insan izni gerekir): uygulamayı durdur → imajı kur → `known_examples`/`known_training` hacimlerine kopyala (`cp -a`) → sayı/bayt doğrula → `data` hacmindeki eski `examples`/`_egitim`'i kaldır → `up -d`; sonra `BACKUP_MATERIAL_DIR` ve `MATERIAL_*_DIR` ile `backup-material.sh`'i bir kez çalıştır.
