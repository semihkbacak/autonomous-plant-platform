# Autonomous Plant Platform v2.0 — Windows FIX7

## FIX6 Windows günlüklerinde doğrulanan dört hata

- `WinError 32` (GES/RES): `sqlite3.connect` dönüşü `with` ifadesi SQL transaction'ı kapatır ama bağlantıyı **kapatmaz**. SQLite `mode=ro` kontrolünü `contextlib.closing` ile değiştirerek dosya tanıtıcılarının `os.replace` öncesi kapatılmasını sağladık. SQLite bağlantılarının açık kalmasını POSIX üzerinde de yakalayan regresyon testi eklendi.
- `desktop/full_simulator_launcher.py` içindeki rotalara ilişkin kırılgan `assert`: router yapıcılarını kendi izole FastAPI örneğinde kontrol ediyoruz. Asıl entegre uygulama için `--smoke-server` gerçek HTTP üzerinden GES, RES ve canlı ikiz uç noktalarını sınar.
- Eski EXE ile karışmayı önlemek için yeni çıktı ismi `AutonomousPlantSimulatorV20_FIX7.exe`.
- `06_WINDOWS_TAM_EXE_DERLE.cmd` derlemeden önce **tüm Windows regresyon testlerini** koşturur. Başarısız test varsa EXE üretilmiş gibi raporlamaz.

## Çalıştırma

1. FIX6'yı veya önceki EXE'yi kapatın. ZIP dosyasını **Tümünü Ayıkla** ile yeni bir klasöre çıkarın. Eski klasörün üzerine kopyalamayın.
2. Önce `02_YALNIZ_TEST.cmd` dosyasını çalıştırın. **706 passed** görmeyi bekliyoruz. Windows testi henüz bu ortamda koşturulmadı.
3. Test geçerse `06_WINDOWS_TAM_EXE_DERLE.cmd` dosyasını çalıştırın. Pencere kapanmayacak; log: `WINDOWS_EXE_DERLEME_RAPORU.txt`.
4. Başarılı derlemede uygulama `dist\AutonomousPlantSimulatorV20_FIX7\AutonomousPlantSimulatorV20_FIX7.exe` yolunda oluşur; `_internal` klasörü birlikte tutulmalıdır.
5. EXE'yi açıp **Start local simulator** ve **GES / RES live twins** üzerinden tarayıcı/sunucu bağlantısını kontrol edin.

Bu yazılım yalnızca sentetik yerel simülasyon içindir; gerçek PLC/SCADA kumandasına bağlanmaz. Her iki işletim sisteminde kaynak testlerinin başarılı olması OEM kalibrasyonu veya işletme güvenlik sertifikası değildir.

**Not:** Linux'ta kaynak regresyonu: 706 passed. Native Windows EXE dağıtımı, gerçek Windows doğrulaması tamamlanana kadar önizleme niteliğindedir.
