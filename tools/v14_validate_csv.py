"""Offline observational holdout screening; never OEM/site certification.

python -m tools.v14_validate_csv --csv data.csv --report report.json
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from core.v14_model_validation import validate_csv


def main() -> int:
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--csv',type=Path,required=True)
    a.add_argument('--report',type=Path,required=True)
    args=a.parse_args()
    if args.csv.resolve()==args.report.resolve():
        a.error('CSV and report cannot be same path')
    report=validate_csv(args.csv)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    if args.report.is_symlink():
        a.error('Refusing to overwrite symlink report')
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'groups':len(report['groups']),'screening_passed':report['all_quality_screens_passed'],
                      'site_validated':report['site_validated'], 'report':str(args.report)},ensure_ascii=False))
    # A completed scientific assessment can still yield a failed metric; exit 2.
    return 0 if report['all_quality_screens_passed'] else 2

if __name__=='__main__':raise SystemExit(main())
