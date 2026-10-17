# P03 — Windows kaynak paketi, test ve başlatıcı düzeltmeleri

## Kullanıcı raporunun kök nedeni

- `2 failed, 781 passed` raporu **P01** dizinine aitti (`...UTC_DISPATCH_P01...`).
  P02 ayrı paket olarak hazırlandığından, P01'deki iki `read_text()` çağrısı hâlâ
  Windows `cp1254` varsayılan kodlamasıyla açılıyordu.
- `14_WINDOWS_P02_KODLAMA_TEST.cmd` üzerinde `.venv` yok uyarısı, farklı veya yeni
  klasörde test betiğinin doğrudan çalıştırılmasından kaynaklanabiliyor.
- `00_WINDOWS_BASLAT.cmd` üzerindeki `Incomplete project` uyarısı, kaynak dosyalarının
  tek klasöre tam çıkarılmaması veya `.cmd`'nin farklı sürüm klasöründe açılması
  halinde doğruydu; ancak eski mesaj tanı koymakta yetersizdi.

## P03 düzenlemeleri

- Tam P02 kaynakları, iki testte zaten mevcut olan açık `encoding='utf-8'`
  düzeltmeleri ve fizik motorları aynı şekilde korundu.
- `START_HERE_WINDOWS.cmd`: **tek giriş noktası**. Klasör bütünlüğü, otomatik
  `.venv` hazırlığı, tam regresyon ve yalnızca geçerse masaüstü başlatma.
- `tools/windows_prepare_env.cmd`: her test başlatıcısında ortak, otomatik
  Windows Python 3.13 ve bağımlılık kontrolü. Var olan doğru venv tekrar kurulmaz;
  eksik/yanlış ortam gerektiğinde `--setup-only` ile hazırlanır.
- `10`, `11`, `13`, `14` numaralı Windows komutları eksik venv için anlaşılır
  tanılama yapar, bağımlılık yoksa kurmayı dener ve UTF-8 kipini etkinleştirir.
- `windows/windows_start.py --setup-only` ve `verify_complete_project()` eklendi.
- `00_WINDOWS_BASLAT.cmd` menüsü P03 başlatıcısına bağlandı ve sürüm karışıklığı
  açıkça anlatıldı.
- Platformlar arası başlatıcı ve paket tutarlılığına yönelik test eklendi.

**Sınırlar:** P03 kaynakları Linux'ta test edilmiştir; Windows GUI/EXE bu ortamda
çalıştırılmadı. Yeni fizik, SQLite şeması veya gerçek saha kontrolü iddiası yok.

## Kullanım

`P03_WINDOWS_ILK_KURULUM_TR.txt` dosyasını takip edin. **Eski P01/P02 üzerine
kopyalamayın**; yeni ve boş klasöre *tam P03 ZIP'i* çıkarın.
