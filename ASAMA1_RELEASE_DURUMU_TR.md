# Aşama 1 — teslim ve kabul durumu

- **Sürüm:** Autonomous Plant Platform v2.0 · Aşama 1 UTC Sync Research Build
- **Model kapsamı:** Mevcut HES/GES/RES sentetik simülatörleri. Kapsama gerçek saha bağlamak veya otomatik gerçek santral kumandası **dahil değildir**.
- **Senkronizasyon:** HES 900 × 1 s native tick; GES/RES 1 × 900 s native interval; tek UTC başlangıç/bitiş, 1–31 gün.
- **Geri yükleme:** Her üç motorun aynı SQLite transaction'ında checkpoint + örnek kayıt; başlangıçta doğrulanmış son tam adım. Kaza sonrası `PAUSED_RECOVERED`, normal sunucu kapanışında `PAUSED`.
- **Kayıt:** SQLite, per-step SHA-256 journal hash zinciri, önceki oturumlar, CSV, tutarlı SQLite backup helper.
- **Açık alanlar:** Gerçek OEM/ölçümle kalibrasyon, gerçek OT güvenliği, saha sertifikasyonu ve imzalı kurumsal EXE. Bu aşamanın fonksiyonel gereği değildir.
- **Windows GUI:** Python başlatıcı + PyInstaller derleme betiğine entegre. **Bu yürütme ortamında native Windows GUI ve EXE yeniden derlenemedi**; kullanıcı bilgisayarında test edilmelidir.
- **Test uyarıları:** Bu çalışmadaki scikit-learn 1.8.0 kayıtlı 1.9.1 modeliyle farklı; son kullanıcı Windows `requirements.txt` 1.9.1 sabitler. Uvicorn/websockets deprecation uyarıları ayrı, başarısız test değildir.
- **Sürüm kontrolü:** GitHub `main` dalı bu teslim sırasında değiştirilmedi; paket ayrı geliştirme/test için kullanılmalıdır.

Açıklamalar: `ASAMA1_KULLANIM_VE_DOGRULAMA_TR.md`. Veri kaynağı `SYNTHETIC_THREE_PLANT_NO_OT`.
