# Autonomous Plant Platform — Gerçek tesis hazırbulunuşluk raporu (v1.3)

**Durum: NO-GO / Gerçek tesise doğrudan bağlamayın.** Bu paket yalnızca simülasyon, fizik taraması ve izinli **offline** SHADOW veri değerlendirmesi içindir. Entegre OT komut geçidi **yoktur**. Erişim politikası ve TOTP modülü yalnızca izole güvenlik testidir; merkezi kimlik sağlayıcısına bağlanmadıkça gerçek MFA/RBAC sayılmaz. Windows build scripti çıktı üretebilir ama bu, imzalama veya kabul değildir.

| İş kalemi | v1.3 içeriği | Gerçek saha onayı için gerekli |
|---|---|---|
| GES OEM | Çoklu string örneklenmiş I–V MPPT taraması; kaynak-hash kayıt kontrolü | Üretici onaylı IV/diyot parametreleri, inverter eğrileri, MPPT dinamizmi, elektriksel koruma testleri, sıcaklık ve gölge saha verisi |
| HES OEM | İdeal Joukowsky basınç taraması, rezervuar su dengesi, beyan edilen türbin verim noktası | Su darbesi için MOC/karakteristikler, surge tank, vana/yük atma, hidrolik transient modeli, OEM türbin haritası, governor hız/kararlılık, koruma röleleri |
| RES OEM | Pitch/yaw hız limiti ve donma arızası, yaw güç sapması | IEC tasarım yükleri, yapısal yükler, pitch/yaw sürücü ve fren modelleri, gerçek OEM güç eğrisi, wake ve türbülans validasyonu |
| Tesis adaptörleri | Tek yönlü offline CSV/etiket şema doğrulaması | Tesis bazlı yetkili OPC UA/IEC 60870-5-104/Modbus tasarımı, gateway, sertifikalar, veri yazma izni **ayrı** değerlendirme |
| OT siber güvenlik | Salt-okunur loopback kısıtı, RBAC/TOTP algoritma araştırması, komut erişimi kapalı | Kimlik sağlayıcı MFA, mTLS, cihaz kimliği, servis hesapları, IEC 62443 risk analizi, ağ segmentasyonu, VPN/ZTNA, key management, HA, kurtarma planı, kırmızı takım |
| Güvenlik/kumanda | Gerçek komut **kapalı** | Yerel interlock, ayrı koruma/SIS, E-stop, manuel takeover, bağımsız süreç güvenlik incelemesi, eğitim, prosedür ve sigorta gereksinimleri |
| HIL/FAT/SAT | Boş kanıt şablonları ve negatif test planları | Yetkili mühendis/test şahidiyle donanım testleri, gerçek I/O, imzalı rapor, arıza kurtarma ve şebeke kodu kabulü |
| Windows | Read-only viewer için build + offline preflight | Windows üzerinde .exe smoke/system test, imza, AV/EDR, uygulama dağıtım, rollback ve kurumsal onay |

## FAT / SAT taslak test sırası

1. Kullanıcı/tesis/envanter kimliği, OEM versiyon, firmware sürümü, P&ID ve haberleşme topolojisinin onaylı belgeleri.
2. İzinli salt-okunur gölgede ölçümlerin referans ölçerle tutarlılığı; zaman damgası/kalite/ünite/etiket doğrulaması.
3. Ağ kopması, gecikme, saat kayması, yanlış kalibrasyon, yeniden başlatma ve zararlı girişin kontrol sistemini etkilememesi.
4. Bağımsız SIS/koruma ekipmanının hiçbir yazılım durumundan etkilenmeden çalışması.
5. Komut moduna geçiş ayrı risk onayı, bakım penceresi, mekanik/elektriksel sorumlu onayı ve tersine çevirme prosedürü gerektirir.
6. Mühendis, OT güvenlik ve işletme temsilcilerinin gerçek fiziksel sınama şahitliği; kanıtların değiştirilemez kayıtlı asılları.
7. Kurtarma, yedekleme, sürüm değiştirme, olay müdahalesi, yetki iptali, 7/24 görevlendirme ve periyodik denetim.

**Belgelerin sisteme yüklenmesi onay verildiği anlamına gelmez.** Gerçek kullanıma izin yalnızca tesis sahibinin, yetkili mühendislerin ve ilgili kurumların yürüttüğü bağımsız kabul sürecinden doğar.
