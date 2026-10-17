# FIX11 — Windows EXE / GES SQL şeması paketleme onarımı

## Sorunun kökü

FIX10 Windows EXE derlenmişti ancak `Start local simulator` veya `--smoke-server` sırasında
`FileNotFoundError: ... _internal/simulator/solar/ges_history_schema.sql` oluşuyordu.
PyInstaller `--collect-submodules simulator` ile Python dosyalarını toplar; Python modüllerinin
yanındaki SQL şemasını otomatik eklemek garanti değildir. Simülasyonun GES geçmişini oluşturması
için bu SQL dosyası zorunludur.

## FIX10'u tekrar derlemeden hemen onar

FIX10 proje klasöründe PowerShell aç. Uygulama kapalıyken:

```powershell
$hedef = '.\dist\AutonomousPlantSimulatorV20_FIX10\_internal\simulator\solar'
New-Item -ItemType Directory -Force -Path $hedef | Out-Null
Copy-Item '.\simulator\solar\ges_history_schema.sql' -Destination $hedef -Force
```

Bu işlem kaynak SQL şemasını uygulamanın beklediği yere kopyalar. Tam dağıtım için FIX11'i kullan.

## FIX11 ile temiz derleme

1. FIX11 ZIP'i **Tümünü ayıkla** ile yeni bir klasöre çıkar; ZIP önizlemesinden çalıştırma.
2. `02_YALNIZ_TEST.cmd` ile Windows regresyon testlerini çalıştır.
3. `06_WINDOWS_TAM_EXE_DERLE.cmd` çalıştır. PyInstaller paketinde SQL dosyası yoksa
   veya kaynakla SHA-256 eşleşmiyorsa artık derleme başarısız sayılacak.
4. `dist\AutonomousPlantSimulatorV20_FIX11\AutonomousPlantSimulatorV20_FIX11.exe`
   dosyasını `_internal` klasörüyle birlikte çalıştır. Masaüstü kısayolu da oluşturulmayı deneyecek.
5. EXE'de `Start local simulator` seç; ardından HES/GES/RES ve `GES / RES live twins` düğmelerini dene.

**Günlük:** `WINDOWS_EXE_DERLEME_RAPORU.txt`.
**Uygulama günlükleri:** `%LOCALAPPDATA%\AutonomousPlantPlatform\logs\`.

## Yapılan değişiklikler

- `desktop/build_full_windows_v20.ps1` ve GitHub Windows Actions betiği SQL dosyasını **mutlak kaynak yoldan** `simulator/solar/` hedefine paketler.
- Yerel ve CI derlemeleri kaynak ve paket içindeki SQL dosyasının SHA-256 değerini karşılaştırır.
- Donmuş EXE açılışında `models/hes_anomaly_iforest.joblib`, GES SQL şeması ve iki statik HTML dosyası doğrulanır.
- Yeni `tests/test_fix11_frozen_sql_resources.py` ile kaynak, derleme reçetesi, CI ve eksik varlığa karşı fail-closed davranışı test edilir.

**Sınır:** Linux'taki Python regresyon testleri Windows EXE'nin çalıştığını tek başına ispatlamaz.
Windows üzerinde tam derleme, `--self-test`, `--smoke-server` ve GUI testi ayrı ayrı gereklidir.
Bu yazılım yalnızca **sentetik HES/GES/RES simülasyonu** içindir; gerçek PLC/SCADA veya tesis kontrolü içermez.
