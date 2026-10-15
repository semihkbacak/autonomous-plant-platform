# Tehdit modeli ve erişim sınırı

- API yalnızca `127.0.0.1` veya `::1` üzerinde; gerçek PLC/SCADA veya tesis DMZ bağlantısı yoktur.
- `APP_OPERATION_MODE=SIMULATION` ya da `SHADOW` dışında modu kabul etmeyin. `REAL`/`PRODUCTION` fail-closed olmalıdır.
- `SIMULATION`: sentetik veriler; HES/GES/RES komutları ancak yerel test onayıyla. `SHADOW`: HTTP değiştirici yöntemler kapalı. Var olan v1.2 sınırı korunur.
- `core/v13_security.py` RBAC ve TOTP yalnızca algoritma taslağıdır. Gerçek oturum, IdP doğrulaması, donanım MFA, paylaşılmış replay engeli, lockout, token iptali ve anahtar yönetimi yoktur.
- Eski HES direkt endpoint'lerinin erişim engeli v1.1/v1.2 kurulumundaki `APP_HARDEN_LEGACY=1` ile ayrıca sınanmalıdır; v1.3 o kodu değiştirmez.
- **Mevcut tüm API'ler üretim açısından kimliği doğrulanmamıştır** ve ağa/internete açılmamalıdır. Yeni API'lerin hiçbiri mutasyon endpoint'i içermez.
- Offline CSV veri kaynağı, kalite bayrağı `GOOD` olsa bile kimlik doğrulaması/kalibrasyon kanıtı değildir. Tesis onaylı export imzaları ve kaynak doğrulaması gerekir.
- Konfigürasyon değerlerini kodda tutmayın. Secret, parola, sertifika, erişim belirteçlerini ZIP, Git veya destek loglarına koymayın.
- Kritik kurallar: amaç dışı çalışan hiçbir sistemin güvenlik rölesi/PLC/E-stop üzerine yetkisi olmaz; merkezi uygulama kapansa bile yerel koruma görevde kalmalıdır.
- Güvenlik standartları gereksinim sınıflandırması için ISA/IEC 62443 ve NIST SP 800-82 r3; fonksiyonel güvenlik analizleri için tesise göre ilgili IEC/ISO standardı uzman görüşü gerekir. Standart uyumluluğu sertifikalandırılmış değildir.
