# Yedekleme ve geri yükleme (PRD 13.4.2)

Sistem kimlik belgeleri barındırır: "yedek var mı" ve "yedekten dönebiliyor muyuz" soruları
cevapsız kalamaz. Bu sayfa gece yedeğini, sunucu dışı kopyayı ve yedekten geri yükleme
prosedürünü anlatır. Betikler `scripts/` altındadır; ikisi de yalnız **kopyalar** — hiçbir belge
değiştirilmez, silinmez (K10, K11).

| Dosya | İş |
|---|---|
| `scripts/backup.sh` | Yedek alır: veritabanı + `DATA_DIR` → tek `belgeee-<UTC zaman>.tar.gz`, yanında `.sha256` |
| `scripts/restore.sh` | Yedeği doğrular, boş bir hedefe (ya da `--force` ile mevcudun yerine) geri yükler |
| `scripts/backup-material.sh` | Eğitim malzemesini (gece arşivinin dışında) artımlı ve sıkıştırmasız kopyalar; `--restore` ile geri koyar |
| `scripts/backup-lib.sh` | İkisinin ortak işlevleri (kaynak alınır, tek başına çalıştırılmaz) |

Gereken araçlar: `bash`, GNU `tar`, `find`, `python3` (yalnız standart kitaplık; uygulamanın sanal
ortamı gerekmez). PostgreSQL için ayrıca `pg_dump`, `pg_restore`, `psql` (`postgresql-client`).

## Ne yedeklenir

- **Veritabanı.** SQLite'ta SQLite'ın kendi yedekleme arayüzüyle alınan tutarlı anlık görüntü
  (yazma sürerken dosya kopyalamak bozuk kopya verebilir; WAL kipindeki henüz işlenmemiş satırlar
  da girer); anlık görüntü `PRAGMA integrity_check`'ten geçmezse yedek başarısız sayılır.
  PostgreSQL'de `pg_dump --format=custom`. Parola komut satırına değil `PGPASSWORD` ortamına
  konur (`ps` çıktısında görünmez).
  Döküm bütün tabloları kapsar: erişim logu (`access_log`) ve giriş kaydı (`login_log`; IP ve
  tarayıcı bilgisi taşır) da veritabanı yedeğiyle alınır.
- **Veri dizini** (`DATA_DIR`): Inbox'taki orijinal yüklemeler, çalışan klasörleri (`Alinan`,
  `Hazir`, `Uretilen`), katalog ve hazır şablonlar (`KnownDocuments/_sablonlar/`). SQLite dosyası
  veri dizininin içindeyse canlı dosya (ve `-wal`, `-shm`, `-journal`) arşive girmez; yerine tutarlı
  anlık görüntü girer.
