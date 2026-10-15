"""Run offline synthetic validator matrix and optionally compare one local CSV."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from app.engineering_core import generate_fault_matrix
from app.engineering_coverage import coverage
from app.engineering_shadow import compare_file


def main() -> int:
    parser = argparse.ArgumentParser(description='Offline research/software-readiness check (no OT connections)')
    parser.add_argument('--csv', type=Path, default=None)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    matrix = generate_fault_matrix()
    report = {
        'scope': 'SYNTHETIC_SOFTWARE_VALIDATION_NOT_FIELD_READY',
        'quality_matrix': matrix,
        'coverage': coverage(),
        'csv_comparison': compare_file(args.csv) if args.csv else {'status': 'NOT_SUPPLIED'},
        'software_quality_matrix_passed': all(item['passed'] for item in matrix),
        'oem_validation_passed': False,
        'field_validation_passed': False,
        'ot_security_certification_passed': False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print('ENGINEERING QA:', 'PASSED' if report['software_quality_matrix_passed'] else 'FAILED')
    print('EXTERNAL/OEM/FIELD: NOT VERIFIED')
    print('Report:', args.report)
    return 0 if report['software_quality_matrix_passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
