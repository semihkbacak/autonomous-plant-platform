# Autonomous Plant Platform v1.5.0-rc.1 — aday sürüm kabul kaydı

**Tarih:** 17 Ekim 2026  
**Dağıtım:** P04 kaynak + RC1 dokümanları/GitHub aktarım aracı. Bu aday fizik motorlarını veya SQLite şemasını değiştirmiyor.  
**Mod:** Sadece yerel/sentetik simülasyon.

## Kaynak tabanı ve uzak depo

- Hedef: `semihkbacak/autonomous-plant-platform`; mevcut `main` ve `release/v1.5-preview-20261015` dalları okundu.
- `main` üzerinde `stage1/controller.py`, `advanced_v2/api.py`, `START_HERE_WINDOWS.cmd` henüz bulunmuyordu; RC1 kaynakta bunlar mevcut. GitHub README'si önceki v1.5 preview durumunu gösteriyordu.
- Yayın hazırlığı için gözlenen `main` tepe commit'i: `83e86742d6f0008844d1386493d2c64b89ece032`. Otomatik aktarım, main farklıysa **işlemi durdurur**.
- `main` bu teslimde değiştirilmedi; `release/v1.5-rc1` uzak dalı ve `v1.5.0-rc.1` tag/release henüz oluşturulmadı.

## Testler

- RC1 kaynak üzerinde Linux Python 3.13 hedefli pytest: **70 passed, 3 skipped, 0 failed**. Kapsam: P04 UI/API testi, UTC dispatch/schedule, kaynak/Windows başlatıcı kontrolleri, Stage 1 ve Stages 2–5, UTF-8 taşınabilirlik testleri.
- RC1 `scripts/verify_release_assets.py`: **5 temel fixture dosyası SHA-256 doğrulandı**.
- RC1 kaynak SHA-256 manifesti: dosya bazında tüm kaynakların bütünlüğü kontrol edildi.
- GitHub aktarım aracı: **yerel bare Git sunucusu** ile önizleme, yalnız RC dalına push, main'in değişmemesi, eski tracked dosyaların temizlenmesi ve çift yayın reddi kontrol edildi; BAŞARILI.
- P04 geçmiş Linux geniş test raporu: **522 passed, 7 skipped, 8 deselected, 4 warnings**. Ek 28 pvlib bağımlı modül ortamda toplanamadı. Bu RC1'de tam 783 Windows regresyonunun çalıştırıldığı anlamına gelmez.
- Daha önceki P01 kullanıcı Windows ekranı: 781 passed / 2 cp1254 failed; bu hata P02/P03 kaynakta düzeltildi. P04 RC1 tam Windows terminal/GUI/EXE kabulü mevcut kanıtla **henüz doğrulanmış değil**.

## GitHub RC yayını için kapılar

1. `RC1_GITHUB_ONIZLE.cmd` ile dosya değişiklik özetini gör; `RC1_GITHUBA_GONDER.cmd` ile sadece `release/v1.5-rc1` dalına gönder.
2. GitHub Actions Windows ve Ubuntu regresyonlarının her ikisinin başarılı olmasını bekle. Stage 1–5 workflow'unu PR üzerinden çalıştır.
3. Windows'ta `P04_KABUL_TEST_WINDOWS.cmd` ve gerçek panel tıklamalarını kontrol et (`UTC_DISPATCH_P04` sürüm işareti beklenir).
4. `LICENSE_DECISION_REQUIRED.md` ve OEM araştırma ZIP'indeki materyallerin dağıtım izinlerini değerlendir.
5. Yalnızca bunlardan sonra `v1.5.0-rc.1` GitHub Releases **pre-release** oluştur; saha, OEM veya üretim onayı iddia etme.

## Bilinen sınırlar

Manuel setpoint sentetik kullanılabilir güç limitine göre çıkış kontrolüdür; tam hidrolik/elektromekanik kapalı çevrim governor ve OEM kalibrasyonu değildir. Native Windows EXE veya PLC/SCADA kontrolü burada test edilmemiştir.
