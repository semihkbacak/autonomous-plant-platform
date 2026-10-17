# Autonomous Plant Platform v2.0 — RC4 mühendislik teslimi / kanıt durum tablosu

**Tarih:** 16 Ekim 2026. **Sınır:** Lokal HES/GES/RES sentetik simülasyon ve offline araştırma. **Saha kumandası kesinlikle yok.**

## Tamamlanan doğrulanabilir yazılım işleri

| Aşama | Teslim / ilgili dosya | Test edilen sınır |
|---|---|---|
| v1.5.1 | `scripts/sbom_v20.py`, `research-v20-security.yml`, Windows EXE CI + attestation, `sign_native_windows_v20.ps1` | Paket envanteri ve release test otomasyonu; **gerçek sertifika sağlanmadan imzalama yapılamaz** |
| v1.6 | `desktop/full_simulator_launcher.py`, `desktop/build_full_windows_v20.ps1` | Masaüstü/yerel sunucu self-test; native EXE GUI ve derleme GitHub Actions ile doğrulanmalı |
| v1.7 | `research_v2/workspace.py`, `engine.py`, `simulator/hydro_checkpoint.py`, `simulator/portfolio_checkpoint.py` | Tekil model konfigürasyonu kilidi, örnekler, SQLite backup/restore, HES kontrol noktası ve GES/RES **duraklatılmış** deterministik tekrar oynatma |
| v1.8 | `research_v2/benchmarks.py`, `physics.py`, `provenance.py` | Kronolojik sentetik ölçüm karşılaştırması; saha parametreleri bulunmadığından OEM kalibrasyonu yapılmış değildir |
| v2.0 | `research_v2/api.py`, `workspace.py`, `provenance.py` | Site/oturum adı, karantina ve CSV raporları; yetkili sahadan otomatik veri bağlantısı yok |

## Dış onay gerektiren sert sınırlar

**Bunlar bir yazılım testinin sonucu değildir ve bağımsız kanıt yokken tamamlandı sayılmaz.**

1. **Lisans / üçüncü taraf hakları:** yazılım hak sahibinin lisans seçimi, üçüncü taraf bileşen envanteri, `ges_oem_research.zip` içindeki tüm PDF/XLSX için ayrı dağıtım hakkı kaydı. Dosyaların halka açık olması yeterli değildir.
2. **Authenticode ve Windows yayını:** yayıncıya ait geçerli kod-imzalama sertifikası, `signtool`, sertifika zinciri/itibar kontrolleri; hedef Windows 10/11 üzerinde GUI, AV/EDR ve kurulum-kaldırma doğrulaması.
3. **OEM kalibrasyonu:** model, parça numarası, firmware, gerçek eğriler, onaylı üretici dokümanı, ölçüm doğruluğu ve sıcaklık/gerilim/debi/rüzgâr çalışma sınırları. De Soto, Joukowsky veya Cp hesabı tek başına OEM onayı değildir.
4. **Gerçek saha verisi:** izinli kaynak, cihaz kimliği, kalibre edilmiş sayaç/sensör, UTC-zaman, veri bütünlüğü, kronolojik holdout ve yetkili değerlendirme; metin `quality=GOOD` otomatik sahicilik kanıtı değildir.
5. **OT güvenliği ve HIL/FAT/SAT:** tesis sahibi, elektrik/mekanik/OT güvenlik mühendisleri, izinli protokol entegrasyonu, bağımsız interlock/SIS/koruma röleleri, HAZOP/FMEA, IEC 62443 güvenlik bölgelemesi, HIL ve imzalı kabul. Hâlihazırdaki tüm komutlar yalnızca sentetik model içindir.

`app.site_readiness.readiness_report()` onay doğrulanmadıkça 10 geçiş kapısının tümünü açık tutar. Projede **real_control_authorized = false** korunmalıdır. Test sayısı veya GitHub yeşil rozetleri bu şartları değiştiremez.

## Windows sürüm kabul adımları

1. ZIP dosyasını *tamamen ayıkla*; `.venv` başka işletim sisteminden aktarılmamalı.
2. `01_WINDOWS_KUR_TEST_VE_BASLAT.cmd` ile Python 3.13 bağımlılıklarını kurup tam testi çalıştır.
3. `05_WINDOWS_MASAUSTU_SIMULATORU.cmd` ile tek bilgisayarda, internet/OT ağı olmadan HES/GES/RES modlarını dene.
4. `06_WINDOWS_TAM_EXE_DERLE.cmd` ile yerel `dist/` klasörünü oluştur; ayrıca GitHub'da `.github/workflows/research-v20-windows-bundle.yml` **manuel** çalıştırıldığında native EXE self-test ve kaynak kökeni attestation kontrolü uygulanır. **Attestation = Authenticode değil**.
5. Gerçek yayın sertifikanı kendi Windows kullanıcı sertifika deposuna güvenli şekilde yükledikten sonra `scripts/sign_native_windows_v20.ps1 -CertificateThumbprint <GERÇEK_SERTIFIKA_SHA1>` çalıştır. Bu komut kayıp/uygunsuz sertifikada **başarısız olur**.
6. Birden fazla temiz Windows makinesinde EXE smoke ve GUI testini, Defender/SmartScreen sonuçlarını, kurulum/kaldırma/yeniden başlatma testlerini kaydet. Başarısızsa release yapma.
7. Manuel GitHub Release için kaynak lisansını/üçüncü taraf haklarını onayla, Windows artifact SHA-256'sını ve raporlarını ekle; RC sürümü önizleme olarak etiketle.

## Araştırma durum devamı (yalnızca sentetik)

- `run_into_store` aynı oturumda fizik konfigürasyonunu JSON+SHA-256 ile bağlar; farklı parametreyle sessizce devamı reddeder.
- `ResearchStore.backup_verified` ve `restore_verified` SQLite yedeği için hash/sağlamlık/üstüne yazma önlemleri kullanır.
- `simulator/hydro_checkpoint.py` eski HES durumunun dahili ilerleme/sentetik alarm kontrol noktasını Pydantic+JSON ile geri yükler.
- `app.sim_runtime` GES/RES için her adımın modunu ve üretim raporu hash'ini kaydeder; farklı sonuç üretirse tekrar oynatma reddedilir.
- `simulator/portfolio_checkpoint.py` **üç motor da duraklatıldıktan sonra** tek araştırma dosyasına kayıt/geri yükleme sağlar. Canlı, paralel çalışan çok düğümlü veya gerçek tesis durumunun atomik snapshot'ı **değildir**. JSON hash'i kötü niyetli erişime karşı kriptografik kimlik doğrulaması değildir.

## Denetim kaynakları (referans, sertifikasyon kanıtı değil)

- NIST SP 800-82r3 OT Security: https://csrc.nist.gov/pubs/sp/800/82/r3/final
- pvlib 0.16.1 Single diode modeling: https://pvlib-python.readthedocs.io/en/stable/user_guide/modeling_topics/singlediode.html
- Microsoft SignTool ve uygulama paketi imzalama: https://learn.microsoft.com/en-us/windows/msix/package/sign-app-package-using-signtool
- GitHub signed build provenance: https://github.com/actions/attest
- ISA/IEC 62443: https://www.isa.org/standards-and-publications/isa-standards/isa-iec-62443-series-of-standards

**Bu teslim v2.0 yazılım araştırma adayıdır, saha/üretim kabul belgesi değildir.**
