# v2.0 Engineering RC4 — Test özeti (2026-10-16)

- **Linux CPython 3.13.5:** `689 passed, 2 warnings in 31.00s`. Kaynak: tam pytest çıktısı `APP_RC4_full_regression.txt`.
- Yeni testler: HES/GES/RES replay ve duraklatılmış portföy geri yükleme, SQLite backup/restore, simülasyon parametresi kilidi, SBOM kaynak doğrulaması, Windows build GitHub Actions önkoşulları.
- Uyarılar: iki `InconsistentVersionWarning` (yerel test ortamı scikit-learn 1.8.0; eğitilmiş modeller 1.9.1). Paket bağımlılıkları 1.9.1'i sabitler; **Windows için yeni RC4 test sonucu yok**.
- Kod denetimleri: `desktop.full_simulator_launcher --self-test`: PASS; `scripts/security_preflight_v20.py`: PASS; `scripts/verify_release_assets.py`: 5/5 SHA-256 PASS.
- Online `pip-audit`: betik ve CI akışı hazır; çalıştırılmadı, güvenlik açıkları değerlendirilmedi.
- Windows EXE: GitHub native build + EXE self-test adımları yazıldı; **RC4 için derlenmedi**, imzalanmadı.
- HIL/FAT/SAT, üretici OEM kalibrasyon, üçüncü taraf lisanslar, sahadan izinli ölçüm: **yapılmadı ve üretime çıkış için açık kapı**.

**Aynı 689 test Windows ve GitHub Actions'ta çalıştırılmadan tamamlandı iddiasında bulunulamaz.**
