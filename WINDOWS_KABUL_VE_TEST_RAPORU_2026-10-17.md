# Autonomous Plant Platform — Linux İnceleme ve Windows Kabul Test Raporu

**Tarih:** 17.10.2026  
**İncelenen kaynak:** `Autonomous_Plant_ASAMA1_5_WINDOWS_AUDIT_FIX_KAYNAK(1).zip`; kıyas tabanı `Autonomous_Plant_Asama1_5_WINDOWS_DUZENLI_KURULUM (1)(1).zip`.  
**GitHub main:** farklı / daha eski v1.5 preview; `stage1/engine.py`, `stage1/controller.py` ve `advanced_v2/engine.py` main'de bulunamadı. Depoya hiçbir yazma uygulanmadı.  
**Kabul statüsü:** **KOŞULLU GELİŞTİRME — WINDOWS KABULÜ BEKLENİYOR**.

## Analiz sonucu

- Güncel ZIP: 339 girdi; eski ZIP: 337. Aralarında güncel `README_OEM_AUDIT_ONAR_TR.md`, `tests/test_windows_audit_missing_restore.py` ve değiştirilmiş `00_WINDOWS_BASLAT.cmd`, `windows/windows_start.py` dosyaları var.
- Yüklenen güncel ZIP'te eski `_WINDOWS_AUDIT_ONAR_YEDEK` bulunmuyor; kullanıcının Windows klasöründeki bu klasörün `test_*.py` tekrarları, rapora göre `import file mismatch` üretti.
- Linux'ta bilerek oluşturulmuş aynı dizin/test dosyası reprodüksiyonunda yedek testler de keşfedildi. `pytest.ini` + açık `tests` hedefleme sonrasında izole keşif testi, yedek dizinini dışarıda bırakarak geçti.
- Kaynak projeye **gerçek kod düzenlemesi** uygulandı: UTC plan, manuel setpoint, START/STOP/AUTO zarf, SQLite audit, fizik kaynak kilitleri, rapor, grafik, hız seçenekleri, performans profili, testler ve dış-yedekleme aracı.

## Çalıştırılan testler — Linux Python 3.13.5

| Test | Çıktı | Sonuç |
|---|---|---|
| `python -m pytest -q tests/test_stage1_three_plant_sync.py` | 13 passed, 2 skipped | GEÇTİ |
| `python -m pytest -q tests/test_stage1_dispatch_schedule_p01.py` (ilk tur) | 12 passed | GEÇTİ |
| Yeni API, fizik kilidi, audit ve saat eklemeleri sonrası Stage 1 + yeni + Aşama 2–5 | 55 passed, 3 skipped (final new rollback/legacy equivalence tests included) | GEÇTİ |
| Tam `python -m pytest -q` | 28 collection errors, **`pvlib` kurulu değil** | TAM REGRESYON YAPILAMADI |
| Yalnızca import hatalı 28 GES dosyası dışlanarak `pytest` | 505 passed, 7 skipped, 8 failed, 4 warnings | 8 başarısızın hepsi `ModuleNotFoundError: pvlib`; tam geçiş iddiası yok |
| Dependency-free selected suite, excluding 28 GES import modules and 10 test cases dependent on `pvlib` | 505 passed, 7 skipped, 10 deselected, 4 warnings | GEÇTİ — sınırlı seçilmiş küme |
| `python -m compileall -q app stage1 tools tests/test_stage1_dispatch_schedule_p01.py` | başarılı | GEÇTİ |
| Gerçek Windows `.cmd` / native GUI / `.exe` | Bu Linux ortamında çalıştırılmadı | DOĞRULANMADI |

`pvlib==0.16.1` kurulumu ağ erişimi olmadığı için sağlanamadı. Kullanıcının önceki Windows **761 passed, 1 warning** kanıtı önceki pakete aittir ve yeni paketin doğrulanması sayılmaz. Önceki sürümün GitHub `main` ile aynı olmadığı ayrıca not edilmelidir.

## Gerçek profilden örnek (sınırlı)

`python -m tools.profile_stage1 --toy-sessions --steps 8`:

- 8 ortak UTC slotu: yaklaşık **0.30001 s duvar**.
- HES native 900 tick ve GES/RES hafif sahte test oturumlarının compute/checkpoint toplamı **0.27813 s**.
- SQLite transaction **0.01854 s**.
- Ölçülen işlem CPU süresi **0.29004 s**.
- **0 s kasıtlı bekleme**, çünkü ölçüm otomatik döngüyü değil açık `advance()` çağrılarını kullanır; gerçek otomatik `NORMAL` modunda 2 saniyelik adım beklemesi ayrıca vardır.
- Tam GES/RES pvlib profili değildir; GPU/CUDA ihtiyacına karar verilmez.

## Kalıcı pytest çözümü

`pytest.ini` test kökünü `tests` olarak belirler; `--import-mode=importlib` ve `norecursedirs` yedekleri dışlar. Windows `windows/windows_start.py` doğrudan `tests` hedefini geçirir. `.gitignore` eski yedekleri de dışlar. `12_WINDOWS_GUVENLI_ONAR_YEDEGI.cmd` ve `FIX11_1_ONAR.ps1` kaynak onarım yedeğini proje dışındaki klasöre koyar; test klasörlerinin yedeklenmesi hiçbir zaman test keşfini etkilememelidir. Yedekleri silmek gerekli değildir.

## Kullanıcının Windows kabul adımları

1. ZIP'i aç: önerilen dizin `C:\AutonomousPlantDispatchP01` (kök projenin `pytest.ini` ve `tests/` içeriği olmalı).
2. Başlangıç için `01_WINDOWS_KUR_TEST_VE_BASLAT.cmd` veya sadece test için `02_YALNIZ_TEST.cmd` (Windows Python 3.13 ve internet gerektirir). Önceden kurulmuş sanal ortam varsa `10_WINDOWS_ASAMA2_5_TEST.cmd`.
3. PowerShell / CMD kökten: `.venv\Scripts\python.exe -m pytest -q --assert=plain --tb=short tests`.
4. Eski yedekli klasörde aynı komutu çalıştır; `test_stage1_three_plant_sync.py` ve `test_stages_2_to_5_advanced.py` çift keşfedilmemeli.
5. Kaynak `09_WINDOWS_ASAMA1_KAYNAK_DOGRULA.cmd` ve teknik kabul testleri geçmeli; `tests/test_stage1_dispatch_schedule_p01.py` ayrıca test edilmeli.
6. Yerel arayüz `http://127.0.0.1:8000/platform/synchronized` açılarak saatlik/günlük/15dk hedef, setpoint, fizik yetersizliği, grafik, üretim toplamları, yeniden başlatma ve hız seçenekleri manuel doğrulanmalı.
7. Test dosyasını `WINDOWS_TEST_RAPORU.txt` ve kullanılan Python/pvlib sürümleriyle birlikte paylaşırsan, yeni sürümün nihai kabul sonucunu karşılaştırabiliriz.

**GitHub:** Yazma ve yeni remote geliştirme dalı henüz oluşturulmadı. Önerilen dal `development/utc-dispatch-p01`. Windows kabulü ve açık kullanıcı onayı sonrası `main` korunarak dal açılıp değişiklikler aktarılmalıdır.
