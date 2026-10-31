"""Bounded per-file pytest audit; no mutation of production source."""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--timeout', type=int, default=65)
    parser.add_argument('--start-at', default='', help='Optional test filename to resume from')
    args = parser.parse_args()
    base = Path(__file__).resolve().parent
    test_files = sorted((base / 'tests').glob('test_*.py'))
    if (base / 'test_calculator.py').exists():
        test_files.append(base / 'test_calculator.py')
    if args.start_at:
        test_files = [p for p in test_files if p.name >= args.start_at]
    results = []
    out_path = base / 'full_regression_by_file.json'
    for file in test_files:
        name = str(file.relative_to(base))
        started = time.monotonic()
        try:
            process = subprocess.run(
                [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', name],
                cwd=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace', timeout=args.timeout,
            )
            status = 'passed' if process.returncode == 0 else 'failed'
            output = process.stdout or ''
            returncode = process.returncode
        except subprocess.TimeoutExpired as exc:
            status, returncode = 'timeout', None
            output = exc.stdout or b''
            if isinstance(output, bytes):
                output = output.decode('utf-8', errors='replace')
        result = {
            'file': name, 'status': status, 'seconds': round(time.monotonic()-started, 2),
            'returncode': returncode, 'output_tail': output[-2500:],
        }
        results.append(result)
        report = {
            'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'timeout_per_file_seconds': args.timeout,
            'scope': 'test_*.py in tests/ and test_calculator.py',
            'results': results,
            'all_passed': bool(results) and all(r['status'] == 'passed' for r in results),
            'note': 'Some tests may have side effects in their temporary workspaces; inspect failed cases.',
        }
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"{status:7} {result['seconds']:7.2f}s {name}", flush=True)
    lines = ['# 全项目分文件回归记录', '',
             f"总体：{'PASS' if report['all_passed'] else 'INCOMPLETE / FAIL'}", '',
             '| 测试文件 | 状态 | 用时 (s) |', '|---|---|---:|']
    lines += [f"| `{r['file']}` | {r['status']} | {r['seconds']} |" for r in results]
    (base / 'full_regression_by_file.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Saved full_regression_by_file.json and full_regression_by_file.md')
    return 0 if report['all_passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
