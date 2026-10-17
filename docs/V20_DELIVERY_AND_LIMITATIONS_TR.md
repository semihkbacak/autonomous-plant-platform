# Autonomous Plant Platform — v2.0 Engineering Research Candidate

**16 Ekim 2026** · **Kaynak ve test teslimi** · **Üretime/sahaya kabul edilmedi**

> Bu paket, gerçek HES/GES/RES santrali kontrol eden bir ürün değildir. PLC/SCADA/OT bağlantısı veya saha komut yetkisi yoktur. **`SIMULATION` ve `SHADOW` dışındaki modları açmayın**. IEC/OEM/FAT/SAT sertifikası, gerçek ölçüm kalibrasyonu veya saha emniyet onayı bu pakette bulunmuyor.

## Adım adım özellik durumu

| Yol haritası | Uygulanıp test edilen | Kalan üretim kapısı |
|---|---|---|
| v1.5.1 Dağıtım | Fixture SHA-256, `scripts/security_preflight_v20.py`, kaynak + paket envanteri, bağımlılık sürümleri, CI workflow | Lisans sahibinin kararı, üçüncü taraf OEM belge yeniden dağıtım izni, çevrim içi pip-audit/SBOM attestasyonu, yayın imzası, Github Release |
| v1.6 Masaüstü | Tkinter sekmeleri, HES/GES/RES canlı sentetik ekran ve eğilim çizgileri, senaryolar, tek işlemlik loopback Uvicorn başlat/durdur, ZIP içinden açılış uyarısı, Windows onedir EXE derleme tarifi | Native Windows çalışır EXE, imzalama/SmartScreen/AV testleri, uzun süreli GUI stress, kurulum/updater ve rollback |
| v1.7 Simülasyon & SQLite | Kalıcı senaryolar, 1-31 gün tek UTC izleme, kısmi çalıştırmadan devam, atomik ardışık adım, CSV ve XLSX dışa aktarma | Mevcut canlı HES/GES/RES fizik motorunun iç durumunu birlikte serileştirerek kesin kaldığı yerden devam ettirme ve gerçek zamanlı kombine orkestrasyon |
| v1.8 Fizik & ML | Mevcut HES/GES/RES araştırma modelleri, açık formüllü sentetik fizik taraması, kronolojik öğrenme/test ayrımı, MAE/RMSE/bias, örnek bulgu raporları | Üretici onaylı parametreler, farklı işletme rejimleri, OpenFAST/ROSCO bağımsız dinamik kalibrasyon, gerçek etiketli ML performans analizi ve OOD sertifikasyonu |
| v2.0 Çoklu tesis | Offline çoklu site/oturum, kaynak etiketli CSV karantina ve SHA-256, araştırma API, senaryo enerji kıyası | Yetkili ölçüm sistemiyle güvenilir entegrasyon, cihaz adaptörleri, bağımsız saha kabulü, gerçek tesis dijital ikiz kriterleri |

## Windows açılış hatasının giderilmesi

`C:\\Users\\...\\AppData\\Local\\Temp\\...zip...\\windows\\windows_start.py` hatası bir ZIP önizleme klasöründe yalnızca CMD dosyasının geçici açılmasından kaynaklanıyor. **ZIP'e sağ tık > Tümünü Ayıkla** ile yeni bir klasöre (örn. `C:\\AutonomousPlantV20`) çıkar. Ardından en üstteki `00_BASLAMADAN_ONCE_WINDOWS.cmd` dosyasını çalıştır. Baştan kopyalamaya veya Linux `.venv` klasörünü Windows'a taşımaya çalışma. Yeni betik eksik dosyaları Python başlamadan yakalayıp açık uyarı verir.

İlk kurulumdan sonra masaüstü GUI: `05_WINDOWS_MASAUSTU_SIMULATORU.cmd`. Tam Windows EXE için (native Windows'ta, internet erişimiyle): `06_WINDOWS_TAM_EXE_DERLE.cmd`. Çıktı **PyInstaller onedir, UNSIGNED**; Windows makinesinde ve Windows Defender ile elle test edilmedikçe dağıtma.

## Test ve güvenlik kanıtı (bu teslim)

- Linux CPython 3.13.5, yerel kod + `pvlib 0.16.1` kaynakları: **678 passed, 2 scikit-learn model sürümü uyarısı**, 29,59 sn. Bunlar eski 662 test + önceki v2.0 7 test + yeni 9 testtir.
- `scripts/verify_release_assets.py`: 5/5 dosya SHA256 başarılı.
- `scripts/security_preflight_v20.py`: onay/saha kontrol bayrakları `false`, loopback sınırı doğrulandı (temel invariant kontrolü).
- Windows EXE derlenmedi; Windows GUI uçtan uca testi yapılmadı; Windows v2.0 test sonucu bilinmiyor.
- Tam bağımlılık kilidi **hash'li değil**, yalnızca `requirements.txt` ve `requirements-windows.txt` içinde ana sürümler sınırlandırılmış/pinlenmiş.
- `pip-audit` çevrim içi güvenlik veritabanı ile çalıştırılmadı; imzalama ve SBOM attestasyonu yapılmadı.
- Windows/Linux CI tanımları pakete eklendi ancak bu aday paket için GitHub Actions **çalıştırılmadı**.

## Laboratuvar, OEM ve gerçek saha gereksinimleri

1. HES: ölçülen net düşü/debi, türbin hill chart, MOC su darbesi, yük atma/overspeed ve bağımsız koruma doğrulaması.
2. GES: panel/inverter OEM IV verileri, pvlib CEC/De Soto parametreleri, gölgeleme/bypass ve saha DC/AC karşılaştırması.
3. RES: IEC uyumlu güç eğrisi, OpenFAST/ROSCO pitch/yaw/aeroelastik doğrulama, türbülans/wake, fren ve koruma.
4. Ortak: saha sahibinden yazılı yetki, gerçek verinin kaynağı ve sensör kalibrasyonu, tarihsel kör test, ölçüm belirsizliği, yetkili OT ağ mimarisi ve bağımsız HIL/FAT/SAT.
5. Hukuk: proje lisansı henüz belirlenmedi; `ges_oem_research.zip` üçüncü taraf PDF/XLSX belgeleri içeriyor. Bu belgeler için telif/dağıtım haklarını ispat edemiyoruz. Mevcut herkese açık GitHub geçmişindeki belge yayını da gözden geçirilmeli.

**Sonuç:** Yazılım yerel **araştırma/simülasyon prototipi** olarak ilerletildi; **tam üretim / gerçek tesis sürümü** değildir. Bu ifade imza veya onay gelmeden değiştirilmemelidir.
