# v1.5.0-rc.1 — GitHub'a güvenli yayın rehberi

**Temel dal:** `main` (dokunulmayacak). **Hedef dal:** `release/v1.5-rc1` (yeni aday).
**Aday kaynak:** P04 sentetik UTC/dispatch sürümü, mevcut fizik çekirdeği ve geçmiş kayıtları korunur.

## 1. GitHub'a kaynak olarak gönderme

Bu ZIP'i GitHub Releases'e yüklemek **kaynak dosyalarını repoya eklemez**. Önce ZIP'i yeni bir klasöre tamamen çıkar. `Git for Windows` kurulu olsun ve GitHub üzerinde push yetkin olduğundan emin ol. Bilgisayarında eski sunucuları kapatmana gerek yoktur; yükleyici hiçbir çalışan sunucuya bağlanmaz.

1. **Tek adımda dal + GitHub ön sürüm:** Git for Windows ve GitHub CLI (`gh`) kurup `gh auth login` yaptıktan sonra `RC1_TEK_TIK_YAYIN_WINDOWS.cmd` çalıştır. Alternatif olarak yalnızca dal göndermek için aşağıdaki eski adımları uygula.
2. `RC1_GITHUB_ONIZLE.cmd` ile karşılaştırmayı incele. Bu komut **hiçbir şey göndermeden** dosya sayısını ve değişiklik özetini gösterir.
3. `RC1_GITHUBA_GONDER.cmd` çalıştır; özet sonrası istenen `YUKLE` onayını ver. Sadece `release/v1.5-rc1` dalını oluşturur/yükler. `main` dalına push, force-push, tag veya release oluşturma yapmaz.
4. GitHub deposunda **Actions → Cross-platform simulation regression** altında Windows + Linux sonuçlarını bekle. Diğer Stage 1–5 workflow'u PR üzerinde de çalışır.
5. Bu dal → `main` için PR açılabilir ancak testler, Windows tıklama kabulü ve lisans kontrolü tamamlanmadan **merge yapma**.

Manuel eşdeğeri: GitHub deposunu `main`'den klonla; yeni bir `release/v1.5-rc1` dalına geç; bu ZIP'deki kaynakları klona aktar; `git add -A`, `git diff --cached`, `git commit`, `git push -u origin release/v1.5-rc1`. **Eski main dosyalarıyla karışma riskini önlemek için hazır aracı kullanman önerilir.**

## 2. Aday sürüm (GitHub Releases)

Dal üzerindeki CI + Windows kabulü geçtikten sonra GitHub → Releases → Draft a new release:

- Tag: `v1.5.0-rc.1` (henüz yoksa oluştur)
- Target: `release/v1.5-rc1` (kesinlikle `main` değil)
- Başlık: `Autonomous Plant Platform v1.5.0-rc.1 — Synthetic research candidate`
- `Set as a pre-release` işaretle. Ön sürüm notlarını `RC1_RELEASE_NOTES_TR.md` dosyasından al.
- Kaynak ZIP'i yalnızca gerekli dağıtım haklarını doğruladıktan sonra ekle. **OEM araştırma arşivindeki üçüncü taraf materyallerin dağıtımı izne tabi olabilir.**

## Doğrulama sınırları

P04 yerel Linux bağımlılıklarının mevcut olduğu kümede 522 geçti, 7 atlandı, 8 hariç tutuldu; native Windows P04 tam kabul **doğrulanmadı**. API sürüm işareti `UTC_DISPATCH_P04` olarak kalır; bu normaldir. Gerçek saha ve OEM onayı yoktur.

## Sorun giderme

- `git: command not found` → Git for Windows yükle, yeni CMD aç.
- `Authentication failed` → Git Credential Manager veya `gh auth login` ile giriş yap.
- `main HEAD changed` → Dal hazırlama durdurulur; yeni main'i karşılaştırmadan otomatik merge yapma.
- `branch already exists` → Dal yalnızca `main` ile tam aynı SHA üzerindeyse güvenli fast-forward yapılır. Dalda farklı commit varsa işlem durdurulur; force-push yapılmaz.
- PowerShell/CMD'yi ZIP önizlemesinden çalıştırma, tüm klasörü çıkar.
