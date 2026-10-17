# RC4 FIX5: GES geçmiş paneli ve Windows EXE derleme hata günlüğü

## GES paneli neden boştu?

`/solar/analytics/dashboard` bir GES *historian* SQLite dosyasını okur. Kaynak ZIP'e sentetik olarak oluşturulmuş `.sqlite3` dosyaları güvenlik/temizlik gerekçesiyle eklenmez. İlk kez açılan kurulumda bu dosya yoksa 404 alınıyordu.

FIX5 hem `01_WINDOWS_KUR_TEST_VE_BASLAT.cmd` ile başlatılan yerel simülasyon için, hem de `05_WINDOWS_MASAUSTU_SIMULATORU.cmd` ile açılan masaüstü sunucusu için yalnızca ilk kullanımda **dört 15 dakikalık, tamamen sentetik** örnek GES geçmişi üretir. MPPT/P-Q analiz grafikleri artık bu verilere dayanabilir. Örnek veri gerçek meteoroloji, OEM kalibrasyonu veya gerçek santral ölçümü değildir. Ayrıca daha uzun geçmiş oluşturmadan panelde sadece dört aralık bulunur.

Yalnızca örnek GES geçmişini kurmak için `07_GES_ORNEK_GECMIS_OLUSTUR.cmd` kullanılabilir. Bunun ardından çalışan sunucuyu **kapatıp yeniden başlatmak** gerekir; geçmiş dosyası yolu sunucu başlatılırken belirlenir. Veritabanı mevcutsa üzerine yazılmaz. `GES_HISTORIAN_DB` tanımlı ise kullanıcının özel veritabanı korunur ve varsayılan örnek kullanılmaz.

## EXE nereye gelir?

`06_WINDOWS_TAM_EXE_DERLE.cmd` ile başarılı Windows derlemesinden sonra:

`dist\AutonomousPlantSimulatorV20\AutonomousPlantSimulatorV20.exe`

EXE'nin yanında `dist\AutonomousPlantSimulatorV20\_internal\` klasörü de gerekir. Betik masaüstüne **kısayol** oluşturmayı dener; EXE'yi tek başına masaüstüne kopyalamaz. İmzasız önizleme, gerçek tesis kontrol ürünü değildir.

Derleme çıktıları/kapanma nedenleri aynı proje klasöründe `WINDOWS_EXE_DERLEME_RAPORU.txt` dosyasına yazılır. Komut penceresi başarısızlıkta da kapanmadan bekler. İşlem başarısızsa bu TXT'yi paylaşın; kimlik bilgisi/sertifika parolası paylaşmayın.

## Yeni paketi çalıştırma

1. ZIP'i tamamen ayrı bir klasöre ayıklayın (arşiv önizleme klasörü değil).
2. `01_WINDOWS_KUR_TEST_VE_BASLAT.cmd` ile testleri/yerel sunucuyu başlatın. Port 8000 başka bir sunucu tarafından kullanılıyorsa önce eski sunucuyu kapatın.
3. `http://127.0.0.1:8000/solar/analytics/dashboard` adresini yenileyin; en az 1 sentetik çalışma seçilebilmelidir.
4. Derleme için `06_WINDOWS_TAM_EXE_DERLE.cmd` çalıştırın, pencerenin son sonucuna bakın. Hata varsa `WINDOWS_EXE_DERLEME_RAPORU.txt` dosyasını paylaşın.

## Sınırlar

Linux kaynak testleri Windows EXE'nin başarıyla oluşturulduğunu **kanıtlamaz**. EXE'yi kullanıcının Windows 10/11 sisteminde derlemek gerekir. Bu düzeltme dosyayı üretmeyi/günlük toplamayı iyileştirir; imza, malzeme lisansı, gerçek OEM ve OT/saha kabulü sağlamaz.
