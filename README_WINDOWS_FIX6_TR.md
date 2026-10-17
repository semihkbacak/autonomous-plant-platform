# Autonomous Plant Platform v2.0 — FIX6 (Windows / Linux)

**Kapsam:** yerel HES, GES, RES **sentetik** simülasyon motorları, çevrimdışı analitik, Windows masaüstü arayüzü ve canlı sentetik ikiz panosu. Gerçek tesis/PLC/SCADA bağlantısı, fiziksel saha kontrolü, OEM onayı ve imzalı Windows dağıtımı **yoktur**.

## Gönderdiğiniz arızanın asıl çözümü

Windows'ta önceki EXE pencereyi gösterebildiği halde "No module named 'uvicorn'" diye hata veriyordu. Eski derlemenin gerçek ASGI/FastAPI çalıştırılmadan önce yaptığı `--self-test` yalnızca çok yüzeysel URL kontrolü içeriyordu. FIX6, bir EXE'yi **başarılı** saymadan önce şunları yapar:

1. Paketlenmiş `uvicorn`, `fastapi`, `pvlib`, `sklearn`, `openpyxl`, `httpx` modüllerini gerçekten yükler.
2. FastAPI yollarını bulur ve GES/RES sentetik motorlarını en az birer adım ilerletir.
3. EXE'yi ayrı bir süreçte `--smoke-server` ile başlatıp **geçici yerel portta gerçek Uvicorn sunucusundan HTTP cevap** alır.
4. Testler başarısızsa derlemeyi başarısız işaretler ve `WINDOWS_EXE_DERLEME_RAPORU.txt` dosyasını korur.

Yeni EXE adı eskisinden farklıdır, karıştırmayın:

`dist\AutonomousPlantSimulatorV20_FIX6\AutonomousPlantSimulatorV20_FIX6.exe`

**`build\` klasöründeki herhangi bir EXE'yi çalıştırmayın.** `_internal` klasörünü EXE'nin yanından ayırmayın. Eski `AutonomousPlantSimulatorV20.exe` çalıştırılmamalıdır. `dist` dizini **Windows derlemesinde** oluşturulur; ZIP'in içinde hazır EXE yoktur.

## İlk kurulum — Windows 10 / 11

1. Önce çalışan eski sunucu/EXE'yi kapatın. `127.0.0.1:8000` portu boş olmalıdır.
2. ZIP'e sağ tıklayıp **Tümünü ayıkla**. Çıkarılan klasörü örneğin `C:\AutonomousPlant\FIX6` altına taşıyın. ZIP penceresinden `.cmd` çalıştırmayın.
3. Python **3.13 (64-bit)** kurulu ve internete erişim varken `01_WINDOWS_KUR_TEST_VE_BASLAT.cmd` çalıştırın; paketler yüklenir ve bütün pytest testleri çalıştırılır.
4. Bu kaynak uygulamanın masaüstü GUI'sini açmak için `05_WINDOWS_MASAUSTU_SIMULATORU.cmd` kullanın (aynı anda başka port 8000 sunucusu açık olmamalı).
5. `Start local simulator` tıklayın. **`GES / RES live twins`** tuşu yeni web simülasyon panelini açar. Panelde GES ve RES için ayrıca **Başlat** tuşlarını kullanın; 2 duvar saati saniyesinde 15 sentetik dakika ilerler. GES'in gece ilk aralıklarda 0 kW göstermesi beklenir: **`Gündüze İlerle`** ile yalnızca sentetik zamanı hızlı ileri alabilirsiniz.
6. Kaydedilmiş (gerçek olmayan) 1 GES günü örneği ve RES 1 günü: `/solar/analytics/dashboard` ve `/wind/dashboard` sayfalarında görünür. Dosyalar mevcutsa **üzerine yazılmaz**.
7. Bir önceki sunucuyu **kapatıp** `06_WINDOWS_TAM_EXE_DERLE.cmd` çalıştırın. Derleme birkaç dakika sürebilir. Sonunda hem EXE bağımlılık self-test'i hem **gerçek HTTP sunucu açma** kontrolü çalışır. Başarılı olursa yeni EXE için masaüstü kısayolu oluşturulur.
8. Kurulum/derleme başarısızsa `WINDOWS_EXE_DERLEME_RAPORU.txt` ve `WINDOWS_TEST_RAPORU.txt` dosyalarını gönderin. Özel anahtar, parola veya kişisel kayıt göndermeyin.

### EXE neden ZIP'in içinde hazır değil?

PyInstaller Windows EXE'yi **Windows üstünde** üretmelidir; Linux'ta oluşturulan EXE'yi Windows sürümüne eşdeğer kabul edemeyiz. Bu paket, derleme betiği + kaynak kod + testlerdir. `06_...cmd` çalışıp tüm kontrollerden geçmeden EXE'nin son kullanıcıya hazır olduğunu iddia etmeyin.

## Ne yeni?

- Eski ikizlerin yalnızca metin halinde sunulması yerine `/platform/live-twins`, `/platform/live-twins/ges` ve `/platform/live-twins/res` yeni sentetik canlı pano rotaları.
- GES: iki inverter gerçek simülasyon motoru, ışınım/ortam sıcaklığı, durumlar, güç ve enerji, 96 x 15 dakikalık aralık, Gündüze İlerle.
- RES: iki türbin gerçek simülasyon motoru, rüzgâr hızı/yönü, güç/enerji, turbin durumları, 96 x 15 dakikalık aralık.
- GES+RES oturumları çalışırken arkaplan saatinde otomatik 15 dk/2 s ilerler, ayrıca elle STEP yapılabilir.
- Canlı oturumların 96 noktalık güç geçmişi, her bir adımın sentetik zaman etiketleri ve referans birim verileri.
- İlk çalıştırmada sentetik RES historian, GES örnek historian ile aynı model: atomik oluşturma ve var olan dosyayı koruma.
- Windows EXE için Uvicorn, FastAPI, PV, rüzgâr motoru import/doğrulaması ve gerçek HTTP sunucu smoke test'i.
- Eski Windows ZIP'inden gelen `.venv`, `build`, `dist`, `*.exe`, geçici test dosyaları ve eski loglar temiz projeye alınmadı.

## Gerçek saha dijital ikizi değil

Bu canlı ekranlar **sentetik simülasyon sırasında güncellenen** ikizlerdir, saha ölçümüne bağlı değildir. Bunların ``GERÇEK GES/RES CANLI İKİZ`` olarak pazarlanması, OEM parametreleri, saha historian yetkisi, ölçüm kalibrasyonu ve bağımsız doğrulama olmadan yanlıştır. Yazılımdan gerçek kumanda isteği/PLC bağlantısı eklenmedi.

**Test notu:** FIX6 Linux Python 3.13 testleri kullanıcı Windows makinesindeki PyInstaller, antivirüs/SmartScreen, Win10/Win11 GUI ve imzalama davranışını kapsamaz. İmzalı dağıtım, kod lisansı ve OEM yeniden dağıtım hakları ayrı karar/kanıt gerektirir.
