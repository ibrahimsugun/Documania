# Documania — Akıllı Çalışan Belge Yönetim Sistemi

Çalışanlardan gelen belgeleri **içeriğinden** anlayan, kime ait olduğunu bulan, hatalı
gönderimleri kurallar dahilinde fiziksel olarak düzenleyen, emin olamadığında insana soran
ve yaptığı her işi izlenebilir biçimde loglayan bir belge yönetim platformu.

> **Ad:** Ürünün adı **Documania**'dır (eski adı *belgeee*). Depo klasörü, veritabanı dosyası
> (`data/belgeee.db`), Docker hacmi ve Postgres kullanıcısı, yedek arşivlerinin adı
> (`belgeee-*.tar.gz`) ve oturum çerezi eski adı taşır: bunlar veriye ve eski yedeklere bağlıdır,
> bilerek değiştirilmedi (PLAN §D91).

> **Durum:** Uygulama ve test paketi mevcut; gereksinim kapsamı ve pilot/üretim hazırlığı `PLAN.md` ile izlenir. Dağıtım ve süreç sınırları aşağıdaki adımlarda belgelenmiştir.

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
| [`docs/YEDEKLEME.md`](docs/YEDEKLEME.md) | Gece yedeği, sunucu dışı kopya ve geri yükleme prosedürü (`scripts/backup.sh`, `scripts/restore.sh`) |

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

### Karar tabloları (PRD §20)

MAX görev sayısı 14'ten 4'e indi — bölerek değil, **kararı önceden verip yazarak**. MRZ alan
yerleşimi ve kontrol hanesi algoritması, çalışan eşleştirme karar tablosu, işlem seçimi
tablosu, Direkt Belge izin matrisi ve dosya işlemlerinin kayıpsızlık sözleşmesi artık PRD
§20'de yazılı. İlgili görev bu tabloyu **zorunlu okuma** olarak taşır.

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

## Üretim dağıtımı (PRD 13.5.1–13.5.2)

Alan adı ve HTTPS ile **tek komutla** dağıtım: PostgreSQL 16, şema göçü, HTTP uygulaması, aynı imajdan
ayrı kuyruk worker'ı ve HTTPS'i sonlandıran Caddy (sertifikayı Let's Encrypt'ten kendisi alır ve yeniler) birlikte kalkar.

**Ön koşullar:** Docker Engine + Docker Compose **2.24 veya üstü**; alan adının DNS A/AAAA kaydı
sunucuyu göstermeli; sunucuda 80 ve 443 dışarıya açık olmalı.

