@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Autonomous Plant Platform - RC1 GitHub Publication

echo =============================================================
echo Autonomous Plant Platform v1.5.0-rc.1 - Aday Surum Yayini
echo Hedef: release/v1.5-rc1 ^| main degistirilmez.
echo =============================================================
echo.
where git >nul 2>&1 || (echo HATA: Git for Windows kurulu degil. & pause & exit /b 1)
where gh >nul 2>&1 || (echo HATA: GitHub CLI kurulu degil. Kurmak icin: winget install GitHub.cli & pause & exit /b 1)
where py >nul 2>&1
if not errorlevel 1 (set "PY=py -3") else (where python >nul 2>&1 || (echo HATA: Python bulunamadi. & pause & exit /b 1) & set "PY=python")

echo [1/4] GitHub kimlik dogrulamasi...
gh auth status || (echo Once gh auth login ile GitHub'a giris yapin. & pause & exit /b 1)
gh auth setup-git || (echo HATA: Git kimlik kurulumu basarisiz. & pause & exit /b 1)
echo.
echo [2/4] Kaynak butunlugu, main ve dal guvenligi kontrol ediliyor...
%PY% scripts\release\publish_rc1.py --dry-run
if errorlevel 1 (echo HATA: Onizleme basarisiz. Kod yuklenmedi. & pause & exit /b 1)
echo.
echo [3/4] Sadece release/v1.5-rc1 dalina kod gonderimi...
%PY% scripts\release\publish_rc1.py --publish
if errorlevel 1 (echo HATA: Dal gonderimi basarisiz. Release olusturulmadi. & pause & exit /b 1)
echo.
echo [4/4] GitHub on surum kaydi aciliyor...
gh release view v1.5.0-rc.1 --repo semihkbacak/autonomous-plant-platform >nul 2>&1
if not errorlevel 1 (echo HATA: Bu surum etiketi zaten var. Yeni release olusturulmayacak. & pause & exit /b 1)
gh release create v1.5.0-rc.1 --repo semihkbacak/autonomous-plant-platform --target release/v1.5-rc1 --title "Autonomous Plant Platform v1.5.0-rc.1 - Synthetic Research Candidate" --notes-file RC1_RELEASE_NOTES_TR.md --prerelease --latest=false
if errorlevel 1 (echo HATA: Kod dali gonderildi ama GitHub Release olusturulamadi. & echo https://github.com/semihkbacak/autonomous-plant-platform/releases/new & pause & exit /b 1)
echo.
echo BASARILI: RC1 dal ve on surum olusturuldu.
echo https://github.com/semihkbacak/autonomous-plant-platform/releases/tag/v1.5.0-rc.1
echo.
echo NOT: Windows/Linux CI sonuclari ve lisans / OEM haklari hala kontrol edilmelidir.
pause
