# Autonomous Plant Platform v1.2 — Gerçek Tesis Kullanımı İçin Açık Mühendislik Konuları

**Bu paket gerçek bir santralde kumanda için uygun değildir.** 54 GES, 12 HES ve 12 RES kayıtlı senaryosu ve canlı oturumlar **sentetiktir**. Önceki yazılım testleri saha güvenliği kanıtı değildir. Bu paket, aşağıdaki işlerin yalnızca yazılım/denetim bölümünü sağlar.

## Öncelik 0: bağımsız yerel güvenlik

- Yetkili tesis mühendisi ile kapsam, HAZOP, LOPA/FMEA, koruma felsefesi.
- Bağımsız PLC, koruma röleleri ve varsa SIS: E-stop, overspeed, aşırı akım, yangın, DC ark/izolasyon vb. İzinler merkezi sunucuya bağlı olmamalı.
- Yetki ayrımı, tehlikeli eylem için onay ve kurtarma/yerel devralma; ağ kopması halinde tesis korunmalı.
- OT ağı ile ofis/internet ağı segmentasyonu; yerel güvenlik ağ geçitleri; mTLS, MFA/RBAC, parola ve anahtar ömrü, imzalı güncelleme, merkezi SIEM, denetim ve bağımsız sızma testi.
- Tesis bazında yetkili SCADA/PLC/OEM üretici entegrasyonu; hiçbir genel "her tesiste bir tuşla çalışır" yaklaşımı güvenilir değildir.

## GES model doğrulaması

- OEM panel/inverter verim ve termal derating, gerçek MPPT çalışma penceresi, string sayısı ve üretici veri kökeni.
- Tam paralel string I-V eğrisi, bypass diyotları, çoklu yerel MPP / global MPPT, dizi gölgelenmesi için bağımsız karşılaştırma.
- Gerilim/frekans limitleri, anti-islanding, DC izolasyon, topraklama, ark tespiti, yangın güvenliği ve ilgili grid code.
- Kirlilik, kar, degrade, hotspot, soğutma kaybı, ölçüm sapması, haberleşme zaman aşımı, firmware ve bakım değişiklikleri.

## HES model doğrulaması

- Cebri boru su darbesi/MOC, rezervuar/kaptaj ve enerji muhasebesi; çevresel debi hakkı ve tesis sınırları.
- Pelton jet/nozzle ve türbin hill-chart; ani yük atma ve overspeed dinamiği, hidrolik aktüatör doğrulaması.
- Mekanik kontrol, titreşim, yatak sıcaklığı, elektrik/trafo ve şebeke senkronizasyonu saha testleri.

## RES model doğrulaması

- OEM sertifikalı türbin güç eğrileri, türbülans, mikrositing, wake/CFD, density correction.
- Pitch/yaw aktüatör sürüşü ve sensör hatası, fren/restart, overspeed, buzlanma, yük ve yorulma modelleri.
- Şebeke koruması, acil kapanma, türbin kontrolör ve ağ kaybı testleri.

## Üç sistem için ortak dağıtım

- OEM/site konfigürasyonu, kalibrasyon sertifikaları, bağımsız test edilmiş ölçümler, zaman eşitlemesi, veri kaybı, replay/reordering, iletişim gecikmesi.
- Historian HA/failover, yedekleme ve geri yükleme tatbikatı, immutable/signed audit trail, olay ve alarm yönetimi, SLA/on-call.
- Etkin komut yetkileri, operatör kimliği, MFA/RBAC, seçilebilir güvenli site profilleri, yerel veto, neden-sonuç ve cihaz onayı.
- HIL, FAT, SAT ve yetkili saha komisyonlandırma; mevzuat, işletmeci/grid operator izinleri.
- Gerçek ölçümle öğrenme/kalibrasyon ayrı eğitim/validasyon/test sahaları üzerinde; sonuçların yerel mühendis tarafından incelenmesi.
- Windows .exe'yi hedef Windows'ta inşa etme, güvenlik taraması, dijital imzalama, otomatik güncelleme, işletim sistemi testleri. İstemci exe sunucunun/PLC'nin yerine geçmez.

## Yeni v1.2 kapsamı

- Gerçek OT protokol sürücüsü / fiziksel komut **yok**.
- `SIMULATION` ve `SHADOW` çalışma modları, bilinmeyen `REAL` moduna fail-closed.
- CSV üzerinden offline SHADOW kalite/düzen/güncellik kontrolü; kaynak izinleri ve kalibrasyon ayrıca doğrulanmalıdır.
- 30 deterministik sentetik telemetri hata deneyi: NaN, negatif, birim, zaman, bozuk kalite, stale, duplicate.
- Saha geçişi kabul kapıları ve dosya SHA-256'ları; hash **bağımsız onay değildir**.
- Windows için salt-okunur gösterici kaynak kodu ve Windows üzerinde .exe derleme betiği; kurulmuş/sınanmış .exe değildir.

**Sonuç:** Bu paket simülasyon/prototip olgunluğunu artırır. `real_site_ready` ve `real_control_authorized` kasıtlı olarak her zaman `false` kalır. Bu yanlış negatif değil; saha kanıtları olmadan güvenli durumdur.

## v1.2 canlı GES/RES kabul denemesi

`tools/live_simulation_acceptance.py` mevcut GES/RES modeline dayalı 14 adet sanal günlük senaryoyu test eder. Bu, önceki 30 **telemetri kalite** hatası deneyinden ayrıdır. Fiziksel işletme/koruma modelinin gerçek saha onayı değildir.