**1. Ayar.** Depoyu sunucuya alıp `cp .env.example .env` yapın ve `.env`'de şunları doldurun
(`.env.example` sonundaki "Üretim dağıtımı" bölümünde satır satır açıklanmıştır; `#`'ler kaldırılır):

| Değişken | Ne |
|---|---|
| `APP_ENV=production` | Panel çerezi yalnız HTTPS'te gider; bot webhook kipine geçer |
| `DOMAIN` | Panelin alan adı (`belge.sirket.com`) |
| `ACME_EMAIL` | Sertifika uyarıları için e-posta |
| `POSTGRES_PASSWORD` | `openssl rand -hex 24` çıktısı (yalnız harf/rakam) |
| `APP_DATABASE_URL` | `postgresql+psycopg://belgeee:<POSTGRES_PASSWORD>@db:5432/belgeee` |
| `ANTHROPIC_API_KEY` (ya da `AI_PROVIDER=openai` + `OPENAI_API_KEY`) | Worker için zorunlu; eksikse worker hata verip yeniden başlar, kuyruk işlenmez — dağıtımdan önce sağlayıcı ayarını girin |

**2. Tek komut:**

```bash
docker compose --profile production up -d --build
```

Sırasıyla `preflight` (ayar denetimi — eksik ya da tutarsız ayarda komut anlaşılır bir hatayla
biter) → `db` → `migrate` (`alembic upgrade head`) tamamlanır; ardından HTTP `app` ve `worker`
ayrı servisler olarak başlar. Worker `python -m app.worker` çalıştırır, HTTP portu yayınlamaz ve
aynı DB/veri hacmini kullanır. Caddy, sağlıklı `app` servisini bekleyip HTTPS'i sonlandırır.
Komut bitince `https://<DOMAIN>` açılır; HTTP istekleri HTTPS'e yönlendirilir.

**3. İlk yönetici** (panel girişsiz açılmaz; parola terminalden gizli sorulur):

```bash
docker compose exec app python -m app.web create-admin --username <ad>
```

**4. Doğrulama:**

```bash
curl -fsS https://<DOMAIN>/health          # {"status":"ok"}
curl -sI  http://<DOMAIN>/health           # 308 → https://<DOMAIN>/health
docker compose --profile production ps -a  # app healthy, worker Up, migrate exited (0)
docker compose logs worker               # kuyruğun tüketildiğini/worker hatalarını doğrula
```

**Güncelleme:** `git pull` sonra aynı komut (`docker compose --profile production up -d --build`);
`migrate` yeni göçleri uygular, veri hacimleri (`data`, `pgdata`, `caddy_data`) korunur.
İmaj bağımlılıkları `uv.lock`'taki sürüm ve hash'lerle kurar; kilit `pyproject.toml` ile uyuşmazsa yapı
durur (`uv lock` ile kilidi yenileyip commit edin). Her servisin konteyner logu en çok 5 × 10 MB tutulur
(`docker-compose.yml` `x-logging`); daha eskisi kendiliğinden silinir.
**Durdurma:** `docker compose --profile production down` — **`-v` vermeyin**: hacimler yüklenen
belgeleri, veritabanını ve sertifikayı taşır (`-v` hepsini siler).

**Telegram botu (isteğe bağlı):** komuta `--profile telegram` eklenir; `TELEGRAM_BOT_TOKEN` ve
`TELEGRAM_WEBHOOK_SECRET` `.env`'e yazılır. Webhook adresi varsayılan olarak
`https://<DOMAIN>/telegram/webhook`'tur; Caddy `/telegram/*` yolunu bota yönlendirir.
Bot yalnız beyaz listedeki Telegram kimliklerine yanıt verir. Telegram'ı herkes **yalnız kendi
hesabına** bağlar: **Hesabım → Telegram** (`/account/telegram`, Kullanıcılar sayfasında
«Telegram'ım») sayfasındaki **Telegram'ı bağla** kişinin kendisi için 10 dakika geçerli, tek
kullanımlık bir bot bağlantısı (`https://t.me/<bot>?start=<kod>`) üretir; kişi bağlantıyı kendi
telefonunda açıp «Başlat»a basınca bot kimliğini hesabına kendisi bağlar. Düğme, bot en az bir kez
çalışıp adını veri dizinine (`data/telegram/bot.json`) yazdıktan sonra açılır. Yedek yol aynı
sayfada elle eklemedir: kimlik telefon numarası değil, Telegram'ın hesaba verdiği sabit sayıdır;
kişi bota `/start` yazarak ya da [@userinfobot](https://t.me/userinfobot)'tan öğrenir (sayı ya da
kopyalanan `Id: …` satırı). Bot sade, kısa ve teknik terimsiz yazar (12.1.9): parti numarası, kuyruk türü, gerekçe ya da
çalışan numarası göndermez; kuyruğa yeni öğe düşünce listedekilere tarama başına tek mesaj gider
("Kontrol etmeniz gereken N yeni belge var"), parti hatası ve izleme uyarısı Telegram'a gitmez.
Bot, bağlı olmayan birinin `/start`'ına tek bir kısa yanıt verir:
bağlı değilsiniz, panelde Hesabım → Telegram'ı açın; son satırda yalnız Telegram numarası (sohbet
başına saatte bir). Bağlı kişinin yardım ve «Bağlandı» yanıtı da numarayı söyler. Yönetici Kullanıcılar sayfasında başkasının kimliğinin iznini kapatıp
açabilir (kaybolan telefon), başkası adına kimlik ekleyemez ve bağlantı üretemez.
Telegram kaydı silinebilir (12.1.10): yönetici Kullanıcılar sayfasında, kişi kendi Hesabım →
Telegram sayfasında «Kaydı sil»e basar. Numara serbest kalır ve aynı ya da başka bir hesaba yeniden
bağlanabilir (telefon ya da hesap değişince). Silmenin izi olay logundadır.

**Botla konuşma (12.3, 12.1.11, 12.1.12):** bot belge ister (“Ahmet Çakar'ın ehliyeti”), tek mesajda birden çok türü yanıtlar (“ehliyet ve CV'si var mı?” → her tür için var/yok), kişinin kısa bilgisini verir (“kaç yaşında?”, “hangi belgeleri var?”) ve bir belge grubu için eksikleri söyler (“adres kaydı için hangi belgeleri tamamlamalı?”; paket yoksa paket açmadan grubu kişinin belgeleriyle karşılaştırır). Kişi adı yazılmayan istek (“ehliyeti de”) son 10 dakikadaki kişiye uygulanır. Sesli mesaj, video, çıkartma gibi mesajlara kısa bir yanıt verir. Kişiye yazdığı dilde (Türkçe, İngilizce, Sırpça) yanıt verir; bu dil bot yeniden başlayana dek sonraki yanıtlarda da kullanılır.

**Kalıcı silme (10.5.12, 10.5.13; PLAN.md §D110, §D113, §D116):** sistem kendiliğinden hiçbir şey
silmez; İK elle ve iki aşamalı onayla siler, geri alma yoktur. Profilin belge listesindeki «Kalıcı
sil» tek belgeyi siler. İşten ayrılan çalışan önce pasife alınır, sonra pasif profildeki «Çalışanı
kalıcı sil» onu bütün belgeleriyle siler (etkin çalışan silinmez). **Silinenler:** çalışan klasörü
(`Hazir`, `Alinan`, `profil.md`), belgelerin dosyaları (etkin, arşivdeki, eski sürüm), isim
yazımları, belge numaraları, iletişim bilgileri, profil alanı gözlemleri, paketler, yalnız o
çalışana ait yüklemelerin Inbox orijinali ve sayfa görüntüleri; planlardaki hedef dosya adı ve
olayların mesajı/verisindeki kişisel değerler temizlenir. **Kalanlar:** çalışan ve belge satırı
iskelet olarak (E numarası, belge kimliği, tür, tarihler, kim ve ne zaman sildi; E numarası bir
daha verilmez), olay ve erişim logu satırları, başka bir çalışana ya da açık kuyruk öğesine de
kaynak olan orijinal ve sayfalar, yüklemenin dosya adı kaydı (`upload_files.original_name`).
Silinen çalışanın adresi «silindi» sayfasıdır (410); liste, arama, eşleştirme ve bot onu görmez,
aynı kişinin yeni belgesi yeni çalışan açar. **Yedekler:** gece yedeğindeki kopyalar yedeğin kendi
saklama süresiyle gider; silme yedeklere dokunmaz.

**Takılan parti (PRD 10.3.6, 10.3.7):** partiyi yalnız ayrı worker süreci işler; worker kapalıysa
parti "Alındı"da bekler. Süren partinin detayında "Partiyi iptal et" iki onayla partiyi durdurur;
alındıktan 10 dakika sonra hâlâ bitmemiş parti kendiliğinden "İptal edildi" olur (denetim worker'ın
her kuyruk turunda ve panelde yükleme listesi ya da parti detayı açılırken). İptal hiçbir dosyayı,
sayfayı ya da belgeyi silmez; aynı dosya yeniden yüklenince tekrar sayılmaz, yeniden işlenir. Süre
yerleşik 600 saniyedir, `.env`'de `UPLOAD_TIMEOUT_SECONDS` yalnız ezer (en az 60).

**Yedekleme:** gece yedeği ve geri yükleme prosedürü [`docs/YEDEKLEME.md`](docs/YEDEKLEME.md)'de
(Compose kurulumuna özgü ayarlar orada). Zamanlayıcı (cron) sunucuya elle kurulur.

**İzleme ve uyarı (PRD 13.6.1):** hata (son bir saatte üç işlenemeyen parti), disk doluluğu (veri
diski yüzde 85), işçi kuyruğu (20 bekleyen parti) ve karar bekleyen kuyruk (50 öğe) eşiği aşınca
uyarı üretilir: worker sürecinin logunda (`docker compose logs worker`, satır "Uyarı — …"). Uyarı
Telegram'a gitmez: bot yalnız sade mesaj gönderir (PRD 12.1.9). Süren uyarı altı saatte bir
hatırlatılır, eşiğin yüzde 90'ının altına inince "Uyarı giderildi" yazılır. Eşikler ve aralıklar
`.env`'deki `ALERT_*` değişkenleridir (`.env.example`). PostgreSQL'in kendi hacmi (`pgdata`)
uygulama sürecinden görünmez, ölçülmez.

**Ağ yüzeyi:** dışarıya yalnız Caddy'nin 80/443'ü açılır. Panel (`8000`) ve PostgreSQL (`5432`)
yalnız `127.0.0.1`'e yayınlanır (ssh tüneli, sunucudaki yedek betiği için). Bu değişiklikle
geliştirmede de panel yalnız `http://127.0.0.1:8000`'den açılır.

**Bu depoda denenen ve denenmeyen:** yığın yerelde `DOMAIN=localhost` ile (Caddy'nin kendi yerel
sertifika otoritesi) uçtan uca ayağa kaldırılıp HTTPS, HTTP→HTTPS yönlendirmesi, `Secure` çerezli
giriş ve göçlerin gerçek PostgreSQL 16'da çalışması doğrulandı. **Gerçek bir alan adında Let's
Encrypt sertifikası alma bu depoda denenmedi** (production dağıtımı ve DNS bu deponun sınırı
dışındadır); Let's Encrypt'in yinelenen sertifika sınırı nedeniyle `caddy_data` hacmini gereksiz
yere silmeyin.

## Bilinmesi gerekenler

- **Uzak git deposu tanımlı değil.** Kapanışta push adımı atlanır, commit yeterlidir
  (`CONVENTIONS.md` §2). Remote eklemek istersen bu senin kararın; pencereler kendiliğinden
  eklemez.
- **Gerçek kimlik belgesi depoya girmez.** Testler `tests/fixtures/gen.py` ile üretilen
  sentetik belgeleri kullanır (`CONVENTIONS.md` §6). `data/` dizini `.gitignore`'dadır.
- **Satır sonları LF'e sabitlendi** (`.gitattributes`). `run-loop.sh` CRLF ile checkout
  edilirse bash çalıştıramaz.
- **Kod güncellendikten sonra paneli `baslat.bat` ile yeniden başlatın** (PRD 13.5.3). Bat dosyası
  önce `alembic upgrade head` koşar, sonra sunucuyu açar. `--reload`'suz çalışan sunucu açılıştaki
  Python kodunu kullanmaya devam eder, şablonları ise diskten okur. Bu yüzden yeniden
  başlatılmayan panel yeni sayfalarda 500 verebilir. Kod açılıştan sonra değiştiyse panel her
  sayfanın üstünde "Sunucu eski sürümle çalışıyor — yeniden başlatın" uyarısı gösterir. Göç
  koşulmamış veritabanıyla panel, işçi ve bot hiç açılmaz; hata iletisi mevcut ve beklenen
  sürümü söyler. `GET /health` çalışan sürecin şema sürümünü (`schema`) ve kod parmak izini
  (`code`) döner.
- **Yerelde Telegram botu `baslat.bat` ile açılır** (PRD 12.1.5). `.env`'de `TELEGRAM_BOT_TOKEN`
  doluysa bat dosyası göçten sonra botu (geliştirmede polling) ayrı bir "Documania bot" penceresinde
  başlatır; boşsa "Telegram botu kapalı: .env'de TELEGRAM_BOT_TOKEN yok" yazar ve paneli botsuz
  açar. Token değeri ekrana yazılmaz. Bot açmak için: Telegram'da [@BotFather](https://t.me/BotFather)'a
  `/newbot` yazıp botu oluşturun, verdiği token'ı `.env`'deki `TELEGRAM_BOT_TOKEN=` satırına yazın
  (token depoya girmez, yalnız yerel `.env`'de durur) ve `baslat.bat`'ı yeniden çalıştırın. Bot
  hata verip kapanırsa pencere açık kalır ve nedenini gösterir. Panel durunca bot penceresi
  kendiliğinden kapanmaz; `baslat.bat`'ı yeniden çalıştırmadan önce eski bot penceresini kapatın
  (aynı token'la iki bot aynı anda dinleyemez).
- **Arayüz dili** (PRD 10.10.1, 10.10.3; PLAN.md §D92): panel English (`en`), Türkçe (`tr`) ve
  Srpski (`sr`, Latin alfabesi) dillerinde sunulur, açılış dili İngilizcedir. `.env`'deki
  `PANEL_DEFAULT_LANGUAGE` bunu değiştirir; tarayıcının dil ayarı kullanılmaz. Kaynak dil
  Türkçedir: şablonda `{{ _("…") }}` ya da `{% trans %}…{% endtrans %}`, Python'da
  `app.i18n.gettext` (modül düzeyindeki sabit etikette `N_`) ile işaretlenen Türkçe metin
  msgid'dir. Çeviri akışı: `python -m app.i18n extract` (işaretli metinler →
  `app/i18n/locales/messages.pot`) → `python -m app.i18n update` (`en`/`sr` `messages.po`'ya yeni
  metin boş çeviriyle girer) → `.po`'da çeviri ([terim sözlüğü](app/i18n/GLOSSARY.md)) →
  `python -m app.i18n compile` (`.mo`; çalışma zamanı bunu okur, depoya girer) →
  `python -m app.i18n check` (boş, bulanık, eksik metin, yer tutucu ve eski `.mo` denetimi; testte
  de koşar). Testler varsayılan dili `tr` yapar (`tests/conftest.py`). İki aşamalı onay
  metinleri (PRD §20.6) kataloğa girmez: `app/web/confirm.py` dil başına PRD'den birebir tutar
  (Türkçe §20.6, İngilizce ve Sırpça §20.6.3; `tests/web/test_confirm.py` tabloyla karşılaştırır) —
  değişecek metin önce PRD'ye yazılır.
- **Faz 0'ın ilk dört görevi DoD kapısının kendisini kurar**; o görevlerde kapı, kurulduğu
  kadarıyla koşulur (`CONVENTIONS.md` §1.1).

## Yığın

Python 3.12 · FastAPI · SQLAlchemy + Alembic · SQLite (geliştirme) / PostgreSQL (üretim) ·
PyMuPDF + pypdf + img2pdf + Pillow · Jinja2 + HTMX · Babel (gettext) · python-telegram-bot · Anthropic API
(birincil) + OpenAI (ikincil) · pytest + ruff · Docker Compose. Tam liste ve gerekçeler
`MASTER-PROMPT.md` §4'te.
