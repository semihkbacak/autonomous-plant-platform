# Autonomous Plant Platform — Aşama 1: ortak UTC dijital ikiz çekirdeği

**Kapsam:** Mevcut FIX11.1 kaynağı üzerine entegre edilen HES/GES/RES **sentetik**, çevrimdışı çok-santralli simülasyon. **Gerçek OT/PLC/SCADA/kumanda veya ölçülmüş saha verisi yoktur.** Bu belge Aşama 1'e aittir; fizik modeli OEM doğrulamasını veya gerçek dijital ikiz sertifikasını kapsamaz.

## Aşama 1 tamamlanan işlevler

1. **Tek UTC saat:** 15 dakikalık ortak zaman dilimi; her üç santral aynı `utc_start` / `utc_end` içinde işlenir. UTC gün başlangıcı `00:00:00+00:00` zorunlu, 1–31 günlük senaryolar.
2. **Eski fizik motorlarını yeniden kullanma:** HES 900 adet 1 saniyelik gerçek sentetik HES tick'i; GES/RES mevcut 15 dakika `SolarSession` / `WindSession` adımı. HES ortalama güç ve saniyelik enerji integrali tutulur.
3. **Çok günlük akış:** Her UTC gün sonundan sonra GES/RES günlük demo hava girişleri yeniden hazırlanır. Bu *aynı sentetik hava gününün tekrarıdır*, doğrulanmış çok günlük meteoroloji değildir.
4. **Kalıcı veri:** SQLite veritabanında run kimliği, sürüm ve konfigürasyon SHA-256, üç santral örnekleri, her slot için UTC, güç, interval enerjisi, toplam enerji ve özet ünite bilgisi bulunur.
5. **ATOMİK işlem:** Aynı veritabanı transaction'ında üç satır + HES/GES/RES kontrol noktası + ortak indeks kaydedilir. Üçünden biri hesaplanamaz veya yazılamazsa yarım slot kalıcı olmaz. Hata sonrası ilerleme kilitlenir; yeniden yükleme gerekir.
6. **Otomatik geri yükleme:** Mevcut SQLite dosyası uygulama yeniden açıldığında algılanır; kayıt/snapshot doğrulandıktan sonra eski simülasyon adımına dönülür. Kaza anında `RUNNING` olan oturum **kendiliğinden çalıştırılmaz**, `PAUSED_RECOVERED` olur; kullanıcı başlatmayı onaylar.
7. **Senaryo ve veri erişimi:** GES/RES mod seçimi (duraklatılmışken), otomatik başlat/duraklat, 1–96 adım ilerletme, eski oturumları listeleme, geçmiş UTC örnekleri ve CSV raporu.
8. **Masaüstü bağlantısı:** Ana Tkinter uygulamasındaki **HES/GES/RES · UTC synchronized** düğmesi yeni birleşik paneli açar: `http://127.0.0.1:8000/platform/synchronized`.
9. **Windows EXE entegrasyonu:** PyInstaller hem `stage1` Python modüllerini paketler hem de Windows native EXE smoke testinde `/api/v2/clock/status` yanıtını doğrular.

## Kurulum / başlatma

- **Windows:** Tam ZIP'i **Tümünü ayıkla** ile ayrı klasöre çıkar. Python 3.13 ve bağımlılık kurulumu için `01_WINDOWS_KUR_TEST_VE_BASLAT.cmd`; yalnızca Aşama 1 testleri + GUI için `08_WINDOWS_ASAMA1_TEST_VE_BASLAT.cmd`. Mevcut FIX11.1 `.venv` klasörü farklı dizinde kaldığı için yeni ZIP'e aktarılmaz.
- **Linux:** `bash 01_LINUX_KUR_TEST_VE_BASLAT.sh` ve ardından `bash 08_LINUX_ASAMA1_TEST_VE_BASLAT.sh`.
- **EXE:** Windows'ta `06_WINDOWS_TAM_EXE_DERLE.cmd` bütün testleri çalıştırır ve PyInstaller ile **eskiyle uyumlu `AutonomousPlantSimulatorV20_FIX11.exe` dosya adını** kullanır. EXE'yi `_internal` klasöründen ayırmayın. Bu sohbet içinde Windows EXE derlenmemiştir.

**Not:** Yeni Aşama 1, mevcut tekil legacy HES/GES/RES canlı panel oturumlarından **ayrı bir senkron portföy oturumudur**. Eski `/platform/live-twins` görüntüsü bağımsız simülatörleri göstermeye devam eder. Üçünün tam hizalı verisini yalnızca yeni `/platform/synchronized` sayfasında ve `/api/v2/clock/*` altında değerlendirin.

