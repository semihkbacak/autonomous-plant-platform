# Autonomous Plant Platform — v1.5.0 stable candidate (source review)

> **Stable candidate, pending final review; not production-grade plant control.** HES/GES/RES only in local synthetic SIMULATION mode. No actual PLC/SCADA, OEM certification, site acceptance, grid-connected control, or production-readiness claim.

**Windows:** Install Python 3.13, extract the complete source tree, run `START_HERE_WINDOWS.cmd`. Subsequent startup: `P04_HIZLI_BASLAT_WINDOWS.cmd`. The shared UTC/dispatch UI is at `http://127.0.0.1:8000/platform/synchronized`. The service build marker remains `UTC_DISPATCH_P04` because this candidate is a versioned packaging of the P04 implementation, not a physics rewrite.

**GitHub:** Use `RC1_GITHUB_ONIZLE.cmd` to preview changes and `RC1_GITHUBA_GONDER.cmd` to push **only** `release/v1.5-rc1`. A `git` CLI and GitHub authentication are required. The script will never push or rewrite `main`. See [RC1_GITHUB_YAYIN_REHBERI_TR.md](RC1_GITHUB_YAYIN_REHBERI_TR.md).

**Quality evidence:** Last user-reported Windows run on earlier P01: 781 passed, 2 failed due to default cp1254 text encoding. That defect was fixed in P02/P03. P04 Linux selected regression: 522 passed, 7 skipped, 8 deselected, and additional pvlib-dependent modules were unavailable in the container. Browser JS/API/SQLite interaction was verified via a FastAPI bridge; **complete native Windows RC1 acceptance is still pending.** Check CI on the RC branch and the Windows GUI before considering publication.

**Licensing:** Original project code and project-authored materials owned by the copyright holder are offered under Apache-2.0 (see `LICENSE` and `NOTICE`). Third-party dependencies retain their respective licenses. The optional private research archive `ges_oem_research.zip` is excluded from public source and is never required for standard installation; see `docs/THIRD_PARTY_MATERIALS_TR.md`. Earlier tagged releases and Git history may still contain copies and require separate review.

## P04 implementation notes (retained)

# P04 — Quick start / HES + GES + RES sentetik UTC paneli

**Windows ilk çalıştırma:** Yeni ve boş bir klasöre P04 TAM kaynak ZIP’ini tamamen çıkarın. Daha önceki P01, P02, P03 klasörlerine yama kopyalamayın. Eski 127.0.0.1:8000 sunucularını normal biçimde kapatın. `START_HERE_WINDOWS.cmd` dosyasını çalıştırın. İlk kurulum bağımlılıkları hazırlar, tam pytest regresyonunu çalıştırır ve masaüstü arayüzünü başlatır. Masaüstündeki **HES/GES/RES · UTC synchronized** düğmesiyle üretim panelini açın.

**Sonraki açılışlar:** `P04_HIZLI_BASLAT_WINDOWS.cmd` (kurulu venv ile hızlı başlatma). **Sadece kabul testleri:** `P04_KABUL_TEST_WINDOWS.cmd`. Sunucu sürümü doğrulaması: `http://127.0.0.1:8000/api/v2/clock/build` yanıtındaki `build` alanı `UTC_DISPATCH_P04` olmalı.

**Panel:** İlk açılışta `NOT_CREATED` bir bozukluk değildir; oturum henüz oluşturulmamıştır. P04 panelinde `Otomatik başlat`, `+15 dk` veya üretim planı/setpoint işlemleri ilk kullanıcı tıklamasında gerekirse oturumu oluşturur. `Yeni oturum / sıfırla` mevcut aktif simülasyonu değiştirir ancak eski oturum geçmişini silmez. Sentetik mod dışında POST komutları reddedilir. HES/GES/RES fiziksel üst sınırlarını aşan güç üretilmiş gibi gösterilmez. Bu katman sahada PLC/SCADA kontrolü veya OEM doğrulaması DEĞİLDİR.

**Önemli doğrulama sınırı:** P04 burada Linux üzerinde API/SQLite testleri ve Chromium UI JavaScript + FastAPI test istemcisiyle doğrulandı. Gerçek Windows GUI ve tam Windows bağımlılıkları bu ortamda çalıştırılmadı; Windows kabulü ayrıca gereklidir.

---

# Autonomous Plant Platform — P03 Windows/Linux tam kaynak

