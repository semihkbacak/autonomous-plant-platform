# v1.4 teslim / doğrulama kapıları

| Kapı | Bu ZIP ne sağlar? | Dış kanıt olmadan sonuç |
|---|---|---|
| Python simülasyonu | Eski regresyon korunmasını sınamak için testler | Kullanıcı ortamı test sonuçları gerekir |
| GES OEM | pvlib De Soto beş-parametre hesabı (tüm değerler açıkça verilirse) | **OEM doğrulanmadı** |
| HES OEM | v1.3 ideal Joukowsky/rezervuar taraması ile literatür bağları | **Hidrolik saha tasarımı doğrulanmadı** |
| RES OEM | v1.3 pitch/yaw proxy ve literatürde OpenFAST/ROSCO karşılaştırma yol haritası | **Türbin sahası doğrulanmadı** |
| Field validation | Veri kalite ve kronolojik holdout karşılaştırması | **Kaynağın sahiciliği / test protokolü onaylanmadı** |
| OT security | Salt-okunur araştırma endpoint, harici prosedür listesi | **Gerçek yetkilendirme/OT entegrasyonu yok** |
| HIL / FAT / SAT | Kanıt envanteri ve sorumluluk kontrol listesi | **Yapılmadı** |
| Windows EXE | Sonraki ayrı release aşaması için checklist | **Exe oluşturulmadı, imzalanmadı** |
| GitHub release | Belgeler, risk uyarıları ve test planı | **Henüz yayın/güncelleme yapılmadı** |

## GitHub yayımlamadan önce

1. `git status` ile çalışan kaynakları gözden geçir. `.venv/`, `.git/`, `outputs/`, `*.sqlite3`, `*.key`, `*.pem`, `.env`, ham saha CSV'leri yüklenmemeli.
2. Windows istemci yalnızca salt okunur SHADOW API'ye bağlanmalı. OAuth/MFA ve uzak erişim gereksinimlerini ayrı belgele.
3. `pytest` çıktıları, build üretim sistemi, sürüm sabitleme, dependency/sbom taraması, imza ve Windows çalıştırma testlerini yayın eklerine ekle.
4. README'de "SIMULATION/SHADOW ONLY; NO REAL OT CONTROL" uyarısını koru.
5. Kaynak kodu/telif/lisans izinlerini kontrol et. pvlib/OpenFAST/ROSCO bağımlılıklarını kendi lisanslarıyla ayrı yönet.
6. GitHub commit/push işlemleri ancak gözden geçirme ve açık onay sonrasında yapılmalı.
