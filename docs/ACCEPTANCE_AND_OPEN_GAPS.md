# Açık konular ve saha geçişinde kabul kapıları

**Sürüm:** 1.1 research/engineering hardening. **Kurumsal/OT sertifikası değildir.**

## Şimdi eklendi / kontrol edilen

1. **Yazılım veri kalitesi:** NaN/Inf/negatif ölçüm, tekrarlanan ünite kimliği, tutarsız ünite-toplam güç, latching model hatası. Simülatör çıktılarında uygulanır.
2. **Hata enjeksiyonları:** 14 adet QA örneği, fiziksel ark-su darbesi-pitch arızası değildir.
3. **Portföy zaman hizası:** Aynı açık UTC 15 dakika aralığı ölçümleri *sentetik veri* olarak verilirse ortak enerji hesabı. Farklı günlerdeki kayıtları reddeder.
4. **Gösterge ve kapsam:** `/platform/engineering`, JSON açık eksik kaydı.
5. **Kumanda gözlemi:** HTTP POST girişim kaydı SQLite (opt-in profil için ek gate). Başarılı HTTP yanıtı ekipman komut uygulandı demek değildir.
6. **Offline shadow araştırma karşılaştırması:** Kullanıcı tarafından sağlanan CSV üzerinde MAE, RMSE, bias; veri kökeni doğrulanmamış kabul edilir.

## GES geriye kalanlar

- Üretici onaylı inverter/DC panel çalışma eğrileri, De Soto/diğer model parametre kalibrasyonu, tam MPPT sıcaklık/Voc/İsc çalışma alanı; karantinadaki katalog parametreleri.
- Bypass diyotlu ve paralel stringli gölgelenmede fiziksel I–V eğrisi/global MPP; spot testleri.
- Gerilim/frekans grid-code, anti-islanding, DC izolasyon, ark, topraklama ve inverter termal korumasının gerçek ekipman/yetkili mühendislik doğrulaması.
- Bakım sonrası tekrar devreye alma ve haberleşme kesintisi testleri, gerçekte ölçülen veri karşılaştırması, uncertainty ve drift.

## HES geriye kalanlar

- Kalibre edilmiş net düşü/debi/türbin hill chart; rezervuar/inflow/çevresel debi kuralları.
- Su darbesi/cebri boru geçişleri, ani yük atma/aşırı hız, wicket/gate/nozzle transient modelleri; uygun hidrolik doğrulama ve HIL.
- Şebeke senkronizasyonu, koruma röleleri, saha interlock/mekanik durum sınamaları.

## RES geriye kalanlar

- Kalibre edilmiş OEM power curve ve wake/CFD saha deneyi.
- Pitch/yaw aktüatör ve sensör hata dinamiği, yapısal aeroelastik ve yorulma, buzlanma.
- Elektrik şebeke kodu, fren/yeniden devreye alma, fail-safe haberleşme sınamaları.

## Ortak otomasyon (kesinlikle sonraki aşama)

- Yetkili kurum/tesisle gereksinim analizi, HAZOP/FMEA ve riskli komutlar için bağımsız PLC/SIS mimarisi.
- Gerçek IAM (çok faktörlü kimlik doğrulama, RBAC/ABAC, oturum revocation), gizli anahtarlar, erişim tabakalaştırma, ağ segmentasyonu, mTLS, güvenlik izleme/backup/disaster recovery.
- Farklı sahalara özel sürüm, OEM sürücü/adapter katmanı, sürücüler için *önce salt okunur shadow*, sistem mühendisliği kontrolleri, SCADA ve koruma röle üreticisi koordinasyonu.
- FAT, SAT, HIL, yük/performans stres testleri, sahada pilot, bağımsız siber güvenlik ve güvenlik doğrulaması.
- Windows `.exe` üretimi ve işletim sistemi imzalama; istemci uzaktan bağlantı güvenliği ve otomatik güncelleme kanalı. Linux simülasyon prototipi kapanmadan sağlanmış sayılmaz.

## Minimum kabul kanıtı listesi

| Kabul kapısı | Şu an | Kapanması için gereken kanıt |
|---|---|---|
| SIMULATION_QA | Yazılım testleri | Regresyon, fault matrix, smoke test raporları |
| OEM_MODEL_CALIBRATION | Açık | İmzalı üretici dokümanı + bağımsız model fit/holdout |
| MEASURED_VALIDATION | Açık | Kalibre edilmiş sensör, veri kökeni, 365 gün veri, ayrı test aralığı |
| OT_CYBER_AUTH | Açık | IAM/RBAC, tehdit modeli, bağımsız pentest, IEC 62443 kapsam raporu |
| LOCAL_SAFETY | Açık | Koruma röle/PLC/SIS ve bağımsız emniyet çalışması |
| HIL_FAT_SAT | Açık | Yetkili saha/mühendis FAT, SAT, negatif durum testleri |
| WINDOWS_CLIENT | Açık | Windows build, QA, imzalama ve güncelleme testi |

**Kontrol düğmelerinin varlığı veya 1000 testin geçmesi bile bu tabloyu tek başına kapatmaz.**