**Windows için tek giriş dosyası: `START_HERE_WINDOWS.cmd`.** Tam P03 ZIP içeriğini eski P01/P02 dosyalarıyla karıştırmadan **yeni boş bir klasöre** çıkarın. Windows Python 3.13 gerekir. Başlatıcı, kaynak bütünlüğünü kontrol eder, gerekli `.venv` ortamını kurar/denetler, tam pytest regresyonunu çalıştırır ve yalnızca başarı halinde sentetik masaüstü simülatörünü başlatır. Yalnız test için `10_WINDOWS_ASAMA2_5_TEST.cmd`. Rehber: `P03_WINDOWS_ILK_KURULUM_TR.txt`; değişiklikler: `P03_WINDOWS_DUZELTME_OZETI.md`. Windows P03 kabulü henüz kullanıcı tarafından doğrulanmamıştır; GUI/EXE sertifikasyonu yoktur.

---

## Önceki sürüm notları (tarihsel)

> **P02 (17 Oct 2026):** Windows cp1254/UTF-8 test portability hotfix; on Windows use `14_WINDOWS_P02_KODLAMA_TEST.cmd`, then `10_WINDOWS_ASAMA2_5_TEST.cmd`. See `docs/WINDOWS_UTF8_P02_QA_TR.md`. Windows P02 acceptance pending.

# Autonomous Plant Platform — Aşama 1–5 Birleşik Sentetik Araştırma Sürümü

> **Mevcut Aşama 1/FIX11.1 korunmuştur.** Aşama 2–5 için ayrı, sürümlenmiş `advanced_v2` fizik/karar destek modülleri ve yerel panel eklendi. **Yalnızca SENTETİK SİMÜLASYON.** OEM kalibrasyonu, gerçek tesis bağlantısı veya güvenlik sertifikası değildir.

**Kullanım:** `ASAMA_1_5_KULLANIM_VE_KAPSAM_TR.md` · Windows: `10_WINDOWS_ASAMA2_5_TEST.cmd` ve `11_WINDOWS_ASAMA2_5_AC.cmd` · Linux: `10_LINUX_ASAMA2_5_TEST.sh` ve `11_LINUX_ASAMA2_5_BASLAT.sh`.

**Yeni panel:** `http://127.0.0.1:8000/platform/advanced-twins` — GES I–V/MPPT, RES pitch/yaw/rotor, HES governor/rezervuar, ortak karar destek, çok günlük SQLite ve UTC kaydı. Eski `/platform/synchronized` paneli ayrıca korunmuştur.

---

**FIX8 Windows desktop preflight patch:** [README_WINDOWS_FIX8_TR.md](README_WINDOWS_FIX8_TR.md).

**FIX7 Windows SQLite / EXE build fixes:** [README_WINDOWS_FIX7_TR.md](README_WINDOWS_FIX7_TR.md).

**FIX6 — Windows EXE / GES–RES canlı sentetik ikiz düzeltmesi:** [README_WINDOWS_FIX6_TR.md](README_WINDOWS_FIX6_TR.md). Önceki EXE ve ZIP içinden çalıştırılan kaynaklarla karıştırmayın.

> **Important:** v2.0 RC4 research candidate. Signed Windows EXE, OEM/site measurements, licensed publishing and independent safety acceptance are NOT completed. Read `00_WINDOWS_RC4_OKU.txt` and `docs/V20_RC4_RELEASE_AND_FIELD_EVIDENCE_TR.md`. NEVER run CMD from inside ZIP preview.

# Autonomous Plant Platform

> **Stage 1 addition — synchronized HES/GES/RES UTC portfolio**: `ASAMA1_KULLANIM_VE_DOGRULAMA_TR.md` · dashboard `/platform/synchronized` · 15-minute native-model steps, multi-day SQLite journal and crash-safe restore. Synthetic simulation only.
 — v2.0 Engineering RC4 (synthetic research)

**HES + GES + RES | Windows/Linux local synthetic simulation, offline research, source-code preview**

> **Release status:** v2.0 RC4 synthetic research preview — not production software.
> **NOT FOR REAL-TIME OT CONTROL.** No production PLC/SCADA command channel, field acceptance, OEM certification, or unattended plant-control approval is included.

**RC4 local engineering checks:** 689 passed, 2 scikit-learn cross-version warnings (Linux CPython 3.13.5). New HES/GES/RES paused synthetic checkpoints, deterministic model configuration locking, SQLite backup/restore, native-Windows EXE smoke-test workflow and SBOM/pip-audit workflow. **New Windows/GitHub checks have not yet been run.** See `docs/V20_RC4_RELEASE_AND_FIELD_EVIDENCE_TR.md`.

