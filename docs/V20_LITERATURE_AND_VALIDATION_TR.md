# v2.0 — Literatürden uygulamaya: kanıt sınırları

Bu kaynaklar **model/standart gereksinimlerini tanımlar**. Literatürden bir formülü Python'a yazmak, belirli santralde doğruluğu veya operasyonel güvenliği kanıtlamaz.

## Fotovoltaik GES

- pvlib `Single diode models`, CEC / De Soto / PVsyst: https://pvlib-python.readthedocs.io/en/latest/reference/pv_modeling/sdm.html. Üretici beş parametresi, sıcaklık, ışınım ve çalışma rejimi gerektirir. Mevcut kodun yalnızca sentetik parametrelerle çalışması OEM yeterliliği değildir.
- SAM PV teknik referansları (Gilman vd.): https://sam.nlr.gov/photovoltaic/pv-publications.html. Sonraki aşamada inverter eğrileri, termal derating, gölge/topoloji ve bağımsız üretim karşılaştırmaları için referans.
- SAM doğrulama çalışmaları: https://sam.nrel.gov/photovoltaic/pv-validation.html. Ölçülen enerji ile test edilmiş dış modellerin karşılaştırma metodolojisi.
- Proje `research_v2/engine.py`: açıklanabilir ışınım-sinüzoidi ve ideal `P = A*G*eta` kullanır; atmosfer, panel/MPPT ve elektroteknik ayrıntıları karşılamaz.

## Hidro HES

- IEC 60041 türbin kabul testi genel kapsamı: https://webstore.iec.ch/en/publication/154. Tesis özel ölçümleri uzman mühendislerin değerlendirmesi gerekir.
- Projede `P[kW] = 9.81 * Q[m3/s] * H[m] * eta` araştırma taraması, **su darbesi, hız denetleyici ve koruma algoritması değildir**.
- Gerçek cebri boru/hidrolik geçişleri için boru parametreleri + ölçüm + geçici rejim model doğrulaması gereklidir.

## Rüzgâr RES

- NREL OpenFAST dokümanı: https://openfast.readthedocs.io/
- NREL ROSCO kontrol algoritmaları: https://rosco.readthedocs.io/en/latest/
- Projedeki `P[kW] = 0.5 * rho * pi * r^2 * V^3 * Cp / 1000`, Cp <= 16/27; nominal güç sınırı basitçe uygulanır. Bu, wake/aeroelastik yük, pitch/yaw kararlılık ve gerçek elektrik koruma modeli değildir.

## Güvenlik ve dağıtım

- NIST SP 800-82 Rev.3: https://csrc.nist.gov/pubs/sp/800/82/r3/final. OT zonları, bağımsız emniyet tasarımı, risk ve operasyonel süreklilik için rehber.
- GitHub Actions Artifact Attestations: https://docs.github.com/en/actions/concepts/security/artifact-attestations. Attestasyon kaynağı ve inşayı doğrular, ürünün güvenli veya sahada onaylı olduğunu **kanıtlamaz**.
- Windows SignTool: https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool. Kullanıcı tarafından edinilmiş ve yetkilendirilmiş imza sertifikası gerekir; paket sertifika içermez.
- `pip-audit`: https://pypi.org/project/pip-audit/ — güncel açık kaynak bağımlılık uyarıları için dış çevrim içi tarama gerektirir.

## Ölçüm–model yöntemi

İlk %75 kronolojik örnekte tek ölçek katsayısı `sum(Ppred*Pmeas)/sum(Ppred²)` fit edilir; **sonraki %25** MAE/RMSE/bias için tamamen ayrı tutulur. Ölçüm kaynağı SHA256 ve `GOOD` yazsa bile bağımsız doğrulamadan geçmeden `site_validated=false` kalır. Uzun dönem drift, OOD, kalibre sensör ve bağımsız inceleme ayrı açık iş kalemleridir.
