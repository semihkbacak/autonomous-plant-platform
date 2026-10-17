# Autonomous Plant Platform v1.5.0-rc.1 — Aday sürüm notları

**DURUM: PRE-RELEASE / SENTETİK SİMÜLASYON.** Gerçek PLC/SCADA, OT, şebeke veya OEM saha kabulü yoktur.

## Yenilikler

- HES, GES ve RES için ortak 15 dakikalık UTC zaman motoru; günlük/saatlik/15 dakikalık sentetik program hedefleri.
- Manuel aktif güç setpoint'i ve fiziksel kullanılabilir güç zarfına göre sınırlandırma; hedef/gerçekleşen/sapma, enerji kWh, operatör ve reddedilmiş komutların SQLite denetim kayıtları.
- Başlat/duraklat/ilerlet akışında oturum yoksa kullanıcı etkileşimiyle oluşturma; yeniden başlatma ve checkpoint geri yükleme.
- Windows için yedek-test discovery izolasyonu, cp1254/UTF-8 testi, eksik `.venv` hazırlığı, eski 8000 port sunucusunun sürüm kontrolü; yeni tek başlangıç dosyası.
- Ölçüme dayalı profil ve normal/hızlı/maksimum sentetik simülasyon hız seçimi.

## Kabul kanıtı ve sınırlamalar

- Daha önceki P01 Windows çıktısı: **781 passed, 2 failed, 1 warning**; iki hata `cp1254` olarak belgelendi ve P02/P03'te kaynak kodda giderildi. P04 ve RC1 tam Windows paketi için bu koşulların yeniden çalıştırıldığı **henüz gösterilmedi**.
- Son P04 Linux seçilmiş regresyon: **522 passed, 7 skipped, 8 deselected**; `pvlib` bağımlı 28 modül bu ortamda toplanamadı. GitHub Actions'ın temiz Windows/Linux tam kabulünü bekle.
- Chromium DOM+JS/FastAPI test istemcisi köprüsüyle START→PAUSE→GES plan→12 kW setpoint→+15 dk→SQLite zinciri geçti; gerçek Windows GUI kabulü değildir.
- HES kontrolü tam hidrolik governor/rezervuar kapalı çevrim yeniden hesaplaması olarak kabul edilmemeli; sentetik güç zarfı sınırlamasıdır.
- Sürüm API işareti `UTC_DISPATCH_P04` kalır; bu, P04 tabanlı RC1 olduğundan bilinçlidir.
- Lisans kararı (`LICENSE_DECISION_REQUIRED.md`) ve OEM araştırma ZIP'inin yeniden dağıtım izni yayın öncesi çözülmelidir.

## Sürüm hazırlama

`release/v1.5-rc1` dalı üzerinde GitHub Actions ve Windows kabulü tamamlanınca `v1.5.0-rc.1` ön sürüm etiketi bu dala bağlanmalıdır. `main` merge edilmemiştir.
