# Autonomous Plant Platform — P02 Windows UTF-8 Uyumluluk Onarımı

**Tarih:** 17 Ekim 2026  
**Temel sürüm:** `AutonomousPlant_UTC_DISPATCH_P01_WINDOWS_LINUX_KAYNAK.zip`  
**Bu sürüm:** `UTC_DISPATCH_P02_WINDOWS_UTF8_FIX`, sentetik araştırma yazılımı; gerçek PLC/SCADA kontrolü veya OEM doğrulaması değildir.

## Windows P01 kabul bulgusu (kullanıcının çalıştırdığı testler)

- **Tam `02_YALNIZ_TEST.cmd`: `781 passed, 2 failed, 1 warning in 51.68s`**.
- İki başarısız test: `tests/test_stage1_three_plant_sync.py::test_builder_bundles_stage1_and_entrypoints` ve `tests/test_stages_2_to_5_advanced.py::test_python_windows_builder_and_gui_include_new_modules`.
- Her iki hata `app/main.py` dosyasını `Path.read_text()` ile Windows Türkçe ANSI **cp1254** altında okumaktan kaynaklanan `UnicodeDecodeError` idi. Bunlar HES/GES/RES fizik veya SQLite sonuç uyuşmazlığı değildir.
- Bağımsız hedefli P01 Windows kontrolünde **58 passed, 1 warning** (görüntüden raporlandığı kadarıyla).
- `import file mismatch` artık görülmemektedir (pytest yedek klasörü keşif izolasyonu çalışıyor).

## P02 uygulanmış düzeltmeler

1. Kaynak okuyan Stage 1 ve ileri aşama builder regresyonları açıkça `read_text(encoding='utf-8')` kullanıyor; diğer aynı örüntülü testler de normalize edildi.
2. `windows/windows_start.py` alt süreçte `PYTHONUTF8=1` ayarlıyor. `PYTHONIOENCODING` tek başına dosya okuma kodlamasını düzeltmediğinden her ikisi de tutuluyor.
3. `tests/test_windows_utf8_portability_p02.py`: cp1254 hatasını sentetik ve deterministik yeniden üretir; UTF-8 kaynak okuma, testlerde açık kodlama kullanılmasını ve Windows başlatıcı değişkenlerini doğrular.
4. Windows için `14_WINDOWS_P02_KODLAMA_TEST.cmd` eklenmiştir. Mevcut sanal ortamla çalışır, paketleri yeniden kurmaz.
5. Diğer testlerdeki birkaç kodlamasız metin yazma çağrısı da UTF-8'e sabitlenmiştir.
6. Simülasyon fiziği, üretim-dispatch formülü, koruma/izinler, SQLite şeması veya API sözleşmesi bu onarımda değiştirilmedi.

## Linux Python 3.13.5 doğrulaması

- Hedefli, kullanılabilir küme (cp1254 kodlama emülasyonu için ASCII locale ve `PYTHONUTF8=0` dahil): **67 passed, 3 skipped, 3 deselected**.
- Bağımlılığa erişilebilir geniş küme: **511 passed, 7 skipped, 8 deselected**, 4 uyarı (scikit-learn sürüm uyuşmazlığı ve websockets deprecation).
- `pvlib` kurulu olmadığı için 28 GES modülü ve 8 bağımlı test tam Linux doğrulamasına dahil edilemedi. Bunlar Windows P01 kabulünde geçmiştir, ama P02 için Windows tam test yeniden gerekir.
- Gerçek Windows P02 tam kabulü, EXE testi, GUI/fizik model validasyonu **henüz yapılmamıştır**. P02 için sayısal Windows test sonucu uydurulmamalıdır.

## Windows'ta yükleme ve çalıştırma

**Seçenek A (tercih):** Önceki P01 ZIP klasörünü olduğu gibi koruyun. `P02_SADECE_DUZELTME_DOSYALARI.zip` dosyasını P01 proje köküne *klasör yapısını koruyarak* çıkartın ve değiştirilecek dosyaları onaylayın. Var olan `.venv` klasörünü silmeyin; onarım için yeniden kurulum gerekmez. Alternatif: Tam P02 ZIP'ini yeni klasöre çıkarın.

1. `14_WINDOWS_P02_KODLAMA_TEST.cmd` — cp1254/UTF-8 ve doğrudan daha önce düşen 2 test.
2. `10_WINDOWS_ASAMA2_5_TEST.cmd` — **tam** regresyon ve advanced doğrulaması.
3. `09_WINDOWS_ASAMA1_KAYNAK_DOGRULA.cmd` — kaynak SHA-256 bütünlük kontrolü.
4. İsteğe bağlı `02_YALNIZ_TEST.cmd` — bağımlılık kurulumunu/yükseltmesini içeren tam başlangıç kabulü; sadece iki test için zorunlu değildir.
5. `WINDOWS_TEST_RAPORU.txt` ve test çıktısını gönderin. **Ancak Windows P02 `0 failed` sonrasında** yayın kararı değerlendirilebilir.

Not: `StarletteDeprecationWarning` ve `httpx2` uyarısı, bu iki karakter kodlaması hatasının kök nedeni değildir; bağımlılık/API geçişinin ayrı bir işidir.

## GitHub ve güvenlik

`semihkbacak/autonomous-plant-platform` deposunun `main` dalına ve herhangi bir remote dalına işlem yapılmadı. P01/P02 kaynakları Windows kabulü tamamlandıktan ve kullanıcı açıkça onay verdikten sonra geliştirme dalına taşınabilir. Bu araştırma platformu sentetiktir, şebeke/PLC/SCADA cihazına kumanda etmez.
