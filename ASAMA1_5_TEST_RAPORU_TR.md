# Autonomous Plant Platform — Aşama 1–5 Test Teslim Raporu

Tarih: 16 Ekim 2026. **Yalnızca sentetik araştırma uygulaması.**

## Kaynak ve regresyon

- Kaynak: Önceki Aşama 1/FIX11.1 projesinin tüm Windows/Linux kaynakları ve yeni `advanced_v2/` modülleri.
- Tam Linux regresyonu: **761 passed, 0 failed, 0 skipped, 4 warnings**, Python **3.13.5**, **37,36 saniye**, **pytest dönüş kodu 0**.
- Yeni Aşama 2–5 hedef testleri: **26 passed**; PV I–V/MPPT, RES aerodinamiği ve dinamiği, HES rezervuar/governor, su bütçesi optimizasyonu, SQLite kesinti ve bozulma testleri, API güvenliği, kronolojik holdout ve bağımsız `pvlib` hesaplaması.
- Zorunlu araştırma/örnek dosyaları: `python scripts/verify_release_assets.py` ile **5/5 SHA-256 OK**.
- İzole preflight: `python scripts/verify_stages_2_5.py` **PASS**; ayrı kontrol noktası oluşturulup 4. adımda kapandı, 5. adımda sorunsuz devam etti.
- Tam uygulamada canlı HTTP kontrolü: `/api/v2/advanced/status`, `/api/v2/advanced/references`, `/api/v2/clock/status`, `/platform/advanced-twins`, ve yeni oturum/iki adım başarılı.
- Referans: **aynı sentetik tek-diyot parametreleri** için pvlib `singlediode` 996,607 W; kurum içi ayrık I–V hesaplaması 995,775 W; **%0,08352** fark. OEM ölçüm doğrulaması anlamına gelmez.
- Windows EXE / GUI bu yeni paket için **henüz yerel Windows üzerinde sınanmadı**. Eski FIX11'in Windows'ta açılması, yeni modüllerin bütün Windows platformlarında kabulü değildir.

## 4 beklenen uyarı

- scikit-learn 1.9.1 modelini Linux test makinesindeki 1.8.0 ile açmaktan doğan iki `InconsistentVersionWarning`. Windows requirements.txt'de 1.9.1 sabitlenmiştir.
- Eski websockets/uvicorn `DeprecationWarning` iki adet.
- Bunlar mevcut regresyonda hata değildir ancak bağımlılık yükseltmesi/yeniden eğitim ve ayrı uyumluluk testleri sonra yapılmalıdır.

## Doğrulama kısıtları

- Tüm meteoroloji/elektrik/su girişleri sentetik; `site_validated=false`, `physical_control=false`.
- Wind referans testi yalnızca Betz üst sınırı ve açık katsayılı `Cp` proxy; OpenFAST/ROSCO bağımsız hesapları çalıştırılmadı.
- HES referans testi ideal `rho*g*Q*H` güç tavanı; MOC transient veya jeneratörün gerçek şebeke modeli sınanmadı.
- Anomali algılama MAD araştırma metriği, ölçümle eğitilmiş saha ML modeli değil.
- Hidro optimizasyonu tek su bütçesi ve kapasite sınırı içerir; gecikme, çoklu rezervuar veya gerçek şebeke kısıtları yer almaz.
- Gerçek OT, PLC, SIS/HIL/FAT/SAT, OEM mühendisliği, lisans/yayıncı imzası ve saha kabulü tamamlanmadı.

## Windows yerel kabul

1. ZIP tümünü çıkar, `01_WINDOWS_KUR_TEST_VE_BASLAT.cmd` ile `.venv` hazırla.
2. `10_WINDOWS_ASAMA2_5_TEST.cmd` ile tüm regresyon + bağımsız referans/SQLite preflight.
3. `11_WINDOWS_ASAMA2_5_AC.cmd` ile uygulamayı başlat.
4. **Advanced physics + decisions** tıkla ve `/platform/advanced-twins` sayfasında yeni oturum oluşturup 1 gün ilerlet.
5. GUI kapat/yeniden başlat: oturumun son UTC adımından **PAUSED_RECOVERED** olarak döndüğünü kontrol et.
6. `06_WINDOWS_TAM_EXE_DERLE.cmd` ile isteğe bağlı native onedir EXE oluştur. Başarılı `--self-test` ve `--smoke-server` çıktısını sakla. EXE `_internal` klasöründen ayrılmamalı.
7. Hata olursa `WINDOWS_TEST_RAPORU.txt`, `WINDOWS_EXE_DERLEME_RAPORU.txt` ve `%LOCALAPPDATA%\AutonomousPlantPlatform\logs\local_simulator.log` dosyalarını paylaş; kişisel token/şifreleri paylaşma.
