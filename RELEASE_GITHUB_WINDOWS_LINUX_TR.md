# v1.5 Windows + Linux — GitHub dağıtım rehberi

**Kapsam:** 2 adet sentetik HES ünitesi, GES/RES modelleri ve yerel FastAPI paneli; saha/PLC/SCADA kumandası **yoktur**. Bu sürüm yalnızca simülasyon ve çevrimdışı SHADOW araştırma önizlemesidir.

## Teslimat

- Windows: `01_WINDOWS_KUR_TEST_VE_BASLAT.cmd` (Python 3.13, internet), `02_YALNIZ_TEST.cmd`, `03_TESTSIZ_BASLAT.cmd`, opsiyonel salt-okunur viewer `.exe` derleyicisi.
- Linux: `bash 01_LINUX_KUR_TEST_VE_BASLAT.sh` veya `bash 02_LINUX_YALNIZ_TEST.sh`; Python 3.13 önerilir.
- Bağımlılıklar: `requirements.txt` içinde scikit-learn==1.9.1 (SSD'deki modelin kaydedildiği sürüm). `pvlib==0.16.1`.
- GitIgnore: `data/` ve `outputs/` altındaki tüm yerel dosyalar hariç tutulur. Yalnızca üç test CSV'si ve bir statik OEM audit JSON dosyası Git'e alınır. `ges_oem_research.zip` ayrı bir istisnadır.
- CI: `.github/workflows/portability-ci.yml` Python 3.13 ile Windows+Linux regresyon ve hash denetimi. Windows viewer EXE iş akışı elle `workflow_dispatch` ile çalışır ve **imzasız/salt-okunur** artefakt üretir.

## GitHub'a aktarırken DİKKAT — mevcut GitHub deposunu koru

Bu ZIP'in içinde `.git` yoktur. **`git init` ile mevcut geçmişin yerine yeni repo oluşturma.** Mevcut `release/v1.5-preview-20261015` dalını ayrı temiz klasöre `git clone` ile al, kaynak paketini bu dalın içine kopyala. Git'te untracked olan kullanıcı verilerini asla topluca aktarma.

1. FIX2 Windows proje klasörünü ve orijinal Linux SSD projesini **ayrı yedek** olarak tut.
2. Kaynak ZIP'i ayrı dizine çıkart; `.git`, `.venv`, `outputs/*.sqlite3` gibi yerel dosyaları taşıma.
3. Yalnızca **bu kaynak ZIP'in içeriğini** hedef klonun köküne kopyala. Kaynak klasörün kendisini alt klasör olarak ekleme. ZIP'den taşınan kaynaklar üzerinden testleri tekrar çalıştır.
4. `python scripts/verify_release_assets.py` (Windows'ta `py -3.13 scripts/verify_release_assets.py`) komutu **5/5 hash OK** demeli. `git check-ignore -v` ile beş gerekli dosyanın engellenmediğinden emin ol.
5. `git status --short` ve `git diff --stat` incele. **Kişisel verilerin, parolaların, erişim anahtarlarının, tescilli OEM dokümanlarının veya gerçek telemetrinin Git'e gitmediğini doğrula.** Bu ZIP'teki `ges_oem_research.zip` türetilmiş araştırma/PDF/XLSX içerir; dağıtım ve alıntı hakkını ayrıca incelemeden açık repoya push yapma.
6. Emin olduğunda sadece ayrı bir branch'te `git add -A`, `git diff --cached --check`, `git diff --cached --stat`, `git commit`, `git push` uygula ve PR aç. **Körlemesine `git add -f .` yapma.**
7. GitHub Actions `Cross-platform simulation regression` iş akışında Windows+Linux iki işin PASS olduğunu, Windows EXE'nin açıldığını ve yerel panellerin çalıştığını kontrol et. Kullanıcının açık onayı olmadan varsayılan `main`i değiştirme veya gerçek tesis sürümü ilan etme.

## Test dürüstlüğü

Temiz kaynak ağacında Linux Python 3.13 ile **662 passed** doğrulandı. Kullanıcı, FIX2 başlatıcısı üzerinden Windows panellerinin çalıştığını bildirdi; Windows tam test özeti bu paket için ayrıca raporlanmalı. GitHub Actions henüz bu paketle tetiklenmediği için CI sonucu iddia edilmiyor.

## Geliştirme sınırı

HIL/FAT/SAT, üretici onayı, saha güvenliği ve imzalama eksiktir. Saha kumandası ve başıboş otonom kontrol **yoktur**.