## Çalıştırma

1. Uygulamayı aç, **Start local simulator**, ardından **HES/GES/RES · UTC synchronized** düğmesini seç.
2. UTC gün başlangıcını ve 1–31 gün sayısını seç; **Yeni oturum**.
3. **+15 dk** bir adım, **+1 gün** en çok 96 adım ilerletir. **Otomatik başlat**, her 2 gerçek saniyede bir 15 dakikalık örnek oluşturur. **Duraklat** çalışma kaydını kapatır.
4. Sunucuyu kapatıp yeniden aç. Aynı konumda SQLite dosyası varsa önceki kayıt otomatik yüklenir. Kaza sonrasında otomatik simülasyon *durdurulmuş* kalır.
5. **CSV indir** ile üç santralin UTC hizalı örneklerini dışa aktar. Eski oturumlara API'de `run_id` parametresi ile erişilebilir.

## Veritabanı konumu

- Windows: `%LOCALAPPDATA%\AutonomousPlantPlatform\stage1\synchronized.sqlite3`
- Linux: `${XDG_STATE_HOME:-~/.local/state}/AutonomousPlantPlatform/stage1/synchronized.sqlite3`
- Test/izole senaryo için `APP_STAGE1_DB` ortam değişkeniyle özel bir yola alınabilir.
- Oturum verisini kaybetmeden sürüm yükseltmeden önce çalışmayan sunucuda SQLite dosyasını yedekleyin. `stage1.store.Journal.backup()` SQLite tutarlı yedek API'sidir. WAL dosyasını tek başına kopyalamayın.

## Stage 1 API

| Yöntem | Yol | Amaç |
|---|---|---|
| GET | `/api/v2/clock/status` | Son UTC ve tüm santrallerin ortak durumunu göster |
| GET | `/api/v2/clock/runs` | Kaydedilmiş oturumları listele |
| GET | `/api/v2/clock/history?limit=300&after=-1` | UTC örnekleri |
| GET | `/api/v2/clock/history?run_id=<id>` | Eski oturumdan örnekler |
| GET | `/api/v2/clock/export.csv` | Şimdiki oturumun CSV raporu |
| POST | `/api/v2/clock/create` | 1–31 günlük yeni sentetik UTC oturumu |
| POST | `/api/v2/clock/start` | İlerlemeyi başlat |
| POST | `/api/v2/clock/pause` | Oturumu duraklat |
| POST | `/api/v2/clock/step` | 1–96 ortak 15 dakikalık adım |
| POST | `/api/v2/clock/mode` | Duraklatılmış GES veya RES sentetik senaryosu |

POST işlemleri **yalnızca loopback + `APP_OPERATION_MODE=SIMULATION` + `X-Synthetic-Confirm: SYNTHETIC_ONLY`** ile kabul edilir; SHADOW modunda reddedilir. Bu kimlik doğrulama sistemi değildir. Sunucuyu internete veya OT ağına **açmayın**.

## Sınırlar ve risk

- SQLite SHA-256 zinciri kazara veri karışıklığını ve tekrarlı/eksik slotları tespit eder; **kriptografik olarak imzalı değiştirilemez denetim kaydı değildir**.
- GES/RES 15 dakikalık günlük sentetik veri döngüsü, 31 gün boyunca gerçekten ölçülen değişken hava koşullarının yerine geçmez.
- Eşit UTC başlangıcı **OEM doğruluğu, kalibrasyon, fiziksel senkronizasyon, ölçüm uygunluğu** anlamına gelmez.
- Aynı SQLite dosyasına birden fazla uygulamadan eşzamanlı yazı yazmayın. İşlem adımı ve doğrulama hata halinde reddedilir.
- Güvenlik sertifikası, imzalı Windows EXE, OEM/saha validasyonu, gerçek HIL/FAT/SAT bu Aşama 1 çıktısı değildir.

## Dosya bütünlüğü ve hazır iki günlük örnek

- `09_WINDOWS_ASAMA1_KAYNAK_DOGRULA.cmd` tüm paket kaynaklarını hash ile kontrol eder.
- `examples/stage1_two_day_SYNTHETIC_UTC.csv` ve `.json` örnek raporu gerçek mevcut HES/GES/RES modelleriyle **192 senkron aralık / 576 satır** üretir. Yalnızca sentetiktir.
