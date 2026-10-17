# FIX9 — Windows PyInstaller veri dosyası yolu düzeltmesi

Windows FIX8 test raporunda **708 passed, 1 warning** bulundu; GUI bağımlılık
öz testi de başarılıydı. Ancak PyInstaller, `--specpath` olarak verilen
`.build_full_v20` altında `app/static` aradığı için EXE üretimi durdu.

## Değişiklik

- `desktop/build_full_windows_v20.ps1`: `app/static`, `models`, `data/solar`
  ve giriş dosyası artık kaynak klasöründen **mutlak yol** ile verilir.
- `.github/workflows/research-v20-windows-bundle.yml`: CI derlemesi de
  izolasyon için ayrı `--specpath` kullanırken mutlak yollarla veri ekler.
- EXE adı `AutonomousPlantSimulatorV20_FIX9.exe` olarak değişti; önceki
  FIX8 derlemesiyle karışmaz.
- Yeni regresyon testleri hem yerel Windows PowerShell hem de CI betiğinin
  bu hata sınıfına geri dönmesini kontrol eder.

## Windows kurulum

1. Eski yerel simülasyon ve FIX8 EXE'yi kapatın.
2. **Tümünü ayıkla** seçeneğiyle FIX9 ZIP'ini ayrı bir klasöre çıkarın.
3. `02_YALNIZ_TEST.cmd` dosyasını çalıştırın; bütün testleri bekleyin.
4. `06_WINDOWS_TAM_EXE_DERLE.cmd` dosyasını çalıştırın; PowerShell derleme
   kaydı proje kökündeki `WINDOWS_EXE_DERLEME_RAPORU.txt` içinde tutulur.
5. Başarılı derlemeden sonra `dist/AutonomousPlantSimulatorV20_FIX9/`
   klasöründeki EXE'yi `_internal` klasörü ile birlikte çalıştırın.
6. GES/RES canlı **sentetik** ikizleri ve yerel sunucu başlat/durdur işlevlerini
   EXE GUI üzerinden kontrol edin.

`torch` ve `matplotlib` optional modül toplama uyarıları bu rapordaki
**bloklayıcı hata** değildir; sorun `--add-data` kaynak yoludur. Bunlar gerçek
bir bağımlılığa dönüşürse ayrıca analiz edilmelidir.

Bu, imzasız ve gerçek PLC/SCADA kontrolüne bağlanmayan bir araştırma
önizlemesidir. Linux testi Windows EXE'nin yerel GUI kabul testinin yerine
geçmez.
