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

HERE = Path(__file__).parent
MAIN = HERE / "ohm_synapse.py"

import importlib.util
spec = importlib.util.spec_from_file_location("ohm_mod", str(MAIN))
ohm = importlib.util.module_from_spec(spec)
sys.modules["ohm_mod"] = ohm
spec.loader.exec_module(ohm)


OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2:1b"


def check_ollama():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.status_code != 200:
            return False, f"api/tags returned {r.status_code}"
        data = r.json()
        models = [m.get("name", "") for m in data.get("models", [])]
        if not any(OLLAMA_MODEL in m for m in models):
            return False, f"model {OLLAMA_MODEL} not present. Run: ollama pull {OLLAMA_MODEL}"
        return True, f"OK, model {OLLAMA_MODEL} available"
    except Exception as e:
        return False, f"connection failed: {e}"


spec_bv3 = importlib.util.spec_from_file_location("bv3", str(HERE / "benchmark_v3.py"))
bv3 = importlib.util.module_from_spec(spec_bv3)
sys.modules["bv3"] = bv3
spec_bv3.loader.exec_module(bv3)

CASES = bv3.CASES
wilson_ci = bv3.wilson_ci
looks_like_abstention = bv3.looks_like_abstention


def make_brain_ollama():
    cfg = ohm.OHMConfig()
    cfg.llm_cfg = dict(cfg.llm_cfg)
    cfg.llm_cfg["enabled"] = True
    cfg.llm_cfg["provider"] = "ollama"
    cfg.llm_cfg["endpoint"] = OLLAMA_URL
    cfg.llm_cfg["model_name"] = OLLAMA_MODEL
    cfg.llm_cfg["timeout"] = 90
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
        "subcat": case.get("subcat", ""),
        "query": case["query"],
        "status": status,
        "verdict": v,
        "confidence": round(r.confidence, 3),
        "llm_used": r.llm_used,
        "preview": text[:140],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    ok, msg = check_ollama()
    print(f"ollama: {msg}")
    if not ok:
        print("aborting - start ollama first: ollama serve")
        sys.exit(1)

    cases = CASES
    if args.category:
        cases = [c for c in cases if c["cat"] == args.category]
    if args.limit:
        cases = cases[:args.limit]

    n = len(cases)
    print("=" * 78)
    print(f"OHM BENCHMARK v3 - OLLAMA - {n} cases")
    if args.category:
        print(f"filter: {args.category}")
    print("=" * 78)

    results = []
    t0 = time.time()
    for i, case in enumerate(cases, 1):
        brain = make_brain_ollama()
        try:
            r = evaluate(brain, case)
        except Exception as e:
            r = {"id": case["id"], "cat": case["cat"], "verdict": "ERROR",
                 "status": "ERROR", "preview": str(e)[:140], "confidence": 0.0,
                 "llm_used": False, "subcat": "", "query": case["query"]}
        finally:
            brain.shutdown()
        results.append(r)
        elapsed = time.time() - t0
        print(f"  [{i:3}/{n}] {case['id']} {r['verdict']:15} ({elapsed:.0f}s)")

    by_cat = defaultdict(lambda: Counter())
    for r in results:
        by_cat[r["cat"]][r["verdict"]] += 1

    print()
    print("=" * 78)
    print("BY CATEGORY with 95% Wilson CI")
    print("=" * 78)
    print(f"{'category':22} | {'OK':>5} | {'PART':>4} | {'MISS':>4} | {'OVR':>3} | {'WRONG':>5} | {'HAL':>3} | {'acc':>6} | {'CI':>15}")
    print("-" * 78)
    for cat in sorted(by_cat.keys()):
        c = by_cat[cat]
        total = sum(c.values())
        ok_n = c["OK"] + c["PARTIAL"]
        acc = ok_n / total if total else 0
        lo, hi = wilson_ci(ok_n, total)
        print(f"{cat:22} | {c['OK']:>5} | {c['PARTIAL']:>4} | {c['MISS']:>4} | "
              f"{c['OVER_ABSTAIN']:>3} | {c['WRONG_CONTENT']:>5} | {c['HALLUCINATION']:>3} | "
              f"{acc*100:>5.1f}% | [{lo*100:>5.1f}%,{hi*100:>5.1f}%]")

    total = len(results)
    ok_n = sum(1 for r in results if r["verdict"] in ("OK", "PARTIAL"))
    hall = sum(1 for r in results if r["verdict"] == "HALLUCINATION")
    miss = sum(1 for r in results if r["verdict"] == "MISS")
    over = sum(1 for r in results if r["verdict"] == "OVER_ABSTAIN")
    wrong = sum(1 for r in results if r["verdict"] == "WRONG_CONTENT")

    acc_lo, acc_hi = wilson_ci(ok_n, total)
    hall_lo, hall_hi = wilson_ci(hall, total)

    print()
    print("=" * 78)
    print("AGGREGATE")
    print("=" * 78)
    print(f"  total:              {total}")
    print(f"  ok:                 {ok_n}  ({ok_n/total*100:.1f}%)  CI [{acc_lo*100:.1f}%,{acc_hi*100:.1f}%]")
    print(f"  hallucination:      {hall}  ({hall/total*100:.1f}%)  CI [{hall_lo*100:.1f}%,{hall_hi*100:.1f}%]")
    print(f"  wrong_content:      {wrong}")
    print(f"  miss:               {miss}")
    print(f"  over_abstain:       {over}")

    print()
    print("FAILURES:")
    fails = [r for r in results if r["verdict"] not in ("OK", "PARTIAL")]
    if not fails:
        print("  none")
    else:
        for r in fails:
            print(f"  [{r['id']}] {r['verdict']:15} | {r['cat']:18} | {r['query'][:50]}")
            print(f"       -> {r['preview'][:100]}")

    print()
    print(f"total time: {time.time() - t0:.0f}s")

    report_path = HERE / "benchmark_v3_ollama_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "total": total, "ok": ok_n, "halluc": hall, "miss": miss,
            "over_abstain": over, "wrong_content": wrong,
            "accuracy_ci": [acc_lo, acc_hi],
            "hallucination_ci": [hall_lo, hall_hi],
            "provider": "ollama",
            "model": OLLAMA_MODEL,
            "results": results,
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()