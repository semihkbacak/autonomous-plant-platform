# Geliştirme dalı yayın protokolü (henüz UYGULANMADI)

Depo: `semihkbacak/autonomous-plant-platform`. `main` korunsun; ZIP mevcut GitHub `main` sürümünden belirgin ileri olduğu için doğrudan üzerine kopyalanması uygun değildir.

Önerilen ayrı dal: `development/utc-dispatch-p01`. Bu teslim, onaydan önce **hiçbir GitHub ref/commit değiştirmez**. Yalnızca zip ve dosya farkı/patch hazırlanır. Windows kabulü sonrası bağımsız clone içinde:

```bash
git clone https://github.com/semihkbacak/autonomous-plant-platform.git
cd autonomous-plant-platform
git switch main
git pull --ff-only
git switch -c development/utc-dispatch-p01
# Kök kaynak ZIP içindeki dosyaları çalışma ağacına kontrollü aktarın.
# Geçerli main'deki özel dosyalar incelenmeden silinmemeli.
python -m pytest -q tests
# Yalnızca Windows QA onayını aldıktan sonra:
git add -A
git commit -m "Add UTC synthetic dispatch, audited controls and cross-platform discovery isolation"
git push -u origin development/utc-dispatch-p01
```

PR açılmadan önce CI'nin Windows ve Linux tam regresyonlarını geçmesi, manifestlerin kontrolü, açık kaynak/lisans ve OEM iddialarının gözden geçirilmesi gereklidir. **Bu komutlar bu teslim için çalıştırılmamıştır.**
