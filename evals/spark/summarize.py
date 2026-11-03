#!/usr/bin/env python3
"""Summarize synthetic results without leaking internal reasoning or user data."""
import argparse
import collections
import json
import math
from pathlib import Path
import statistics


def summarize(path):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    cases = [r for r in rows if r['type'] == 'case']
    domains = {}
    for domain in sorted({r['domain'] for r in cases}):
        selected = [r for r in cases if r['domain'] == domain]
        domains[domain] = {'passed': sum(r['passed'] for r in selected), 'total': len(selected),
                           'median_case_seconds': statistics.median(r['case_seconds'] for r in selected) if all('case_seconds' in r for r in selected) else None}
    timings = [m for r in cases for m in r['metrics']]
    def median(field):
        values = [t[field] for t in timings if t.get(field) is not None]
        return statistics.median(values) if values else None
    return {'run': rows[0], 'complete': rows[-1]['type'] == 'end' and rows[-1].get('completed') is True,
            'total': len(cases), 'passed': sum(r['passed'] for r in cases), 'domains': domains,
            'failures': [{'id': r['id'], 'reason': r['reason']} for r in cases if not r['passed']],
            'median_visible_ttft_seconds': median('visible_ttft_seconds'),
            'median_request_seconds': median('seconds'),
            'p95_request_seconds': sorted(t['seconds'] for t in timings)[max(0, math.ceil(len(timings)*.95)-1)] if timings else None,
            'median_decode_tokens_per_second_estimate': median('decode_tokens_per_second_estimate'),
            'median_completion_tokens_per_total_second': median('completion_tokens_per_total_second'),
            'min_available_gib': min((r['min_available_gib'] for r in cases), default=None)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', type=Path, nargs='+')
    args = parser.parse_args()
    print(json.dumps([summarize(p) for p in args.paths], indent=2))
