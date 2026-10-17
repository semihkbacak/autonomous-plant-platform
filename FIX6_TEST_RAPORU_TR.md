# FIX6 — Test ve teslim raporu

**Tarih:** 16 Ekim 2026 · **Kapsam:** HES/GES/RES yerel sentetik simülasyon, masaüstü kodu, GES/RES canlı araştırma panosu. Fiziksel tesis/onay kanıtı değildir.

## Linux testi
- Python 3.13.5 + proje bağımlılıkları + yerel pvlib kaynak kopyası: **702 passed, 2 warnings, 0 failed**.
- Uyarılar: kayıtlı IsolationForest/ExtraTreeRegressor modelinin scikit-learn 1.9.1 ile oluşturulması, test ortamının 1.8.0 kullanması. Windows paketi `requirements.txt` içinde scikit-learn==1.9.1 istemektedir.
- `python -m desktop.full_simulator_launcher --self-test`: PASS, Uvicorn, FastAPI, PV, RES/Wind, iki simülasyon motoru doğrulandı.
- `python -m desktop.full_simulator_launcher --smoke-server`: PASS; gerçek Uvicorn sunucusu geçici loopback portunda HTTP isteğine yanıt verdi.
- `python scripts/verify_release_assets.py`: 5/5 SHA-256 PASS.
- `python scripts/security_preflight_v20.py`: yerel SIMULATION / SHADOW değişmezleri PASS. Bu bir sızma testi değildir.
- İlk açılış sentetik GES: 1 run / 4 interval, MPPT ve P-Q hazır; RES: 1 run / 96 interval, iki türbin hazır; kayıtlara HTTP üzerinden erişim PASS.
- `/api/v1/live-twins/state`: HES, GES, RES sentetik durumları API'den okundu. GES ve RES birer adım çalıştırıldı (GES gece 0 kW beklenen davranış).
- GES `POST /api/v1/sim-console/ges/daylight`: sentetik gün içi ışıma örneğine hızlı ilerleme PASS.

## Windows .exe — henüz haricî doğrulama gerekir

- Kullanıcının önceki exe'si `No module named 'uvicorn'` ile sunucuyu başlatamıyordu. Önceki `--self-test` bu bağımlılığı gerçek anlamda yüklemiyordu.
- FIX6 `--self-test` artık Uvicorn ve bağlı bileşenleri gerçekten içeri alıp test eder; `--smoke-server` gerçek ASGI süreç/HTTP smoke testi gerçekleştirir.
- `06_WINDOWS_TAM_EXE_DERLE.cmd`: yeni, **farklı isimli** `dist\AutonomousPlantSimulatorV20_FIX6\AutonomousPlantSimulatorV20_FIX6.exe` üretir; gerçek Windows makinede bu derleme komutu çalıştırılmadan EXE var veya sorunsuzdur denemez.
- PyInstaller Windows üzerinde inşa edilmelidir; bu teslim Linux çalışma ortamında kaynak kod ve testlerden oluşturulmuştur. Windows imzası, antivirüs, SmartScreen, Windows 10/11 ve gerçek GUI kullanılabilirlik testleri burada yürütülemedi.
- `ges_oem_research.zip` içindeki üçüncü taraf verilerin yeniden dağıtım hakları ve proje lisansı kullanıcı/ilgili hak sahibince doğrulanmalıdır. Gerçek PLC/SCADA kontrolü yoktur.
