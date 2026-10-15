# Autonomous Plant Platform v1.4 — Literatür taraması ve teknik uyarlama

**Tarih:** 15 Ekim 2026. **Durum:** bağımsız bilimsel ön inceleme; standart uygunluğu veya OEM/saha kabul belgesi değildir.

Bu özet, Google Akademik'te başlık/DOI ile bulunabilen hakemli çalışmalar ile NREL/NLR, Sandia, IEC, ISA ve NIST'in kamuya açık *tanıtım/dokümantasyon* sayfalarını esas alır. Akademik indekslenme veya bir standart sayfasının bulunması, içeriğinin tamamına lisanslı erişim ya da modelin o standarda uyduğu anlamına gelmez. Telifli IEC standartlarının tam metinleri pakete kopyalanmadı.

## GES

1. **De Soto, Klein, Beckman (2006)**, *Improvement and validation of a model for photovoltaic array performance*, Solar Energy 80(1), 78–88. DOI: https://doi.org/10.1016/j.solener.2005.06.010. Beş-parametreli I–V modelinin üretici katalog verisi, ışınım, sıcaklık ve ölçümlerle doğrulanması. **Bizde:** `core/v14_pv_desoto.py`; üretici parametreleri **zorunlu girdi**, varsayılanları yok. Kayıtlı parametrelerin doğruluğunu test etmek için saha veri karşılaştırması gerekir.
2. **pvlib python, Single diode models**: https://pvlib-python.readthedocs.io/en/latest/reference/pv_modeling/sdm.html. CEC, PVsyst, De Soto ve I–V çözümlerinin uygulama arayüzleri. **Bizde:** yeni modül bağımlılığı mevcut `pvlib` üzerinden kullanır, koruma sistemi değildir.
3. **Sandia PVPMC**: https://pvpmc.sandia.gov/. Açık performans modelleme/karşılaştırma yaklaşımı. **Bizde:** kronolojik holdout kalite analizi ve veri-kaynak kaydı.
4. **NLR SAM PV model doğrulama**: https://sam.nlr.gov/photovoltaic/pv-validation.html. Model-kör karşılaştırma ve bağımsız veri gereksinimi.

**Açık teknik işler:** Onaylı panel ve inverter datasheet/seri eşleme; iki ışınım seviyesinde I–V; gölgelenme/bypass diyot topolojisi, sıcaklığa bağlı inverter verimi; ölçülmüş DC/AC verim-kısıntı; IEC 62109/61727 vb. ilgili ekipman/şebeke standardı uyumunun yetkili incelemesi. GES güç referansı ve şebeke bağlantı komutları hâlâ gerçek ekipmana kapalı.

## HES

5. **IEC 60041:1991**, *Field acceptance tests to determine the hydraulic performance of hydraulic turbines...*: https://webstore.iec.ch/en/publication/154. Saha performans kabulüne ilişkin ölçüm ve raporlama konularını tanımlar. Bu dokümanın tam metni ücretli olabilir; sertifikasyon yapılmadı.
6. **A. Bergant (2025)**, *Issues Related to Water Hammer in Francis-Turbine Hydropower Schemes*, Energies 18(24), 6404: https://www.mdpi.com/1996-1073/18/24/6404. Francis türbini ağırlıklıdır; mevcut HES Pelton modeli için doğrudan onay anlamına gelmez.
7. **A. El-Turki**, *Modeling of Hydraulic Transients in Closed Conduits*: https://mountainscholar.org/bitstreams/b0531d37-d9ed-4991-a364-d1afb89384c9/download. Su darbesi ve basınç dalgası dinamiğinde boru/esneklik/sınır koşullarının önemini gösterir.

**Açık teknik işler:** Pelton türbiniye özgü gerçek verim eğrileri, cebri boru elastikiyeti/geometrisi, MOC veya eşdeğer geçici rejim modeli, ölçülen debi-basınç-rotor hızı, bağımsız governor ve aşırı hız koruması, HIL/FAT/SAT.

## RES

