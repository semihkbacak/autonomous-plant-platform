# Autonomous Plant Platform v1.5 — Windows 3.13 tam kaynak paketi (FIX2)

**Kaynak:** 15 Ekim 2026 tarihli `windowsproje.zip` — taşınabilir SSD/Linux proje ağacı. Kodlar temel olarak oradan birebir alındı. Windows kurulumu için yeni başlatıcı eklenmiştir.

## Tek işlemle başlatma

1. ZIP'i `C:\Users\...\Desktop` gibi bir yere **Tümü ayıkla** ile aç. Bir üst dizin içinde bu dosyaları göreceksin.
2. Windows'ta **Python 3.13** yüklü olmalı (`py -3.13 --version`). İnternet, ilk `pip install` işlemi için gerekli.
3. `01_WINDOWS_KUR_TEST_VE_BASLAT.cmd` dosyasına çift tıkla. Yönetici olarak açmana gerek yok.
4. Başlatıcı, Windows'a uygun `.venv` oluşturur, paketleri kurar, orijinal veri dosyalarının SHA256 özetlerini doğrular, tüm testleri çalıştırır; başarılıysa yerel HES + GES + RES sunucusunu ve masaüstü izleyicisini açar.
5. Panel: http://127.0.0.1:8000/platform/dashboard
6. Yerel simülasyonu durdurmak için açılan **sunucu konsolunda Ctrl+C** yap.

## Hızlı seçenekler

- `02_YALNIZ_TEST.cmd`: bağımlılık kurulumu / onarımı + tam test, sunucu başlatmaz.
- `03_TESTSIZ_BASLAT.cmd`: bağımlılık kuruluysa daha hızlı başlatır; testleri atlar.
- `04_WINDOWS_VIEWER_EXE_OLUSTUR.cmd`: Windows'ta PyInstaller ile **salt-okunur** izleyici EXE oluşturur. Windows_EXE/AutonomousPlantViewer.exe. Bu EXE sunucu DEĞİLDİR, imzasızdır ve antivirüs uyarısı verebilir. Ana başlatıcı zaten GUI'yi Python/Tkinter ile açar; EXE şart değildir.

## SSD'den `.venv` kopyalanması hatası

Eğer önceden Linux `.venv` yanlışlıkla Windows'a kopyalanmışsa `'did not find executable at /usr/bin/python.exe'` hatası çıkabilir. Windows başlatıcısı sanal ortamın Python 3.13 Windows yorumlayıcısı olup olmadığını kontrol eder; değilse `.venv_linux_backup_YYYYMMDD_HHMMSS` olarak **yedekler** ve yeni bir sanal ortam oluşturur. Eski Linux `.venv` ZIP'e DAHİL DEĞİLDİR.

## Neler bulunur / bulunmaz

**Bulunur:** HES/GES/RES Python kaynakları, testler, `data/solar` altındaki orijinal sentetik test CSV'leri, yerel OEM araştırma ZIP'i, OEM testleri için gereken küçük audit JSON, orijinal demo HES anomali modeli, dokümantasyon ve Windows başlatıcı.

**Bulunmaz:** Linux `.venv`, `.git` geçmişi, boyutlu geçmiş simülasyon çıktıları ve SQLite historian veritabanları, eski yedekler. Historian sayfaları yeni kurulumda boş görünebilir; bu arıza değildir. Bu paket GitHub'a otomatik push yapmaz.

## Bilinen sınırlamalar / güvenlik

- **Sadece sentetik simülasyon ve SHADOW araştırması. Gerçek PLC / SCADA / OT ekipmanı kontrolü yok.** `127.0.0.1:8000` dışına açmayın.
- İlk kurulumun başarısı Windows güvenlik politikası, Python sürümü, pip bağlantısı ve bağımlılık sürümlerine bağlıdır. Tamamının Windows'ta doğrulandığı iddia edilmiyor.
- `.joblib` dosyaları serileştirilmiş Python nesneleridir. Yalnızca güvenilir kullanıcı kaynaklarından gelen bu projeyi açın.
- Windows Defender'ı bu paket için kapatmak gerekmez ve önerilmez. Kod bütünlüğü ilkesi tekrar dosya engellerse olay kayıtlarını inceleyin.
- Yeni bir GitHub klonunda aynı eksikler çıkabilir: bu ZIP kullanıcıdan gelen SSD kopyasıyla bütünlenmiştir, GitHub dalına bir commit yapılmamıştır.

## Kaynak paketinde düzeltilen çelişki

`.github/workflows/windows-viewer-preview.yml` dosyasının orijinalinde `push:` tetikleyicisi vardı, fakat `tests/test_release_tooling_v15.py` iş akışının **yalnızca elle `workflow_dispatch`** ile çalışmasını bekliyordu. Windows paketinde iş akışı testiyle tutarlı olacak şekilde `push` tetikleyicisi kaldırılmıştır. GitHub deposu değiştirilmemiştir.

## Model surumu

SSD kaynakli `models/hes_anomaly_iforest.joblib`, scikit-learn **1.9.1** ile olusturulmus. Windows kurulumunda `requirements-windows.txt` bu surumu sabitler. Baska bir scikit-learn surumunde modelin `joblib.load` ile geri yuklenmesi uyumluluk uyarisi verebilir.

## Windows'ta WinError 5 / pytest-of-SEMİH düzeltmesi (FIX2)

Bir önceki Windows paketinde bazı bilgisayarlarda `pytest` geçici dosyalarını
`%LOCALAPPDATA%\Temp\pytest-of-KULLANICI` içine açarken
`PermissionError [WinError 5]` verdi. Kullanıcının paylaştığı çıktıda
**525 test geçti, kalan 137 test aynı geçici dizin izni hatasıyla başlayamadı.**
Bu hata geçici dizin erişimi sırasında oluşuyor; gerçek test assertion başarısızlığı değil.

FIX2 Windows başlatıcısı testleri **proje içindeki `.windows_test_tmp`** dizininde
yalıtılmış ve her koşuda ayrı `--basetemp` ile çalıştırır. `TEMP/TMP/TMPDIR`
yalnızca `pytest` alt işlemi için değişir; Windows genel ayarları değiştirilmez.
Tam çıktı otomatik `WINDOWS_TEST_RAPORU.txt` içine yazılır.

Bir önceki paketle **aynı klasöre birleştirmeden**, yeni klasöre ayıklayın.
`01_WINDOWS_KUR_TEST_VE_BASLAT.cmd` veya sadece test için `02_YALNIZ_TEST.cmd`
çalıştırın; mümkünse yönetici (Administrator) olarak açmayın.
Herhangi bir test tekrar hata verirse `WINDOWS_TEST_RAPORU.txt` dosyasını paylaşın.
FIX2'de Windows üzerinde 662 testin geçtiği henüz bizzat doğrulanmamıştır.
