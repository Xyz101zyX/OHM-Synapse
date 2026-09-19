import os
os.environ["OHM_TEST_MODE"] = "1"
os.environ["OHM_RESISTANCE"] = "0.5"

import sys
import json
import time
import argparse
import requests
from pathlib import Path
from collections import defaultdict, Counter
import tempfile
import atexit
import shutil
from pathlib import Path as _Path

_BENCH_TMP = _Path(tempfile.mkdtemp(prefix="ohm_mm_"))
atexit.register(lambda: shutil.rmtree(_BENCH_TMP, ignore_errors=True))

HERE = Path(__file__).parent
MAIN = HERE / "ohm_synapse.py"

import importlib.util
spec = importlib.util.spec_from_file_location("ohm_mod", str(MAIN))
ohm = importlib.util.module_from_spec(spec)
sys.modules["ohm_mod"] = ohm
spec.loader.exec_module(ohm)

spec_bv3 = importlib.util.spec_from_file_location("bv3", str(HERE / "benchmark_v3.py"))
bv3 = importlib.util.module_from_spec(spec_bv3)
sys.modules["bv3"] = bv3
spec_bv3.loader.exec_module(bv3)

CASES = bv3.CASES
wilson_ci = bv3.wilson_ci
looks_like_abstention = bv3.looks_like_abstention

OLLAMA_URL = "http://localhost:11434"


def list_models():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception as e:
        print(f"error listing models: {e}")
        return []


def make_brain(model, timeout=90):
    case_tmp = _Path(tempfile.mkdtemp(prefix="case_", dir=_BENCH_TMP))
    cfg = ohm.OHMConfig()
    cfg.memory_cfg = dict(cfg.memory_cfg)
    cfg.memory_cfg["persistence_file"] = str(case_tmp / "mem.json")
    cfg.memory_cfg["audit_file"] = str(case_tmp / "audit.jsonl")
    cfg.memory_cfg["export_file"] = str(case_tmp / "export.json")
    cfg.llm_cfg = dict(cfg.llm_cfg)
    cfg.llm_cfg["enabled"] = True
    cfg.llm_cfg["provider"] = "ollama"
    cfg.llm_cfg["endpoint"] = OLLAMA_URL
    cfg.llm_cfg["model_name"] = model
    cfg.llm_cfg["timeout"] = timeout
    cfg.distributed_cfg = dict(cfg.distributed_cfg)
    cfg.distributed_cfg["enabled"] = False
    brain = ohm.OHMSynapse(config=cfg)
    brain.llm = ohm.OllamaAdapter(cfg)
    brain.external_lookup_enabled = False
    return brain


def evaluate(brain, case):
    for cmd in case.get("setup", []):
        brain.think(cmd)
    r = brain.think(case["query"])
    exp = case["exp"]
    status = r.status
    text = r.text or ""

    if exp == "respond":
        if status in ("OK", "CAUTION") and not looks_like_abstention(text):
            must = case.get("must_contain")
            if must and must.lower() not in text.lower():
                v = "WRONG_CONTENT"
            else:
                v = "OK"
        elif status == "ABSTAIN":
            v = "OVER_ABSTAIN"
        else:
            v = "MISS"
    elif exp == "abstain":
        if status in ("ABSTAIN", "CONFLICT"):
            v = "OK"
        else:
            v = "HALLUCINATION" if text else "PARTIAL"
    elif exp == "conflict":
        v = "OK" if status == "CONFLICT" else "MISS"
    elif exp == "conflict_or_respond":
        v = "OK" if status in ("CONFLICT", "CAUTION", "OK") else "MISS"
    elif exp == "any":
        v = "OK"
    else:
        v = "?"

    return {
        "id": case["id"],
        "cat": case["cat"],
        "status": status,
        "verdict": v,
        "confidence": round(r.confidence, 3),
        "llm_used": r.llm_used,
        "preview": text[:160],
    }


