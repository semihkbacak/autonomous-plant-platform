# FIX11.1 — Windows yol uyumluluğu

Windows FIX11 testinde 1/720 hata: eksik SQL dosyasının raporlanan göreli yolu `simulator\solar\ges_history_schema.sql` olarak yazılmıştı. Test `/` bekliyordu. `desktop/full_simulator_launcher.py` içinde `.as_posix()` ile sadece hata mesajı normalleştirildi; gerçek paketleme/SQL bütünlük denetimi korunuyor.

`FIX11_1_ONAR.cmd` halihazırda yüklenmiş FIX11 klasöründe yama ve 5 hedef test için kullanılabilir. Mevcut `.venv` ve `dist` silinmez. Temiz ZIP zaten bu yamayı içerdiğinden tekrar uygulamak gerekli değildir.

**NOT:** PowerShell'e proje klasörünün dışından verilen `./simulator/solar/...` komutları çalışmaz. Kaynak ve hedef dosyaların doğruluğu için proje kökünde veya tam dosya yollarıyla işlem yapılır.

Sürüm hâlâ sentetik HES/GES/RES simülasyonu. Windows EXE'nin kendi bilgisayarındaki GUI testi ve lisans/alan doğrulamaları ayrıca gereklidir.
