# GitHub sürüm hazırlığı — Autonomous Plant Platform

Bağlı GitHub hesabındaki açık depo: `semihkbacak/autonomous-plant-platform`.

**Kontrol anında GitHub main README güncel sürümü `v0.2.0 HES MVP` olarak gösteriyordu.** Yerel Linux projesi ise v1.4 araştırma / SHADOW araçlarını içeriyor. Bu yüzden yalnızca v1.5 betiklerini eski main'e eklemek tam bir sürüm güncellemesi değildir. Önce kullanıcıya ait **en güncel, testleri geçen temiz kaynak ağacı** senkronize edilmeli. İçeriği kontrol etmeden repo'ya topluca dosya göndermeyin.

Önerilen yerel sıra:

```bash
cd /run/media/semih/Others-Partition/Projects/autonomous-plant-platform
source .venv/bin/activate
python -m pytest -q --assert=plain -x
# Git durumunu gör; commit/push YAPMAZ
bash scripts/audit_git_v15.sh
```

Git clean ve dosya denetiminden sonra **ayrı bir release hazırlık dalında** PR açılması önerilir. Sürüm etiketi `v1.5.0-rc1` ancak kullanıcı incelemesinden ve Windows testlerinden sonra verilmeli; aksi takdirde yanlışlıkla saha kullanımına hazır algısı oluşturur.

**Git'e yüklenmemesi gerekenler:** `.env`, şifreler/sertifika özel anahtarları, kişisel bilgiler, gerçek saha telemetrisi ve tesis IP/adresleri, SQLite ve çıktı dosyaları, `.venv`, OEM lisanslı/üçüncü taraf tescilli dokümanlar, `build/`, `dist/`, Windows imzalama sertifikası ve PyInstaller cache.

`.github/workflows/windows-viewer-preview.yml` manuel başlatıldığında **unsigned preview** üretir. GitHub Actions artifact önce kullanıcı tarafından Windows'ta test edilmeli. İmza/AV raporu ve bağımsız kabul olmadan ``production-ready'' veya ``safe for unattended operation'' denmemelidir.