- **Eğitim malzemesi gece arşivine girmez** (`KnownDocuments/examples`, `_egitim`, `_referans`):
  birkaç GB tutar (örnekler, eğitim modunda yüklenen dosyaların kopyası, referans görüntüler), JPG/PDF/PNG
  sıkışmaz ve kaynak koleksiyondan yeniden üretilebilir. Bunun yedeği ayrıdır (aşağıda, "Eğitim
  malzemesinin yedeği"). Arşivin `MANIFEST.txt`'inde `material=excluded` yazar; `BACKUP_INCLUDE_MATERIAL=1`
  verilirse malzeme de arşive girer (`material=included`).
- **Örnek önizlemeleri arşive girmez** (`cache/previews`, 11.9.7): eğitim ve katalog sayfalarının
  gösterdiği küçük JPEG'lerdir, örneklerden yeniden üretilir. Geri yüklemeden sonra ilk istekte
  kendiliğinden üretilir; hepsini önceden üretmek için `python -m app.training previews`.
- Arşivin içi: `MANIFEST.txt` (zaman, veritabanı türü, veritabanı dökümünün SHA-256'sı, dosya
  sayısı), `db/…`, `data/…`. Arşiv `umask 077` ile yazılır (yalnız sahibi okur) — kimlik belgesi
  içerir.

Yedek **şifrelenmez**: uygulama düzeyinde şifreleme yoktur; koruma sunucu düzeyindedir (disk
şifreleme — LUKS ya da sağlayıcının çözümü — ve sunucu dışı hedefin kendi erişim denetimi). Sunucu
dışı hedef olarak şifrelenmemiş, paylaşımlı bir yer seçmeyin.

## Ayarlar

Ortam değişkeni ya da depo kökündeki `.env` (ortam değişkeni önceliklidir). `DATABASE_URL` ve
`DATA_DIR` uygulamayla aynıdır; betikler depo kökünden çalıştırılır (göreli yollar oradan çözülür).

| Değişken | Anlamı | Varsayılan |
|---|---|---|
| `DATABASE_URL` | `sqlite:///…` ya da `postgresql[+sürücü]://kullanıcı:parola@sunucu[:port]/veritabanı[?sslmode=…]` | zorunlu |
| `DATA_DIR` | Veri dizini | `data` |
| `BACKUP_DIR` | Yedeklerin yazıldığı yerel dizin; `DATA_DIR`'in **içinde olamaz** | `backups` |
| `BACKUP_KEEP_DAYS` | Bu günden eski yedekler silinir; `0` = silme | `14` |
| `BACKUP_COPY_DIR` | Sunucu dışı kopya için dizin (bağlı ağ paylaşımı, harici disk) | boş |
| `BACKUP_SCP_TARGET` | Sunucu dışı kopya için `kullanıcı@sunucu:/dizin` (`scp` ile; anahtarla, parolasız) | boş |
| `BACKUP_INCLUDE_MATERIAL` | `1` ise eğitim malzemesi de gece arşivine girer | boş (girmez) |
| `BACKUP_MATERIAL_DIR` | `backup-material.sh` hedefi: yerel dizin ya da `kullanıcı@sunucu:/dizin` (`rsync` ile) | zorunlu (o betik için) |
| `MATERIAL_EXAMPLES_DIR`, `MATERIAL_TRAINING_DIR`, `MATERIAL_REFERENCE_DIR` | `backup-material.sh` kaynakları (`examples`, `_egitim`, `_referans`) | `$DATA_DIR/KnownDocuments/…` |

**Sunucu dışı kopya:** `BACKUP_COPY_DIR` ya da `BACKUP_SCP_TARGET` tanımlıysa yedek oraya da
gider; kopya başarısız olursa betik **hata koduyla biter** (cron e-postası ya da izleme yakalasın).
İkisi de boşsa betik "yedek yalnız bu sunucuda" uyarısı yazar — bu, sunucu yandığında yedeğin de
gitmesi demektir; üretimde en az biri tanımlı olmalıdır. Budama (`BACKUP_KEEP_DAYS`) `BACKUP_DIR`
ve `BACKUP_COPY_DIR` içinde yalnız `belgeee-*.tar.gz*` adlı dosyaları siler ve yalnız **yeni yedek
başarıyla alındıktan sonra** çalışır. `BACKUP_SCP_TARGET` tarafı budanmaz; orada saklama süresini
hedef sunucu yönetir.

## Gece yedeği

Sunucuda uygulamanın çalıştığı hesapla, depo kökünden (örnek: her gece 02:30):

```cron
30 2 * * * cd /srv/belgeee && ./scripts/backup.sh >> /var/log/belgeee-backup.log 2>&1
```

Betik başarıyla bittiğinde çıkış kodu 0'dır; günlükte `yedek hazır: …` satırı ve (tanımlıysa)
`sunucu dışı kopya yazıldı` satırı görünür. Zamanlayıcıyı kurmak sunucu kurulumunun parçasıdır
(13.5.1 üretim dağıtımı); bu görev betiği ve prosedürü teslim eder. Yedek alınırken yükleme sürüyorsa
tar "dosya okunurken değişti" uyarısı verebilir; yedek yine geçerlidir, sürerken gelen dosya bir
sonraki geceye kalır.

Yedeğin işe yaradığını **haftada bir** geri yükleme provasıyla doğrulayın (aşağıda).

## Eğitim malzemesinin yedeği

Malzeme gece arşivinde olmadığı için ayrı yedeklenir: `scripts/backup-material.sh` `rsync -a` ile
`BACKUP_MATERIAL_DIR`'e kopyalar (yerel dizin, harici disk ya da `kullanıcı@sunucu:/dizin`).
İlk koşu hepsini taşır, sonrakiler yalnız yeni ya da değişen dosyaları; **sıkıştırma yok**.
Kasıtlı olarak `--delete` kullanmaz: ne kaynakta ne hedefte bir şey silinmez; kaynak dizin yok ya da
boşsa (hacim bağlanmamış olabilir) atlanır ve hedefteki yedek yerinde kalır. Hedef kaynağın içinde olamaz.

```cron
30 3 * * 0 cd /srv/belgeee && ./scripts/backup-material.sh >> /var/log/belgeee-backup-material.log 2>&1
```

(Haftada bir yeterli: malzeme gece değişmez; eğitim koşusu yaptığınız gün elle de çalıştırılabilir.)

**Geri alma:** `./scripts/backup-material.sh --restore` hedefteki dosyaları kaynağa koyar; var olan
dosyanın üzerine **yazmaz** (`--ignore-existing`). Docker'da dosyalar uygulama kullanıcısına (uid
10001) ait olmalıdır: `chown -R 10001:10001 <hacim yolu>`. Gece arşivinden geri yüklemeden sonra
(`restore.sh` bunu hatırlatır) veritabanındaki örnek kayıtlarının dosyaları ancak bu adımla döner.
Malzeme kaybolursa kaynak koleksiyon (toplayıcı aracın çıktısı) ikinci yoldur.