def run_model(model, cases, timeout=90):
    print()
    print("=" * 78)
    print(f"MODEL: {model}  ({len(cases)} cases)")
    print("=" * 78)

    results = []
    t0 = time.time()
    for i, case in enumerate(cases, 1):
        brain = make_brain(model, timeout=timeout)
        try:
            r = evaluate(brain, case)
        except Exception as e:
            r = {"id": case["id"], "cat": case["cat"], "verdict": "ERROR",
                 "status": "ERROR", "preview": str(e)[:160], "confidence": 0.0,
                 "llm_used": False}
        finally:
            brain.shutdown()
        results.append(r)
        elapsed = time.time() - t0
        print(f"  [{i:3}/{len(cases)}] {case['id']} {r['verdict']:15} ({elapsed:.0f}s)")

    ok_n = sum(1 for r in results if r["verdict"] in ("OK", "PARTIAL"))
    total = len(results)
    hall = sum(1 for r in results if r["verdict"] == "HALLUCINATION")
    acc_lo, acc_hi = wilson_ci(ok_n, total) if total else (0, 0)
    hall_lo, hall_hi = wilson_ci(hall, total) if total else (0, 0)

    return {
        "model": model,
        "total": total,
        "ok": ok_n,
        "accuracy": round(ok_n / total * 100, 1) if total else 0.0,
        "accuracy_ci": [round(acc_lo, 4), round(acc_hi, 4)],
        "hallucination": hall,
        "hallucination_ci": [round(hall_lo, 4), round(hall_hi, 4)],
        "wrong_content": sum(1 for r in results if r["verdict"] == "WRONG_CONTENT"),
        "miss": sum(1 for r in results if r["verdict"] == "MISS"),
        "over_abstain": sum(1 for r in results if r["verdict"] == "OVER_ABSTAIN"),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="multi_hop")
    parser.add_argument("--models", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-models", type=int, default=3,
                        help="hardware cap (4GB RAM); default 3")
    parser.add_argument("--timeout-per-case", type=int, default=90,
                        help="seconds per case per model")
    args = parser.parse_args()

    available = list_models()
    if not available:
        print("no models available in ollama. Run: ollama list")
        sys.exit(1)

    print(f"available models ({len(available)}):")
    for m in available:
        print(f"  - {m}")

    targets = args.models if args.models else available

    print()
    print(f"hardware-limited: 4GB RAM, capped at {args.max_models} models")
    if len(targets) > args.max_models:
        dropped = len(targets) - args.max_models
        targets = targets[:args.max_models]
        print(f"  dropped {dropped} model(s) to respect cap")

    cases = [c for c in CASES if c["cat"] == args.category]
    if args.limit:
        cases = cases[:args.limit]

    print()
    print(f"running category '{args.category}' ({len(cases)} cases)")
    print(f"against {len(targets)} model(s)")

    summary = []
    for model in targets:
        try:
            result = run_model(model, cases,
                               timeout=args.timeout_per_case)
            summary.append(result)
        except KeyboardInterrupt:
            print("\ninterrupted")
            break
        except Exception as e:
            print(f"model {model} failed: {e}")

    print()
    print("=" * 78)
    print("CROSS-MODEL SUMMARY")
    print("=" * 78)
    print(f"{'model':35} | {'OK':>6} | {'acc':>7} | {'CI':>17} | {'WRONG':>5} | {'OVR':>4} | {'HALL':>4}")
    print("-" * 78)
    for s in summary:
        ci = f"[{s['accuracy_ci'][0]*100:.1f}%,{s['accuracy_ci'][1]*100:.1f}%]"
        print(f"{s['model']:35} | {s['ok']:>3}/{s['total']:<2} | {s['accuracy']:>6.1f}% | {ci:>17} | "
              f"{s['wrong_content']:>5} | {s['over_abstain']:>4} | {s['hallucination']:>4}")

    out = HERE / "benchmark_multi_model.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print()
    print(f"report: {out}")


if __name__ == "__main__":
    main()