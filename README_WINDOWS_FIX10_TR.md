# FIX10 — Windows EXE grafik başlatma / Uvicorn logging düzeltmesi

## Sorun
FIX9 native Windows EXE derlenmiş ve CLI `--smoke-server` testinden geçmişti,
ama masaüstünde **Start local simulator** tıklanınca:

`ValueError: Unable to configure formatter 'default'`

hatası oluştu. PyInstaller `--windowed` uygulamasında `sys.stdout` ve
`sys.stderr` geçersiz/None olabilir. Uvicorn varsayılan formatter'i
`sys.stdout.isatty()` kullanır; bu hatayı tetikleyebilir.

## FIX10
- Uvicorn yapılandırmasında `log_config=None` ile konsola bağımlı formatter devre dışı.
- Dönüşümlü günlük dosyası `%LOCALAPPDATA%\AutonomousPlantPlatform\logs\local_simulator.log`.
- Grafik EXE için eksik standart akışlar güvenli şekilde tamamlanır; Python traceback `%LOCALAPPDATA%\AutonomousPlantPlatform\logs\python_errors.log` içine yazılır.
- `--smoke-server`, GUI'nin gerçek `LocalServer.start()` işlevini **ephemeral localhost portunda** kullanır. Önceki ayrı iş yolu kaldırıldı.
- FIX10 EXE yeni `dist/AutonomousPlantSimulatorV20_FIX10/` klasöründe oluşturulur.

## Windows'ta kabul sırası
1. Eski FIX9 programını ve 8000 portundaki uygulamayı kapat.
2. Bu ZIP'i tamamen yeni klasöre çıkar; `.venv` ya da eski `dist` taşıma.
3. `02_YALNIZ_TEST.cmd` ile tüm testleri çalıştır.
4. `06_WINDOWS_TAM_EXE_DERLE.cmd` ile yeniden derle; `SUCCESS` sonucunu al.
5. FIX10 EXE'sini aç, **Start local simulator** ve HES/GES/RES canlı panellerini dene.
6. Sorun yaşanırsa `WINDOWS_EXE_DERLEME_RAPORU.txt` ile yukarıdaki günlükleri gönder.

### Sınır
Bu salt yerel, sentetik simülasyon aracıdır; gerçek PLC/SCADA kumandası değildir.
Üretici OEM doğrulaması, imza ve FAT/SAT yapılmış kabul edilmez.
