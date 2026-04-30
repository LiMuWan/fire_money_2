# Quant Hunter Stability Test Report

## Summary

- Date: 2026-04-15
- Environment: Windows / PowerShell
- Main runtime: Python 3.13.12
- Compatibility runtime: Python 3.12.10
- Full regression result: 230 tests passed

The current desktop app, core strategy flow, broker execution checks, report export, paper trading loop, cache handling, and CSV fault tolerance are all passing regression in the main runtime.

## Covered Areas

- Strategy and backtest logic
- Daily pool ranking, trade planning, and risk gating
- Broker execution summary and order validation
- Qt startup smoke tests and repeated boot checks
- Paper trading loop and strategy rotation feedback
- Report export and duplicate filename protection
- Cache roundtrip, truncation, and broken payload fallback
- CSV parsing tolerance and mixed-quality universe scans
- Performance smoke checks

## Key Outcomes

- Risk-profile-aware controls are active across recommendation, planning, broker review, and paper trading.
- Strategy rotation now influences recommendation priority and suggested budget sizing.
- Broken CSV files no longer silently block universe loading; scan warnings surface in workspace status and shell pulse.
- Report and paper-trading exports use unique filenames to avoid accidental overwrite.
- Performance diagnostics now include Qt boot breakdown metrics.

## Performance Baseline

See [perf_baseline_2026-04-15.json](/C:/Users/18335/Documents/New%20project/docs/perf_baseline_2026-04-15.json).
See [PERF_COMPARISON_2026-04-15.md](/C:/Users/18335/Documents/New%20project/docs/PERF_COMPARISON_2026-04-15.md).

Current representative baseline:

- Pipeline with 10 files: scan 4.82ms, recommend 3.54ms, export 4.83ms
- Pipeline with 100 files: scan 41.01ms, recommend 4.39ms, export 8.98ms
- Pipeline with 500 files: scan 207.13ms, recommend 21.08ms, export 28.73ms
- Qt boot: about 1.07s to 1.26s in repeated samples
- Qt boot breakdown: `build_ui` about 119ms, `post_build` about 360ms

## Remaining Notes

- Qt startup remains the clearest optimization target.
- The main cost center in boot diagnostics is still the post-build polish chain.
- Future performance work should compare against the JSON baseline before and after each optimization pass.
