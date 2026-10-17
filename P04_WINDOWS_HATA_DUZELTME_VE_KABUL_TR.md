# Autonomous Plant Platform — P04, kaynak ve Windows kabul notu

**Kapsam:** Sentetik HES + GES + RES simülasyonu; gerçek PLC/SCADA, saha kumandası ve OEM doğrulaması YOK.

## P03 ekranından doğrulanan sorun

Kullanıcının gönderdiği `/platform/synchronized` ekranında `Durum: NOT_CREATED` ve `HTTP 409 {"detail":"No resumable run"}` görülüyordu. Önceki HTML düğmesi hiçbir oturum yokken doğrudan `/api/v2/clock/start` çağırıyordu. Bu, API'nin kayıt bütünlüğü adına doğru reddi, fakat arayüzün eksik onboarding davranışıydı. Ayrıca Windows `windows_start.py` yalnızca `/api/v1/plant` 200 yanıtına bakıyordu; 8000 portundaki önceki sürüm yanlışlıkla yeni sunucu sanılabilirdi.

## P04 onarımı

- P04 paneli, kullanıcı **başlat, +15 dakika, plan, setpoint veya santral komutu** düğmesine bastığında `status` kontrol eder; gerekirse `/create` ile yalnızca yerel, açıkça sentetik bir oturum oluşturur; asıl işlemi sonra yapar. Sayfanın salt açılması veri yazmaz. API `NOT_CREATED` durumunda doğrudan `/start` çağrısını yine 409 ile reddeder (koruma devam ediyor).
- İlk kurulum mesajı ve işlem nedenleri Türkçe, okunabilir hale getirildi. Plan başlangıcı oturumun mevcut UTC adımıyla doldurulur; manuel değişiklik korunur.
- HES/GES/RES fizik girdileri ham uzun JSON yerine okunabilir başlıklarla gösterilir; tek örnekten sonra grafik noktası görünür.
- `/api/v2/clock/build` yanıtı sürümü `UTC_DISPATCH_P04` olarak bildirir. Windows CLI başlatıcı 8000 portunu önce kontrol eder ve sunucunun beklenen sürümde SIMULATION modunda olduğunu teyit eder. Port doluysa **işlemi güvenli şekilde reddeder**, başka işlem sonlandırmaz.
- `START_HERE_WINDOWS.cmd` tam temiz kurulum/test/GUI akışıdır; `P04_HIZLI_BASLAT_WINDOWS.cmd` var olan kurulumu hızla açar, `P04_KABUL_TEST_WINDOWS.cmd` tam Windows test akışıdır.
- `APP_VERSION_P04.txt` + hazırlık betiği, önceki klasöre yanlışlıkla karışan dağıtımları ayırt etmek için kullanılır. P03 işaretinin tutulmasının nedeni geçmiş Windows testlerinin statik uyumluluk kontrolüdür.

## Çalıştırılan testler (Linux/Python 3.13, 17 Ekim 2026)

- Hedefli P04 / P01 ortak-UTC / dispatch testleri: **34 geçti, 2 atlandı**.
- Yeni P04 API+SQLite entegrasyon testleri: **4 geçti**.
- P03 kaynak ve Windows betiklerine yönelik statik uyumluluk + P04 testleri: **15 geçti**.
- Bağımlılıkları mevcut geniş Linux regresyon: **522 geçti, 7 atlandı, 8 özel bağımlılık testi dışarıda bırakıldı, 4 uyarı**; ayrıca 28 `pvlib` bağımlı modül bu ortamda toplanamadığından hiç dahil edilmedi.
- İsteğe bağlı gerçek Chromium DOM+JavaScript testi: **BAŞARILI**; tarayıcının ağ erişimi yönetici politikası nedeniyle yerel FastAPI TestClient köprüsü kullanıldı. Test adımları: ilk tıklamada START ve otomatik oturum → PAUSE → GES saatlik plan → manuel 12 kW setpoint → 15 dakika adımı → SQLite ve ekranda güç kontrolü. **Bu, Windows yerel uygulamasında test yapıldığı anlamına gelmez.**
- Sunulan P04 kaynakta `simulator/` veya `stage1/engine.py`, `stage1/store.py`, `stage1/dispatch.py`, `stage1/controller.py` üzerinde model/şema değişikliği yapılmadı. Onarım arayüz, sürüm denetimi ve test altyapısı ile sınırlıdır.

## Windows'ta nasıl doğrulanır?

1. Çalışan eski simülatör pencerelerini normal biçimde kapat. Windows 8000 portu başka bir programa aitse P04 onu kapatmaz; kullanıcı doğru uygulamayı kapatmalıdır.
2. **P04 tam ZIP** dosyasını eski P01/P02/P03 klasörleri üzerine değil, **yeni ve boş klasöre** tamamen çıkar.
3. Önce `START_HERE_WINDOWS.cmd` çalıştır. `python 3.13` ve internet bağımlılıkları gerekir. Tam testler başarılı olmadan GUI başlatılmaz.
4. Açılan masaüstü GUI'de `HES/GES/RES · UTC synchronized` seç. Üst satırda `Sürüm: UTC_DISPATCH_P04 · Mod: SIMULATION` görülmeli. Görünmüyorsa eski bir sunucu çalışıyor olabilir.
5. İlk kullanımda **Otomatik başlat** düğmesine tıkla; önce **Yeni oturum**a tıklama zorunluluğu olmamalı. Gerekirse **Duraklat**, santral seçimi, hedef ekleme ve **+15 dk** ile sonuçları kontrol et.
6. Önceki oturumlar ve denetim logları temizlenmez; `LOCALAPPDATA` altında mevcut SQLite korunur. Temiz test veritabanı isteniyorsa önce kullanıcı tarafından ayrıca yedeklenmelidir.

## Kabul sınırı

Bu ortamda Windows `.cmd`, Windows `.exe`, gerçek Tkinter Windows GUI, tam GES `pvlib` zinciri çalıştırılmadı. Gerçek Windows kabulü yalnızca kullanıcının çalıştıracağı **tam Windows regresyon + GUI tıklama testi** sonrası doğrulanabilir. Önceki 781/783 başarılı testten iki tanesinin `cp1254` problemi P02/P03 kaynaklarında düzeltilmişti; P04 bunları korur ancak Windows'ta koşulduğu iddia edilmez.
