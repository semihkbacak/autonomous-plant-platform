# UTC Synthetic Dispatch P01 — kaynak değişiklik özeti

- Orijinal kullanıcının 17.10.2026 tarihli en güncel 339 girdili kaynak ZIP'inden geliştirilmiştir; eski taban ZIP korunmuştur.
- `pytest.ini`: yalnızca `tests/`, importlib, dış-yedekleme/test geçici dizinleri hariç.
- `windows/windows_start.py`: tam test çağrısı açıkça `tests/` klasörünü hedefler.
- `tools/audit_repair_backup.py`, `12_WINDOWS_GUVENLI_ONAR_YEDEGI.cmd`, `FIX11_1_ONAR.ps1`: kaynak tamiri yedekleri proje dışında SHA-256 ile.
- `stage1/dispatch.py`: yeni UTC üretim planı hesap ve fizik/ihracat zarfı.
- `stage1/engine.py`: eski native örnekler korunarak yalnızca dispatch etkinse sonradan kaynak sınırına kısma; HES fizik girdileri.
- `stage1/store.py`: SQLite `production_plans`, `dispatch_controls`, `dispatch_audit`, plan raporlaması, denetlenebilir rollback.
- `stage1/controller.py`: operatör setpoint/START/STOP/AUTO, plan, modlar, profil süreleri.
- `stage1/api.py`: tek panel HTML/JS, HTTP korumalı plan ve kontrol uçları, plan raporu ve CSV alanları.
- `tools/profile_stage1.py`: hesaplama vs SQLite süresi; `--toy-sessions` gerçeği yansıtmaz uyarısı.
- `tests/test_stage1_dispatch_schedule_p01.py`: Linux/Windows pytest keşfi, UTC, kaynak kapasiteleri, restart, audit, SQLite yazma hatası, HTTP, performans.
- `13_WINDOWS_DISPATCH_KABUL.cmd`: hedefli P01 kabul testi.
- `docs/UTC_DISPATCH_ENGINEERING_REVIEW_TR.md`: teknik mimari, denklemler, riskler.
- `WINDOWS_KABUL_VE_TEST_RAPORU_2026-10-17.md`: rapor, test sonuçları ve eksikler.
- `GIT_BRANCH_PREP_TR.md`: henüz GitHub'a aktarılmamış geliştirme dalı planı.

**Durum:** Gerçek PLC/SCADA, OEM onayı, HIL/FAT/SAT, Windows native GUI/EXE kabulü **YOK**. Windows tam QA gelmeden GitHub `main` değiştirilmemiştir.