8. **OpenFAST**: https://openfast.readthedocs.io/. Bağlı aerodinamik, servo, mekanik ve yapı dinamiğini kapsamlı çözen araştırma platformu. v1.3'teki aktüatör proxy'sinin yerini otomatik olarak almaz.
9. **ROSCO**: https://rosco.readthedocs.io/en/latest/. Referans kontrolör, pitch/yaw ve arıza çalışmaları.
10. **IEC 61400-12-1:2022**: https://webstore.iec.ch/en/publication/68499. Türbin güç performansının ölçümü. Ölçüm protokolüne uyum için veri kalitesi ve uzman denetimi gereklidir.
11. **Saint-Drenan vd. (2019)**, *A parametric model for wind turbine power curves incorporating environmental conditions*: https://arxiv.org/abs/1909.13780. Ortam duyarlı güç eğrisi modellemesi; OEM özel eğri yerine geçmez.
12. **Liu vd. (2023)**, *Wind turbine anomaly detection based on SCADA: A deep autoencoder enhanced by fault instances*, DOI https://doi.org/10.1016/j.isatra.2023.03.045. Gerçek etiketli saha verisi ve bağımsız metrik ihtiyacı.

**Açık işler:** OEM türbin gücü ve yük eğrileri, pitch/yaw motor/encoder arızaları ve gerçek stop-state sekansları, yapısal yorgunluk/aeroelastik doğrulama, türbülans ve wake sahası, bağımsız koruma ve saha kalibrasyonu.

## Elektrik, OT güvenliği, gerçek kontrol

13. **NIST SP 800-82 Rev. 3**, 2023: https://csrc.nist.gov/pubs/sp/800/82/r3/final. OT güvenlik modelini fiziksel güvenilirlik ve güvenlikle birlikte ele alır. 2026 itibarıyla revizyon 4 için kamuya açık ilk taslak süreci bulunmaktadır.
14. **ISA/IEC 62443 serisi**: https://www.isa.org/standards-and-publications/isa-standards/isa-iec-62443-series-of-standards. Yaşam döngüsü/tedarikçi-sistem riskleri; ağ zonları/iletişim kanalları.
15. **IEC 61850-5**: https://webstore.iec.ch/en/publication/6012. Utility IED iletişim gereksinimleri.
16. **IEC 62351 serisi**: https://webstore.iec.ch/en/publication/6912. Güç sistemleri veri ve haberleşme güvenliği.

**Ürüne geçiş engelleri:** OEM/tag sözleşmesi, protokol ve OT segmentasyonu, izole salt-okunur pilot, kimlik + MFA + RBAC + audit, bağımsız PLC/safety relays, yerel override, HIL, FAT, SAT, yetkili onay; siber güvenlik testi, bakım ve müdahale sorumluluğu; ticari/sigorta ve yerel düzenleyici koşullar.

## Bu sürümün matematiksel katkısı ve sınırı

`tools/v14_validate_csv.py` her ekipmanın **tarihsel erken %75 verisiyle** tek katsayılı (0.5…1.5) hata düzeltme çarpanı tahmin eder; **geç sonraki %25 verisini** hiç eğitime almadan test eder. MAE, RMSE, signed bias ve ortalama gerçek güçle normalize edilmiş MAE/bias verir. %15 ve %10 kontrol eşikleri *projenin kendi araştırma eşikleridir, IEC/NREL onay limitleri değildir*. İşlem gerçek tesise hiçbir komut göndermez. Kaynak etiketlerinin veya SHA256'nın varlığı saha verisinin doğru/otantik olduğunu ispatlamaz.

Bu modül sonuçlarına göre **`site_validated=false`**, **`real_control_ready=false`** sabit tutulur. Gerçek tesis kabulü ancak harici yetkili kuruluş tarafından yapılabilir.

## Google Akademik arama girişleri

- https://scholar.google.com/scholar?q=De+Soto+Klein+Beckman+2006+photovoltaic+array+performance
- https://scholar.google.com/scholar?q=water+hammer+hydropower+transient+method+of+characteristics
- https://scholar.google.com/scholar?q=wind+turbine+pitch+yaw+actuator+fault+OpenFAST+ROSCO
- https://scholar.google.com/scholar?q=wind+turbine+SCADA+anomaly+detection+independent+validation

## Öncelikli gerçek veri talep listesi

- `HES`: türbin/alternatör OEM modeli, cebri boru/rezervuar şeması, basınç-hız-debi seri kayıtları, koruma işlev listesi.
- `GES`: panel datasheet ve seri, inverter MPPT parametreleri, string topolojisi, güneş/panel sıcaklığı/DC/AC 15 dakika kayıtları.
- `RES`: türbin güç/yük eğrileri, hub-height rüzgâr, pitch/yaw/rotor hızı/jeneratör gücü ve arıza olayları.
- `Tümü`: ham verinin kaynağı ve kalibrasyon belgeleri, zaman senkronizasyonu, yetkili saha mühendisi, FAT/SAT/HIL sonuçları.