[![Windows viewer preview](https://github.com/semihkbacak/autonomous-plant-platform/actions/workflows/windows-viewer-preview.yml/badge.svg)](https://github.com/semihkbacak/autonomous-plant-platform/actions/workflows/windows-viewer-preview.yml)

## Overview / Genel bakış

Autonomous Plant Platform explores a modular, vendor-independent software architecture for **hydroelectric (HES), photovoltaic (GES), and wind (RES)** energy systems. A single FastAPI service provides synthetic simulators, read-only analytics, historical scenario reports and development-oriented interfaces.

Bu proje, hidroelektrik, güneş ve rüzgâr enerji santralleri için üretici bağımsız bir **sentetik simülasyon ve karar destek araştırma platformudur**. Gerçek bir tesisi devralmaz; saha kumandası veya bağımsız elektriksel/mekanik koruma sistemi değildir.

## What is implemented / Mevcut yazılım kapsamı

| Plant | Simulator and research coverage |
|---|---|
| HES | Two-unit hydro simulator, state machine, governor/dispatch, safety checks, alarms, historical scenarios, synthetic research models |
| GES | Synthetic PV/inverter/MPPT simulation, shading and AC/P-Q analysis, scenarios, historian and research/validation tools |
| RES | Synthetic wind generation simulation, turbine scenarios, historian, research models for pitch/yaw and fault injection |
| Shared | FastAPI, dashboards, centralized synthetic alarms, engineering diagnostics, offline CSV-based SHADOW analysis, test suite |

These are software capabilities, **not** claims of OEM-level digital-twin fidelity or operational safety certification. The three simulators do not imply a common synchronized physical clock.

## Installation — Windows / Linux (local simulation)

**Python 3.13 recommended**, test suite snapshots: Linux 662 passed, user-reported Windows FIX2 all panels opened; Windows final regression count should be confirmed by local report. Other versions may require additional testing. No real PLC, SCADA or OT network integration is authorized.

### Windows (PowerShell/CMD, Python 3.13 installed)

From the extracted project folder, launch `01_WINDOWS_KUR_TEST_VE_BASLAT.cmd` to install dependencies, run the full test suite, and start a localhost-only server. Alternatives: `02_YALNIZ_TEST.cmd` for test-only and `03_TESTSIZ_BASLAT.cmd` for subsequent quick launches. The GUI viewer is read-only.

### Linux (Bash, Python 3.13 recommended)

```bash
bash 01_LINUX_KUR_TEST_VE_BASLAT.sh
# or run tests without starting a server:
bash 02_LINUX_YALNIZ_TEST.sh
# or start after dependencies are already installed:
bash 03_LINUX_TESTSIZ_BASLAT.sh
```

### Manual / developers

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q --assert=plain -x
.venv/bin/python -m tools.v15_launcher --mode SIMULATION --enable-local-sim-commands
```

For Windows use `.\.venv\Scripts\python.exe` in place of `.venv/bin/python`.

The launcher binds to `127.0.0.1:8000` only. It must not be exposed to a public network or to an OT network. The Windows preview viewer expects port 8000.

## Interfaces / Arayüzler

With the server running locally:

- [Unified dashboard](http://127.0.0.1:8000/platform/dashboard)
- [Synthetic alarms](http://127.0.0.1:8000/platform/alarms)
- [Engineering diagnostics](http://127.0.0.1:8000/platform/engineering)
- [SHADOW/site preparation](http://127.0.0.1:8000/platform/site-transition)
- [Research / evidence](http://127.0.0.1:8000/platform/research)
- [API Developer Center](http://127.0.0.1:8000/docs)

These URLs refer to a server running on **your own computer**. A SHADOW mode screen does not imply a live site connection.

## Windows viewer preview

The Windows preview is a **read-only viewer**, **not** the complete plant simulator or a plant-control application. It queries the local FastAPI service and does not create a remote OT connection.

A native Windows environment (or the `windows-viewer-preview.yml` GitHub Actions workflow) can build the unsigned preview:

```powershell
powershell -ExecutionPolicy Bypass -File desktop\build_windows_v15.ps1
```

The produced executable is checked with an offline self-test and SHA-256 report. GUI usability, code signing, malware screening and target Windows releases require additional validation before external distribution.

## Scientific and site-validation status / Gerçek tesis sınırı

The research models and validation tools do **not** replace:

- Manufacturer-approved component curves, control logic and limits
- Authorized plant data, site-specific calibration and uncertainty assessment
- Hydraulic transients, electrical protection and aeroelastic validation as applicable
- Independent OT safety systems, safe failure modes and authorized engineering review
- Cybersecurity architecture and tested access controls in a site-specific environment
- Hardware-in-the-loop tests, factory/site acceptance tests (FAT/SAT) and supervised pilot operation

No real-plant control or autonomous unattended operation is authorized by this repository. See `docs/RELEASE_GATES_TR.md`, `docs/SECURITY_AND_OT_BOUNDARY_TR.md`, and `docs/LITERATUR_TARAMASI_TR.md` for evidence requirements and references.

## Release assets and contribution requirements

The repository must track the five explicitly allow-listed test inputs, despite the default exclusion of `data/`, `outputs/` and `*.zip`. Run `python scripts/verify_release_assets.py` after every fresh clone. Do not push personal or production data. See `RELEASE_GITHUB_WINDOWS_LINUX_TR.md` for the reviewed staging workflow.

## Project layout

```text
app/             FastAPI APIs and UI
core/            shared research, security and validation primitives
simulator/       synthetic hydro, PV and wind models
tests/           automated regression tests
tools/           launchers and offline engineering utilities
desktop/         read-only viewer and Windows packaging
scripts/         local helper scripts
examples/        synthetic example datasets
docs/            release gates, literature and engineering limitations
.github/         preview CI workflows
```

Generated `outputs/` (except a single reviewed static audit JSON), SQLite historians, secrets, local configuration, and virtual environments must not be committed. The research archive `ges_oem_research.zip` is allow-listed for repeatable offline tests but requires explicit third-party rights review before public redistribution.

## Testing and contributions

Before submitting a PR:

```bash
python -m pytest -q --assert=plain -x
git diff --cached --check
```

A contributor-reported local development snapshot passed **662 automated tests** (2026-10-15). This is a historical snapshot, **not** a guarantee that every future commit, operating system or installation passes. Review GitHub CI results for each new commit.

Please submit changes through a review branch/PR. Label synthetic examples clearly and never include plant credentials, real production telemetry or proprietary OEM documents without appropriate rights.

## License / Lisans

**License has not yet been declared in this repository.** All code and third-party data must be reviewed for ownership and compatible redistribution rights before commercial or public packaged distribution. GitHub public visibility by itself does not grant third-party reuse permission.

## Experimental v2.0 research preview

This workspace contains optional local research APIs under `/api/v2/research`, a basic desktop launcher and CSV/SQLite offline analysis. This is an **experimental work-in-progress**, not the completed production milestones. See `docs/V20_DELIVERY_AND_LIMITATIONS_TR.md`.

## RC4 FIX5 — GES historian / Windows EXE build

On first launch, the GES historian-backed MPPT dashboard requires historical SQLite
rows. FIX5 creates an explicitly **synthetic four-interval** demo historian only
when no `GES_HISTORIAN_DB` environment variable is set and no default demo file
exists. Other existing databases are never overwritten. For manual installation
on Windows run `07_GES_ORNEK_GECMIS_OLUSTUR.cmd`, then restart the server.

To build the unsigned Windows simulator folder run `06_WINDOWS_TAM_EXE_DERLE.cmd`.
The log is saved as `WINDOWS_EXE_DERLEME_RAPORU.txt`. Output is
`dist/AutonomousPlantSimulatorV20/AutonomousPlantSimulatorV20.exe`, which **must
stay with its `_internal` folder**. The script pauses after completion and
attempts to create a Desktop shortcut after successful native `--self-test`.
See `README_WINDOWS_GES_FIX5_TR.md` for Turkish instructions and limitations.

FIX5 was regression-tested on Linux / CPython 3.13: **693 passed, 2 warnings**
(the local scikit-learn 1.8.0 did not match the bundled model's 1.9.1).
Native Windows EXE build, GUI interactions, signing and hardware/site validation
are not certified by these tests. This is local synthetic research software only.

## FIX11: Windows packaged SQL resource repair

FIX10 could build but the packaged executable omitted `simulator/solar/ges_history_schema.sql`.
FIX11 includes and SHA-256-verifies this resource before marking the native Windows EXE build successful.
See [`README_WINDOWS_FIX11_TR.md`](README_WINDOWS_FIX11_TR.md) for a no-rebuild FIX10 hotfix and clean FIX11 build instructions.
This is a **synthetic simulator**; a Windows GUI acceptance check is still required.

## UTC production scheduling / sentetik üretim planı — development P01

The current development package adds a **synthetic-only, bounded export-dispatch envelope** over the Stage 1 synchronized portfolio. Open `/platform/synchronized` for 15-minute/hourly/daily UTC production targets, per-plant kW/MW manual setpoints, synthetic STOP/START/AUTO, scenario availability limits, SQLite audit history and Normal/Fast/Max simulation pacing.

**Do not confuse this with actual PLC/SCADA setpoint control or closed-loop hydro dispatch.** The underlying native hydro mechanical state is not recomputed to match curtailed exported power. OEM validation and field acceptance remain outstanding.

- Architecture, models, formulae, limitations: `docs/UTC_DISPATCH_ENGINEERING_REVIEW_TR.md`
- Linux regression and required Windows acceptance: `WINDOWS_KABUL_VE_TEST_RAPORU_2026-10-17.md`
- Existing legacy repair backup folders are ignored by `pytest.ini`; new backups can be made with `12_WINDOWS_GUVENLI_ONAR_YEDEGI.cmd` outside project root.
- Development branch and main-safe GitHub publishing instructions: `GIT_BRANCH_PREP_TR.md`
