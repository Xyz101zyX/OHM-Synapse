# OHM-Synapse — Design & Operator's Guide

**Version:** 0.0.3
**Date:** 2026-09-19
**Status:** All 12 phases green. Zero open debts.
**Audience:** Anyone starting on this project (including myself in a month).

---

## §0 — How to use this document

This is the project manual. It answers three questions:

1. **What is** OHM-Synapse and why does it exist (§1)
2. **How to run** it from scratch and day to day (§2, §3)
3. **What works** and what broke before (§4, §6)

If you are returning to the project after time away:

```bat
python journey.py       :: state of the 12 phases
python check_all.py     :: syntax + mypy + imports
python run_tests.py     :: 230 tests
python verify_all.py    :: full audit (skip phase8 for speed)