# Autonomous Plant Platform — v1.5 Preview Dağıtım Notları

**Kapsam:** SIMULATION / SHADOW yazılımı ve salt-okunur masaüstü izleyici.
**Kapsam dışı:** sahada canlı kontrol, uzaktan kontrol komutları, PLC/SCADA bağlantısı, OEM/IEC sertifikasyonu, HIL/FAT/SAT.

## Linux

`bash scripts/setup_linux_v15.sh` bağımlılıkları sanal ortama kurar ve salt-okunur istemciye ait çevrimdışı self-test gerçekleştirir.

`./.venv/bin/python -m tools.v15_launcher` varsayılan olarak **SHADOW** ve kapalı komutlarla, yalnızca `127.0.0.1:8000` üzerinde sunucu açar. Haricî ağ erişimi sağlanmaz.

`./.venv/bin/python -m tools.v15_launcher --mode SIMULATION --enable-local-sim-commands` yalnızca yerel sentetik model kumandalarını açar. Bu **gerçek yetkilendirme ya da uzaktan güvenli kumanda değildir**.

## Windows

`desktop/build_windows_v15.ps1`, native Windows 10/11 ortamında Python 3.13 ve PyInstaller ile yalnızca **read-only viewer** `.exe` oluşturur. `.exe` FastAPI sunucusunu veya bir tesis kontrol servisinin kendisini içermez. `--self-test` çalıştırılır, PE/MZ kontrolü ve SHA-256 raporu üretilir.

**İmza, Microsoft SmartScreen itibarı, antivirüs taraması, GUI kullanılabilirlik testleri ve hedef Windows sürümleri testi ayrıca gereklidir.** Windows CI artifact çıktısı önizleme niteliğindedir, tesis kontrol ürünü değildir.

## Dağıtım ve sürüm sınırları

- Bağımlılıklar `requirements.txt` ile kurulur; tam reproducible lockfile, SBOM ve bağımlılık güvenlik taraması ayrıca hazırlanmalıdır.
- Veri/üretim `.sqlite3` ve `outputs/`, `.env`, özel anahtarlar ve sanal ortam release ZIP'e girmez.
- SHADOW, dosya/dışa aktarılmış CSV okuyan offline prototiptir; otomatik gerçek tesis bağlantısı kurmaz.
- Tek santrale dahi gerçek kumanda için yetkili mühendislik, OEM test verisi, PLC/SCADA sözleşmesi, HIL, FAT, SAT ve bağımsız korumalar gereklidir.

## GitHub yayın sırası

1. Yerel `pytest -q` ve Linux SHADOW smoke test geçsin.
2. Kaynakları yalnızca doğrulanmış, gizli veri içermeyen hâliyle temiz bir dalda hazırlayın.
3. `.github/workflows/windows-viewer-preview.yml` yayınlandıktan sonra Actions/Run workflow üzerinden Windows derlemesini çalıştırın.
4. İndirilen Windows artifact'ini **gerçek bir Windows 10/11 makinede** GUI ve offline ağ sınırları bakımından kontrol edin.
5. Sonuçları PR'la gözden geçirip `main`e alın. Preview tag/release notlarında güvenlik sınırlarını açıkça belirtin.
6. Gerçek tesis kumandası için ayrıca tesis-bazlı kabul süreci gerekir; bunu GitHub release işlemi kapatmaz.

## Linux taşınabilir izleyici (.pyz)

`python -m tools.build_linux_viewer_v15 --output dist/AutonomousPlantViewer-Linux.pyz`

`python dist/AutonomousPlantViewer-Linux.pyz --self-test` ile ağ/GUI kullanmadan kendi kendini test eder.
Normal çalıştırma: `python dist/AutonomousPlantViewer-Linux.pyz`.
Bu ZIPAPP, Python 3 ve tkinter bulunan Linux'ta çalışır; kendi başına CPython/GUI çalışma zamanı paketlemez.
