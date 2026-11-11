# HANDOFF arşivi — 2026-11-11

Kaynak: HANDOFF.md (canlı dosyadan taşındı, birebir). Blok sayısı: 1.

<!-- bloklar (newest-first) -->

## 196 — 11.9-i Önizleme ön yükleme: giriş sonrası küçükler, sayfaya girince o sayfanın büyükleri — done — 2026-10-27
- Yapıldı: `preview-prefetch.js` (yalnız girişli sayfada) boşta `/previews/thumbs` listesinden bütün küçük önizlemeleri 2 eşzamanlı + 150 ms arayla, `priority: "low"` ile HTTP önbelleğine indirir, bitince `localStorage`'a yalnız sürüm yazar; sayfadaki `data-preview-large` (tür, katalog örnekleri, `/uploads/<id>` sayfa görüntüleri) önce iner; tıklama/HTMX/çıkışta iptal, gizli sekme/saveData/2g'de durur, 429/503'te `Retry-After` geri çekilme. Sunucu: en çok 2 önizleme üretimi + tek üretim kilidi, ön yükleme beklemez (`503 Retry-After: 2`), liste ucu oturum başına 30/dk; sayfa görüntüsü `private, max-age=900` + ETag/304; çıkışta `Clear-Site-Data: "cache"`.
- Doğrulama: ruff check/format, compileall, `import app.main`, `python -m app.i18n check`, temiz SQLite'ta `alembic upgrade head` exit 0; tests/web + storage + scripts + i18n + training (-n 6) 2431 geçti, 4 atlandı; headless Chrome + CDP ile ağ günlüğü (en çok 2 eşzamanlı, orijinal yok, ikinci açılışta yalnız liste + sayfa büyükleri, tıklamada iptal). Tam kapı (`--cov`) koşulmadı (insan kuralı).
- Varsayımlar: liste yalnız eğitim tür sayfası adreslerini verir (`/training/known/<slug>/previews/small/…`); katalog sayfası küçükleri ayrı adreste olduğundan ısıtılmaz, büyükleri aşama 2 ile iner. İmleç sayısal sıra (belge adı saklanmaz). Ön yükleme isteği `X-Preview-Prefetch: 1` başlığıyla ayrılır; kullanıcı isteği sırasını bekler. `asyncio.Semaphore` yerine `threading` (uçlar eşzamanlı değil, Starlette iş parçacığı havuzunda koşar).
- Sonraki pencereye not: YanPC'ye DAĞITILMADI. `Clear-Site-Data` yalnız HTTPS'te (belge.siyahkus.com) ya da localhost'ta etkilidir. Faz 1'de açık satır kalmadı; faz kapanışı (KF1 yeniden denetimi) ayrı iştir, tablo `AÇIK` bırakıldı.
