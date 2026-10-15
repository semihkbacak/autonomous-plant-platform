# Autonomous Plant Platform v1.4 araştırma/kanıt güncellemesi

Mevcut HES/GES/RES simülatörlerini, canlı simülasyon API'lerini, alarm/historian ve veritabanlarını değiştirmez.

1. `cd /run/media/semih/Others-Partition/Projects/autonomous-plant-platform`
2. `source .venv/bin/activate`
3. `unzip -q ~/Downloads/Autonomous_Plant_Platform_v14_Research_Validation.zip -d ~/Downloads/plant_v14`
4. `python ~/Downloads/plant_v14/autonomous_plant_upgrade_v14/install.py --project "$PWD"` (**yalnızca dry-run**)
5. `python ~/Downloads/plant_v14/autonomous_plant_upgrade_v14/install.py --project "$PWD" --apply`
6. `python -m pytest tests/test_research_validation_v14.py -q --assert=plain -x`
7. `python -m pytest -q --assert=plain -x`
8. SHADOW: `APP_OPERATION_MODE=SHADOW APP_HARDEN_LEGACY=1 APP_SIM_CONSOLE_WRITES=0 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
9. Aç: `http://127.0.0.1:8000/platform/research`
10. Örnek sentetik CSV: `python -m tools.v14_validate_csv --csv examples/v14_synthetic_measurements.csv --report "$HOME/plant-v14-example-screen.json"`

**Aynı ZIP'i ikinci kez uygularsan dosyalar aynıysa SKIP edilir, farklıysa çakışma hatası alınır.** `app/main.py` önce yedeklenir. Bu işlemler gerçek OT bağlantısı oluşturmaz.

`docs/LITERATUR_TARAMASI_TR.md` kaynakça ve araştırma/kullanım sınırlarını içerir.
