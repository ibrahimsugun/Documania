# belgeee — Akıllı Çalışan Belge Yönetim Sistemi

Çalışanlardan gelen belgeleri **içeriğinden** anlayan, kime ait olduğunu bulan, hatalı
gönderimleri kurallar dahilinde fiziksel olarak düzenleyen, emin olamadığında insana soran
ve yaptığı her işi izlenebilir biçimde loglayan bir belge yönetim platformu.

> **Durum:** belge sözleşmesi ve otonom yapım altyapısı kuruldu. Kod yazımı henüz başlamadı.
> İlk görev: `tm 1 — 00.1 Uygulama iskeleti`.

## Belgeler

| Dosya | Ne için |
|---|---|
| [`urun-gereksinim-dokumani-PRD.md`](urun-gereksinim-dokumani-PRD.md) | **Ne yapılacak** — 155 numaralı gereksinim, 14 modül, 4 faz, kabul kriterleri, karar tabloları, veri modeli, kabul senaryoları |
| [`MASTER-PROMPT.md`](MASTER-PROMPT.md) | **Nasıl yapılacak** — K1–K18 kilitli ürün kararları, yığın, contract-first sıra, sınırlar |
| [`CONVENTIONS.md`](CONVENTIONS.md) | **"Bitti" ne demek** — DoD kapısı (exit code'larla), git, handoff, kanıt disiplini, gizlilik |
| [`PLAN.md`](PLAN.md) | **Neredeyiz** — faz/modül/gereksinim durum tabloları, §G iş kırılımı, §K kanıt geçmişi |
| [`HANDOFF.md`](HANDOFF.md) | Pencereler arası köprü — her görev kapanışında blok eklenir |
| [`CLAUDE.md`](CLAUDE.md) | Her pencerenin otomatik okuduğu kısa çıpa |
| [`TASK-RUNNER-PROMPT.md`](TASK-RUNNER-PROMPT.md) | Bir pencerenin görevini nasıl yürüttüğü |
| [`run-loop.sh`](run-loop.sh) | Otonom döngü sürücüsü |
| [`docs/UYGULAMA-PLANI-KAYNAK.md`](docs/UYGULAMA-PLANI-KAYNAK.md) | İlk uygulama planı — tarihsel kaynak, taşınmaz |

## Nexa Panel ile izleme

Panel `~/Desktop/Claude_Loop_Controller-main` klasöründedir ve bu projeyi **yalnızca okur**.

```bash
node C:/Users/Hobbie/Desktop/Claude_Loop_Controller-main/server.mjs
```

Panel açılınca (`http://127.0.0.1:4545`) üst çubuktaki **📁 proje seç** rozetine tıkla ve
listeden **belgeee**'yi seç. Panel bu klasörü kendisi keşfeder (skor 14). Seçim kalıcıdır.

Kayıtlı seçimi değiştirmeden tek seferlik bağlanmak istersen:

```bash
DASH_PROJECT=C:/Users/Hobbie/Desktop/belgeee node C:/Users/Hobbie/Desktop/Claude_Loop_Controller-main/server.mjs
```

### Kurulumun doğrulandığı noktalar

Panelin kendi ayrıştırıcılarıyla ölçüldü:

| Kontrol | Sonuç |
|---|---|
| Workspace işaretleri | 9/11 (taskmaster, planMd, runLoop, claudeMd, masterPrompt, conventions, handoff, runnerPrompt, git) — skor 14 |
| PLAN gereksinim satırı | 155 (PRD kimliksiz 0, damgasız 0) |
| Faz özet sayıları | 4 fazın hepsi tablolardan sayılan değerle birebir (`plan-count-drift` yok) |
| §G düz tablo ↔ görev ağacı | 92 ↔ 92 (`plan-not-imported` yok) |
| Görev izlenebilirliği | 92/92 görev bir PRD kimliğine bağlı (`orphan-task` yok) |
| Bağımlılık grafiği | 0 sorun; sıradaki iş `tm 1` |
| Teşhis taraması | `errors: []`, critical/high bulgu yok |

## Görev bağlamı ve model seçimi

Her görev **ayrı ve bağlamsız** bir Claude penceresinde çalışır — önceki pencerenin
hafızası yoktur. Bu yüzden görevin `details` alanı bağlamı tek başına taşır:

```
KAPSAM · NE YAPILACAK (gereksinim + kabul kriteri) · GİRDİ (üzerine kurduğu, hâlihazırda
var olan kod ve dosyaları) · ÇIKTI (dokunacağı dosyalar) · BU GÖREVİ BAĞLAYAN KİLİTLİ
KURALLAR (K/R metinleri birebir gömülü) · PRD'DE AYRICA OKU · İLGİLİ KABUL SENARYOLARI ·
KAPSAM SINIRI · TUZAKLAR · KAPANIŞ
```

Ortalama 2.160 karakter. Pencere kuralı okumak için başka dosyaya gitmez; "üzerine ne
kuruyorum" sorusunun cevabı dosya adlarıyla yazılıdır.

Görev başlığındaki etiket hem **modeli** hem **eforu** seçer:

| Etiket | Adet | Ne tür iş |
|---|---|---|
| `[SONNET-XHIGH]` | 40 | Mekanik, kapsamı net, kabul kriteri ölçülebilir |
| `[OPUS-XHIGH]` | 48 | Karar, bütünlük veya kimlik mantığı taşıyan |
| `[OPUS-MAX]` | 4 | Yalnız bütün olarak değerlendirilebilen işler: gruplama üçlüsü (04.1–04.3) ve doğal dil niyeti (12.3) |

Belge bütünlüğü, kişi eşleştirme, Direkt Belge kuralı, kayıpsız PDF işlemleri ve kimlik
doğrulama **hiçbir koşulda** sonnet'e verilmez. Bir sonnet penceresi DoD kapısını geçemezse
döngü aynı görevi **opus ile** bir kez daha dener. Ayrıntı: `MASTER-PROMPT.md` §6.

### Karar tabloları (PRD §12)

MAX görev sayısı 14'ten 4'e indi — bölerek değil, **kararı önceden verip yazarak**. MRZ alan
yerleşimi ve kontrol hanesi algoritması, çalışan eşleştirme karar tablosu, işlem seçimi
tablosu, Direkt Belge izin matrisi ve dosya işlemlerinin kayıpsızlık sözleşmesi artık PRD
§12'de yazılı. İlgili görev bu tabloyu **zorunlu okuma** olarak taşır.

Sonuç: kodlama anında karar verilmiyor, uygulanıyor. Bir görev fazla zor geliyorsa ilk şüphe
efor seviyesi değil, **eksik spesifikasyondur**.

## Otonom döngüyü başlatma

Paneldeki **Başlat** düğmesi (önerilen — kota kapısı, nazik durdurma ve otomatik devam
devreye girer), ya da doğrudan:

```bash
cd C:/Users/Hobbie/Desktop/belgeee && ./run-loop.sh
```

İlk 1–2 görevi izle. Döngü her turda sıradaki görevi seçer, temiz bir pencerede baştan sona
yaptırır, DoD kapısından geçirir ve `PLAN.md` + `HANDOFF.md` + commit ile kapatır.

**Durdurma:** paneldeki *nazik durdurma*. Panel `.loop-logs/STOP-REQUESTED` bayrağını bırakır,
script bunu görev sınırında görüp kendi temiz çıkar — çalışan hiçbir pencere kesilmez.

## Bilinmesi gerekenler

- **Uzak git deposu tanımlı değil.** Kapanışta push adımı atlanır, commit yeterlidir
  (`CONVENTIONS.md` §2). Remote eklemek istersen bu senin kararın; pencereler kendiliğinden
  eklemez.
- **Gerçek kimlik belgesi depoya girmez.** Testler `tests/fixtures/gen.py` ile üretilen
  sentetik belgeleri kullanır (`CONVENTIONS.md` §6). `data/` dizini `.gitignore`'dadır.
- **Satır sonları LF'e sabitlendi** (`.gitattributes`). `run-loop.sh` CRLF ile checkout
  edilirse bash çalıştıramaz.
- **Faz 0'ın ilk dört görevi DoD kapısının kendisini kurar**; o görevlerde kapı, kurulduğu
  kadarıyla koşulur (`CONVENTIONS.md` §1.1).

## Yığın

Python 3.12 · FastAPI · SQLAlchemy + Alembic · SQLite (geliştirme) / PostgreSQL (üretim) ·
PyMuPDF + pypdf + img2pdf + Pillow · Jinja2 + HTMX · python-telegram-bot · Anthropic API
(birincil) + OpenAI (ikincil) · pytest + ruff · Docker Compose. Tam liste ve gerekçeler
`MASTER-PROMPT.md` §4'te.
