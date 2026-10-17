# Üçüncü taraf materyaller ve dağıtım sınırı — v1.5.0 hazırlığı

- Orijinal proje kaynak kodu için Apache License 2.0 seçilmiştir. Lisans yalnızca hak sahibinin lisanslayabildiği kod ve özgün dokümanlara uygulanır.
- Önceki aday sürümdeki `ges_oem_research.zip` (OEM veri katalogları, analiz Excel/PDF, türev tablolar) **stabil kaynak dalından çıkarılmıştır**. Kamuya dağıtım izni doğrulanmamıştır. Bu, belgelerin lisanslandığı anlamına gelmez.
- GES OEM araştırma köprüsü için arşiv **isteğe bağlı yerel girdidir**. Arşiv bulunmadığında buna bağımlı yedi regresyon testi neden belirtilerek atlanır; modelin doğrulandığı iddia edilmez.
- `data/solar/reference/*.csv` ve diğer örnek materyallerin telif/tedarik zinciri ayrı kaynak bazlı inceleme gerektirir. Üçüncü taraf materyal olduğu doğrulanan dosyalar son stabil sürümden çıkarılmalı veya izin belgesiyle yayımlanmalıdır.
- Eski Git geçmişinde ve `v1.5.0-rc.1` etiketi altında araştırma arşivi **halen erişilebilir olabilir**. Dalda dosyayı silmek geçmişten silmez; geçmişin temizlenmesi/release kaldırılması ayrıca kararlaştırılmalıdır.
- Kullanıcıların paylaştığı harici OEM arşivleri kendi yerel sistemlerinde saklaması mümkündür; depoya commit/push yapmayın.
- Gerçek PLC/SCADA, OT, saha kabulü, IEC uyumu veya OEM sertifikasyonu yapılmış değildir.
