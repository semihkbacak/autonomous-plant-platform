# Autonomous Plant Platform — Aşama 1–5 Birleşik Araştırma Sürümü

**Durum:** çalışan **sentetik araştırma uygulaması**; gerçek saha/OEM için kabul verilmemiştir.

**Önceki korunmuş sürüm:** FIX11.1 + Aşama 1; yeni çalışma `advanced_v2/` modüllerindedir. Eski Aşama 1 ortak saat, günlüğü ve `/platform/synchronized` ekranı silinmemiştir. Yeni araştırma katmanı ayrı bir oturum ve veritabanı tutar. İki farklı ekranın aynı anda *tek fiziksel ikiz* olduğunu varsaymayın; aynı UTC birimleri kullanan iki **ayrı** araştırma deneyidir.

## Kurulum — Windows 11 / Python 3.13

1. ZIP dosyasını **Tümünü ayıkla** ile `C:\AutonomousPlant\Asama1_5` benzeri **yeni** klasöre çıkarın. ZIP içinden `.cmd` çalıştırmayın.
2. Önce `01_WINDOWS_KUR_TEST_VE_BASLAT.cmd` ile Python ortamını kurun. Kaynak kodu/bağımlılıkları İnternet gerektirebilir. Python konsolundaki `pytest` özetini kontrol edin.
3. Sonraki testlerde `10_WINDOWS_ASAMA2_5_TEST.cmd`; uygulamayı açmak için `11_WINDOWS_ASAMA2_5_AC.cmd` kullanın.
4. Masaüstü uygulamasında `Start local simulator` ve `Advanced physics + decisions` tuşlarını kullanın. Tarayıcı: `http://127.0.0.1:8000/platform/advanced-twins`.
5. `SIMULATION` modu (masaüstü uygulamasının yerel açılışı) dışında yeni oturum oluşturma ve adım ilerletme **engellenmiştir**. **SHADOW modunda salt okunur** kalır.
6. İmzalanmamış Windows EXE kaynağından `06_WINDOWS_TAM_EXE_DERLE.cmd` ile *yerel Windows üzerinde* oluşturulabilir. `dist/AutonomousPlantSimulatorV20_FIX11` ve `_internal` birlikte taşınmalıdır. Yeni paket **hazır derlenmiş veya imzalı EXE içermez**. Windows EXE ve gerçek GUI son kabul testi ayrıca yapılmalıdır.
7. Port 8000 başka programca kullanılmamalıdır. Sunucu yalnızca `127.0.0.1` üzerindedir. Ağ/OT erişimine açmayın.

**Yeni araştırma veritabanı:** `%LOCALAPPDATA%\AutonomousPlantPlatform\advanced\research.sqlite3`.

**Eski Aşama 1 veritabanı:** `%LOCALAPPDATA%\AutonomousPlantPlatform\stage1\synchronized.sqlite3`; üzerine yazılmaz.

Her oturum maksimum **31 gün**, her gün **96 × 15 dakika**. Durdurup yeniden açınca yalnızca **son tamamen yazılmış UTC dilimi** geri yüklenir ve otomatik yürütme durur. SHA-256 zinciri veri tutarsızlığını saptar ama kriptografik olarak imzalanmış değiştirilemez denetim kaydı değildir.

## Aşama 2 — GES

- `advanced_v2/physics.py: SolarPhysics, iv_curve`
- Üç seri, bypass diyotlu alt dizi × iki paralel string için **sentetik tek-diyot ailesi**; örnek I–V ve P–V noktaları.
- P&O, Incremental Conductance ve global tarama MPPT; gerilim komutuna sınırlı adımlarla yaklaşma.
- Hücre sıcaklığı tepkisi, inverter verim/klipleme, sıcaklık derating'i.
- `NONE/PARTIAL/HEAVY` gölge seçenekleri; `GRID_LOSS/INVERTER_TRIP/HOT_INVERTER/STRING_OPEN` sentetik arızaları.
- 1kW civarı örnek bloğun `pv_blocks=300` ile portföyde çoğaltılması gerçekte 300 aynı panelin bulunduğuna dair kanıt değildir.
- Referans: `pvlib.pvsystem.singlediode` ile aynı **beyan edilmiş sentetik** parametre setinde bağımsız matematik denetimi (`GET /api/v2/advanced/references`).

**Sınır:** Bypass modeli basitleştirilmiştir; gerçek string topolojisi, ışınım/hücre ölçümü, parametre fit'i, inverter grid-code ve koruma testleri yoktur.

## Aşama 3 — RES

- İki türbin; `Cp(lambda,beta)` proxy ve **16/27 Betz sınırı**, rotor atalet/şaft torku dengesi.
- Sınırlı pitch/yaw aktüatör hızı, deterministik sentetik türbülans, Jensen-türü wake azaltması.
- `PITCH_STUCK/YAW_STUCK/BRAKE/HIGH_WIND/GRID_LOSS` sentetik arıza seçenekleri.
- Rotor RPM, pitch/yaw, güç ve enerji hesaplanır.

**Sınır:** Bu bir OpenFAST/ROSCO çalıştırması değildir. Yapısal esneklik, blade element momentum, yorulma, OEM pitch sürücüsü/elektriksel koruma gerçeklenmemiştir. OpenFAST ve ROSCO ileride sayısal karşılaştırma için araştırma referanslarıdır.

## Aşama 4 — HES

- Akış/hedef yük için basitleştirilmiş governor PI, nozul sınırlaması, rotor hareket denklemi, jeneratör yükü, voltaj/frekans proxy.
- Rezervuar su dengesi, çevresel su bırakma ve basınç değişimi için **Joukowsky zarfı**.
- `NOZZLE_STUCK/LOAD_REJECTION/LOW_RESERVOIR/GRID_LOSS` sentetik arıza seçenekleri.

