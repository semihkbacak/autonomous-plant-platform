# Autonomous Plant Platform v1.5 — sürüm kalite raporu

**Kaynak:** Kullanıcının taşınabilir SSD arşivindeki FIX2 temiz proje kopyası. Windows ve Linux başlatma araçları ile GitHub çalışma akışları birleştirildi. Arşivde `.git`, `.venv`, `__pycache__`, SQLite ve kişisel telemetri yoktur.

## Uygulanan doğrulamalar

| Kontrol | Sonuç |
|---|---|
| Linux CPython 3.13 / tüm pytest | **662 passed** (25,41 s) |
| Test çalıştırıcısı | `--basetemp` için üst klasör oluşturularak tekrar koşuldu |
| Uyarılar | 2 `InconsistentVersionWarning`, yalnızca bu test ortamındaki scikit-learn 1.8.0 ile modelin 1.9.1 sürümü farkından; dağıtılan `requirements.txt` 1.9.1 sabitler |
| Test varlıkları | 5 zorunlu dosyanın SHA-256 özetleri doğrulandı |
| Git takip denetimi | Zorunlu 5 dosyanın `.gitignore` tarafından dışlanmadığı doğrulandı |
| Gerçek Windows kurulum | Kullanıcı, FIX2 üzerinden HES/GES/RES arayüzlerinin açıldığını bildirdi; birleşik GitHub kaynak paketi için yeniden test gerek |
| GitHub Actions CI | Paket oluşturulduğu anda çalıştırılmadı; push/PR sonrası doğrulanmalı |
| Gerçek saha/OT kullanımı | **Doğrulanmadı. Yasak / desteklenmiyor.** |

**Önemli:** Bu bir kaynak teslimatıdır; imzalı bir Windows çalıştırılabilir dosyası veya üretim sistemi değildir. `ges_oem_research.zip` içindeki araştırma/PDF/XLSX verileri kamuya yayımlanmadan önce telif/lisans kontrolünden geçirilmelidir.
