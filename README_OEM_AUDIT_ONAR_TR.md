# Aşama 1-5 Windows OEM audit veri onarımı

Sorun: Eski Windows başlatıcısı, geçmiş araştırma raporu `outputs/ges_oem_shadow_v05/oem_shadow_audit.json` çıkarılmış klasörde yoksa bütün kurulumu durduruyordu.

Bu sürümde rapor eksikse aynı orijinal baytlar kod içindeki SHA-256 denetimli yedekten atomik olarak geri yüklenir. Var olan ama değiştirilmiş dosyalar **üzerine yazılmaz**. Diğer 4 veri dosyasının hash kontrolü aynen sürer.

Ayrıca `00_WINDOWS_BASLAT.cmd` menüsündeki **1** komutu artık yalnızca test yapan `02_YALNIZ_TEST.cmd` yerine kurulum yapan `01_WINDOWS_KUR_TEST_VE_BASLAT.cmd` dosyasına yönlenir.

İlk kullanım: ZIP'i bütünüyle ayrı klasöre çıkar. `00_WINDOWS_BASLAT.cmd` çalıştır. Var olan ortamı korumak için küçük onarım ZIP'ini ayrıca kullanabilirsin.

Fizik modelinin OEM/saha onayı yoktur. Dosya gerçek üretim verisi değildir. GitHub'a yükleme yapılmamıştır.
