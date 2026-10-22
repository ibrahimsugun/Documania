# CONVENTIONS gerekçeleri ve ölçümler

`CONVENTIONS.md`'den taşınan tarihçe/gerekçe metinleri (birebir). Kural değil, **neden böyle** kaydıdır;
pencerelerin her görevde okuması gerekmez. Bölüm numaraları `CONVENTIONS.md` ile aynıdır.

## §1 — Kapı tablosu, madde 4–5

Taşınan ifade: "tek paralel koşuda (~10 dk; seri koşu ~59 dk idi)".

## §1.1 Kapıyı kuran görevler istisnadır

Faz 0'ın ilk görevleri (`00.1.1` … `00.1.4`) kapının kendisini kurar. O görevlerde kapı,
**o görevin kurduğu kadarıyla** koşulur: `pytest` henüz test yokken "0 test" ile geçerse
bu kabul edilir, ama `00.1.2` bittiğinde en az bir gerçek test bulunmak zorundadır.
`00.1.4` bittikten sonra 1–4 arası maddeler her görevde koşulur, 5. madde Faz 0 kapanışından
itibaren zorunludur.

## §1.2 PLAN.md kanıt disiplini — sebebi

**Sebebi ölçümdür.** Kanıt hücrede biriktiğinde tablo satırı on binlerce karaktere çıkar;
sonraki her pencerenin `grep`'i o tek satırı okurken bağlam bütçesinin önemli bir kısmını
yakar. Ayrıca kanıt metnindeki kaçırılmamış `|` karakterleri satırı yanlış sütunlara böler
ve panel durumu yanlış okur.

**Canlı dosya boyutu (2026-10-14 ölçümü).** Kanıt maddeleri uzadıkça `PLAN.md` ~984 KB,
`HANDOFF.md` ~381 KB, `tasks.json` ~676 KB olmuştu; her pencere bunları taradığı için bağlam boşa
harcanıyordu. 2026-10-14'te eski bloklar/maddeler `docs/archive/` altına birebir taşındı
(`PLAN.md` ~169 KB, `HANDOFF.md` ~12 KB, `tasks.json` ~247 KB); kalıcı kural §1.2 ve §3'te.

## §1.4 Kapının önkoşulları — test süresi ve zaman aşımı

- Paralel suite ~10 dk sürer (seri koşu ~59 dk idi). Aracın varsayılan üst sınırı 600000 ms'dir ve
  daha büyük değer sessizce 10 dakikaya kırpılıp kapı yarıda kesilirdi. Bu yüzden sınır
  `.claude/settings.json` → `env.BASH_MAX_TIMEOUT_MS = 3600000` ile 60 dakikaya açıldı; bu ayarı
  kaldırma, kapıyı da parçalara bölme.
- Tam suite için `timeout: 2400000` (40 dk).
- `run_in_background` ile başlatılan test/build komutu, pencere sırasını bitirdiği anda oturumla
  birlikte ölür ve sonuç asla gelmez. 2026-10-23 insan kararı: testler yine de arka planda koşulur
  (zaman aşımı sınırı ve kaynak yönetimi için); pencere sonuç gelene kadar sırasını bitirmez
  (`Monitor`/bildirim). Aynı kararla testler hafif yazılır — suite süresi kısalsın.
- `-n 12` yalnız tam kapı komutundadır, `addopts`'a konmaz (tek dosya koşusunu yavaşlatır).
- Kararsızlık kuralının ayrıntısı: paralel koşuda düşüp seri koşuda geçen test "paralel yüzünden"
  denip geçilmez; ortak durum (modül düzeyi önbellek, sabit dosya yolu, `os.environ`, sabit port,
  `get_settings` önbelleği) aranır. Parametre kimlikleri süreçten sürece aynı olmalıdır (bellek
  adresi, zaman damgalı bayt taşımaz; gerekirse `ids=`).