### Docker Compose üretim dağıtımında (13.5.1)

`docker compose --profile production up -d --build` ile kurulan sunucuda uygulama ve PostgreSQL
konteynerdedir, betikler ise **sunucunun kendisinde** (konteyner dışında) çalışır:

- **Veritabanı:** `db` servisi `127.0.0.1:5432`'yi yalnız bu makineye yayınlar; betik `pg_dump` ile
  buradan bağlanır (`postgresql-client` sunucuya kurulur). `.env`'e `DATABASE_URL=postgresql://belgeee:<POSTGRES_PASSWORD>@127.0.0.1:5432/belgeee`
  yazılır. Konteynerdeki uygulama bu satırı kullanmaz (`APP_DATABASE_URL` kullanır).
- **Veri dizini:** `data` adlı Docker hacmi. `.env`'e `DATA_DIR=` olarak hacmin diskteki yolu yazılır:
  `docker volume inspect belgeee_data --format '{{ .Mountpoint }}'` (Linux'ta genelde
  `/var/lib/docker/volumes/belgeee_data/_data`; hacim adı Compose proje adından, yani depo
  klasörünün adından gelir). Dosyalar konteyner kullanıcısına (uid 10001) aittir; cron `root` ile
  koşmalıdır.
- **Eğitim malzemesi ayrı hacimlerdedir:** `docker-compose.yml` `KnownDocuments/examples` ve
  `KnownDocuments/_egitim` yollarına `known_examples` ve `known_training` hacimlerini bağlar (uygulama
  için yol aynıdır; veritabanındaki göreli yollar değişmez). `DATA_DIR`'e verdiğiniz `data` hacmi bu
  yüzden küçüktür ve gece yedeği yalnız onu alır. `backup-material.sh` için kaynak yolları:
  `docker volume inspect belgeee_known_examples --format '{{ .Mountpoint }}'` (ve `…_known_training`)
  çıktısı `MATERIAL_EXAMPLES_DIR` / `MATERIAL_TRAINING_DIR` olarak `.env`'e yazılır; `_referans`
  `data` hacminde kalır (varsayılan yol yeter, uygulama onu kullanmaz).
- **Geri yükleme:** önce `docker compose --profile production stop app bot caddy` (db çalışır
  kalır), betik, sonra `docker compose --profile production up -d`. Şemayı `migrate` adımı `up`'ta
  zaten `alembic upgrade head` ile günceller (aşağıdaki 4. adım ayrıca gerekmez).

Bu kurulum yerelde `DOMAIN=localhost` ile ayağa kaldırılıp panele girildi; yedek betiklerinin
gerçek PostgreSQL konteynerine karşı koşusu **denenmedi** (aşağıdaki "Deneme kaydı" sınırı geçerli).

## Geri yükleme prosedürü

Uygulamayı **durdurun** (`docker compose stop app bot` ya da servis neyse). Sonra hedef sunucuda,
depo kökünden, hedef `DATABASE_URL`/`DATA_DIR` ayarlıyken:

1. **Yedeği seçin.** En yenisi `BACKUP_DIR`'de ya da sunucu dışı hedefte; adı zamandır
   (`belgeee-20260919T023000Z.tar.gz`, UTC). Arşivin yanında `.sha256` dosyası da bulunmalı.
2. **Geri yükleyin:**

   ```bash
   ./scripts/restore.sh /yol/belgeee-20260919T023000Z.tar.gz
   ```

   Betik sırayla: arşivin SHA-256'sını ve içindeki veritabanı dökümünün özetini doğrular → hedefi
   denetler → veri dizinini yan dizine açar, dosya sayısını arşivle karşılaştırır → yerine koyar →
   veritabanını yükler (SQLite'ta `PRAGMA integrity_check`) . Doğrulama geçmezse hedefe **hiçbir
   şey yazılmaz**.
3. **Hedef boş değilse betik durur.** Veri dizini doluysa, SQLite dosyası varsa ya da PostgreSQL
   veritabanında tablo varsa `--force` istenir. `--force` ile mevcut veri dizini ve SQLite dosyası
   **silinmez**, `.before-restore-<zaman>` adıyla yanına çekilir; işiniz bitince siz silersiniz.
   PostgreSQL'de `--force`, `pg_restore --clean --if-exists` ile mevcut nesnelerin **üzerine yazar**
   — önce ayrı bir `pg_dump` alın.
4. **Şemayı güncelleyin.** Yedek, uygulamanın eski bir sürümünden olabilir: `alembic upgrade head`.
5. **Uygulamayı başlatın** ve panelde bir çalışan profilini, bir belgeyi ve `/access-log`'u açıp
   verinin geldiğini gözle kontrol edin.

Yarım kalmış geri yükleme `DATA_DIR.restoring` dizinini bırakırsa betik bir sonraki çalışmada
durur; dizini inceleyip kendiniz silin.

### Felaket senaryosu (sunucu tamamen kayıp)

Yeni sunucuda uygulamayı kurun (kod, `.env`, Docker), sunucu dışı hedeften en yeni arşivi ve
`.sha256`'ını getirin, yukarıdaki 2. adımı boş `DATA_DIR` ve boş veritabanıyla çalıştırın, sonra 4–5.
Kayıp en çok son yedekten bu yana geçen süredir (gece yedeğinde en fazla bir gün).

## Deneme kaydı — geri yükleme bir kez denenmiştir

Prosedür otomatik testte gerçek betiklerle uçtan uca denendi (`tests/scripts/test_backup_restore.py`,
her koşuda yeniden çalışır); sentetik belgelerle, gerçek kimlik belgesi kullanılmadan:

| Tarih | Ne denendi | Sonuç |
|---|---|---|
| 2026-09-19 | `test_restore_drill_into_a_fresh_location_…`: yedek alındı, **yeni bir konuma** geri yüklendi | Her dosya bayt bayt aynı (Türkçe/Kiril/boşluklu adlar dahil); çalışan, belge ve erişim logu satırları aynı; `integrity_check: ok` |
| 2026-09-19 | `test_restore_drill_after_the_server_is_lost_…`: veri dizini ve veritabanı **tamamen silindi**, yedek başka bir dizindeki kopyasından **aynı yola** döndürüldü | Aynı sonuç |
| 2026-09-19 | Bozuk arşiv, bozuk veritabanı dökümü, dolu hedef | Hedefe hiçbir şey yazılmadan reddedildi; `--force` mevcudu silmeden yanına çekti |

Sınırlar (dürüstçe): deneme SQLite ile yapıldı. PostgreSQL yolu (`pg_dump`/`pg_restore`) bu
makinede gerçek sunucuyla değil, komut satırını ve ortamı kaydeden sahte istemci araçlarıyla
sınandı. **Üretim dağıtımı (13.5.1) PostgreSQL'e geçtiğinde ilk gerçek sunucuda bu prosedürün bir
kez daha, gerçek `pg_restore` ile denenmesi ve buraya satır eklenmesi gerekir.**

## Sunucu düzeyi (uygulama dışı)

Disk şifreleme (LUKS ya da sağlayıcının çözümü), sunucu dışı hedefin erişim denetimi ve
şifrelemesi, cron/zamanlayıcının kurulumu ve yedek başarısızlığının izlenmesi sunucu kurulumunun
işidir (13.5.1, 13.6.1). Uygulama düzeyinde şifreleme yoktur.