**Sınır:** Bu bir Method of Characteristics (MOC) hidrolik transient çözümü, elektriksel şebeke akışı, Pelton OEM hill-chart, gerçek governor tuning veya bağımsız emniyet sistemi değildir.

## Aşama 5 — Ortak karar destek

- Ortak UTC: her 900 saniyede üç santralin fizik modeli ilerletilir, sonuçlar ve durum JSON kontrol noktası **tek SQLite transaction** ile saklanır.
- Şebeke talebine karşı önce GES/RES, ardından HES kullanımı için **sentetik merit-order bilançosu**: servis, kısıntı, açığı ayrı hesaplar.
- Son 48 güç örneği ile median/MAD tabanlı **anomali sinyali**. Saha arızası teşhisi veya doğrulanmış ML modeli değildir.
- Son 4+ nokta için sönümlü eğilim **üretim tahmini**; bantlar yalnızca sezgiseldir, kalibre istatistiksel güven aralığı değildir.
- 1..96 adım için, çevresel su hakkı sonrası kullanılabilir sentetik su bütçesini kritik zaman dilimlerine tahsis eden **sınırlı doğrusal su bütçesi optimizasyonu**. Gerçek hidrolojik çok kısıtlı üretim optimizasyonu değildir.
- Aynı UTC ve aynı başlangıç konfigürasyonuyla 1–5 alternatif senaryo karşılaştırması.
- Yetkili olduğu ileri sürülen offline gözlem dizileri için **zaman sıralı %70 eğitim / %30 test** ve MAE, RMSE, signed bias. Kullanıcıdan gelen etiketlerin ve kaynağın sahiciliği teyit edilmez; `site_validated=false`.
- Betz, hidrolik ideal güç ve `pvlib` bağımsız matematik denetimleri; **gerçek saha performansı onaylamaz**.

## Yeni API ve arayüz

| API | Amaç |
| --- | --- |
| GET `/platform/advanced-twins` | Canlı sentetik araştırma paneli |
| GET `/api/v2/advanced/status` | Oturumun UTC, durum ve son sonuçları |
| GET `/api/v2/advanced/history` | Üç santralli zaman dilimleri |
| GET `/api/v2/advanced/export.csv` | Sentetik araştırma CSV |
| GET `/api/v2/advanced/runs` | Kayıtlı oturum listesi |
| GET `/api/v2/advanced/forecast` | Heuristik kısa vadeli üretim tahmini |
| GET `/api/v2/advanced/optimize` | Su bütçeli sentetik üretim planı |
| GET `/api/v2/advanced/references` | pvlib + analitik üst sınır kontrolleri |
| POST `/api/v2/advanced/create` | Yeni, kontrollü sentetik oturum |
| POST `/api/v2/advanced/step` | 1..96 zaman dilimi ilerlet |
| POST `/api/v2/advanced/start`, `/pause` | Otomatik yürütmeyi yönet |
| POST `/api/v2/advanced/compare` | What-if senaryo karşılaştırma |
| POST `/api/v2/advanced/holdout` | Kaynağı **doğrulanmamış** zaman sıralı ölçüm karşılaştırma |

Değiştirici istekler yalnızca yerel `SIMULATION` modunda `X-Synthetic-Confirm: SYNTHETIC_ONLY` başlığıyla kabul edilir. `REAL/PRODUCTION` gibi çalışma modları yoktur. Servis alan ağı veya saha üzerinden kullanmayın.

## Bağımsız araştırma kaynakları

- pvlib-python 0.16.1, single diode: https://pvlib-python.readthedocs.io/en/stable/user_guide/modeling_topics/singlediode.html
- OpenFAST — coupled aero-hydro-servo-elastic: https://openfast.readthedocs.io/en/main/
- NLR ROSCO reference controller: https://rosco.readthedocs.io/en/latest/
- NIST SP 800-82 Rev. 3 — OT security: https://csrc.nist.gov/pubs/sp/800/82/r3/final
- Önceki proje belgeleri: `docs/LITERATUR_TARAMASI_TR.md`, `docs/RELEASE_GATES_TR.md`, `docs/REAL_SITE_GATE_MAP_TR.md`.

## Tamamlanmamış bağımsız kabul koşulları

**Ürün/saha onaylı değildir:** OEM panel/inverter/türbin karakteristikleri, gerçek yetkili tesis veri kaynağı, uzun dönem holdout, gerçek şebeke kodu, hidro su darbesi MOC, OpenFAST/ROSCO karşılaştırmalı iş yükü, ISO/IEC/ISA OT güvenlik incelemesi, ayrı PLC/SIS, HIL/FAT/SAT ve gerçek Windows EXE GUI/kurulum imzalama testleri.

**Telif/lisans:** Depodaki OEM PDF/XLSX/ZIP araştırma dosyalarının yeniden dağıtım hakları ve yazılımın genel lisans kararı hâlâ hak sahibi tarafından değerlendirilmeli. Dosya adlarının veya hash’lerin mevcut olması dağıtım izni vermez.

### Test

`10_WINDOWS_ASAMA2_5_TEST.cmd`, `10_LINUX_ASAMA2_5_TEST.sh` veya `python -m pytest -q tests/test_stages_2_to_5_advanced.py`.

`python scripts/verify_stages_2_5.py` dosya, bağımsız matematik referansı, SQLite kayıt ve devam testlerini internet veya OT bağlantısı olmadan gerçekleştirir.
