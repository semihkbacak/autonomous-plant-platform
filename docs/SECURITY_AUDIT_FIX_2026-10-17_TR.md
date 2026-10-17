# Stabil aday güvenlik denetimi düzeltmesi — 17 Ekim 2026

## Kanıt

GitHub Actions çalışması `38988651444` Ubuntu 24.04 ve Windows 2022'de başarısız oldu. Korunan `pip-audit.json` raporunda **pytest 8.4.2** için **PYSEC-2026-1845 / GHSA-6w46-j5rx-g56g / CVE-2025-71176** bulundu. Raporda aynı kayıt iki defa görülüyor; iki bağımsız paket değil.

Kök neden `requirements.txt` içindeki `pytest>=8.0,<9.0` sınırıydı. `pip-audit` düzeltme sürümünü `9.0.3` olarak bildirdi. Yeni gereksinim `pytest>=9.0.3,<10.0` şeklindedir; CI her iki işletim sisteminde gerçek kurulum ve internet tabanlı güvenlik denetimi çalıştıracaktır.

Ayrıca Node.js 20 kullanıldığına ilişkin ayrı **uyarı** için GitHub Actions bileşenleri `checkout@v5`, `setup-python@v6`, `upload-artifact@v6` (Node 24) olarak güncellendi. Söz konusu uyarı testin başarısız olmasına neden olmamıştı.

## Yayın kapısı

`pip-audit` başarısızlık durumu saklanmaz veya `continue-on-error` ile geçilmez. JSON raporu ve SBOM başarısızlık halinde de artifact olarak saklanır. GitHub Actions'ın son commit üzerinde Windows ve Ubuntu'da başarılı olması **gerekir**. Projenin endüstriyel saha/PLC/SCADA kontrol onayı, OEM sertifikası veya açık kaynak dışındaki üçüncü taraf veri için dağıtım lisansı olduğu iddia edilmez.
