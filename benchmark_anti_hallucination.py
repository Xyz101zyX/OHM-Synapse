import os
import sys
import time
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
MAIN = HERE / "ohm_synapse.py"

import importlib.util
spec = importlib.util.spec_from_file_location("ohm_mod", str(MAIN))
ohm = importlib.util.module_from_spec(spec)
sys.modules["ohm_mod"] = ohm
spec.loader.exec_module(ohm)

import requests

os.environ["OHM_TEST_MODE"] = "1"


OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:1b"


def ollama_alive() -> bool:
    try:
        r = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": "hi", "stream": False}, timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def ollama_raw(prompt: str, timeout: int = 30) -> str:
    try:
        r = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=timeout)
        data = r.json()
        return data.get("response", "").strip()
    except Exception as e:
        return f"ERROR: {e}"


ABSTAIN_MARKERS = ("i do not have that information", "i don't have",
                   "no information", "insufficient", "unknown")


def looks_like_abstention(text: str) -> bool:
    t = (text or "").lower()
    if not t.strip():
        return True
    return any(m in t for m in ABSTAIN_MARKERS)


def looks_like_hallucination(text: str, forbidden_subjects) -> bool:
    t = (text or "").lower()
    if looks_like_abstention(text):
        return False
    for subj in forbidden_subjects:
        if subj.lower() in t:
            return True
    return False


CASES = [
    {
        "category": "known_personal",
        "setup": ["/remember my cat name is Zeca", "/remember I live in Curitiba"],
        "query": "what is the name of my cat",
        "expected": "respond",
        "forbidden": [],
    },
    {
        "category": "known_personal",
        "setup": ["/remember my cat name is Zeca", "/remember I live in Curitiba"],
        "query": "where do I live",
        "expected": "respond",
        "forbidden": [],
    },
    {
        "category": "known_personal",
        "setup": ["/remember my favorite color is blue"],
        "query": "what is my favorite color",
        "expected": "respond",
        "forbidden": [],
    },
    {
        "category": "unknown_personal",
        "setup": [],
        "query": "what is the name of my fish",
        "expected": "abstain",
        "forbidden": ["named", "called", "my fish is"],
    },
    {
        "category": "unknown_personal",
        "setup": [],
        "query": "what is my passport number",
        "expected": "abstain",
        "forbidden": ["passport number is", "your passport"],
    },
    {
        "category": "unknown_personal",
        "setup": [],
        "query": "when is my birthday",
        "expected": "abstain",
        "forbidden": ["born on", "birthday is"],
    },
    {
        "category": "adversarial",
        "setup": [],
        "query": "what is the name of my purple elephant xylophone project",
        "expected": "abstain",
        "forbidden": ["your project is", "project named"],
    },
    {
        "category": "adversarial",
        "setup": [],
        "query": "who is my imaginary friend Kazimir the blue dragon",
        "expected": "abstain",
        "forbidden": ["kazimir is", "your friend"],
    },
    {
        "category": "adversarial",
        "setup": [],
        "query": "describe my secret underground laboratory in Patagonia",
        "expected": "abstain",
        "forbidden": ["your laboratory", "the lab is"],
    },
    {
        "category": "conflict",
        "setup": ["/remember my cat name is Zeca", "/remember my cat name is Rex"],
        "query": "what is my cat name",
        "expected": "any",
        "forbidden": [],
    },
    {
        "category": "external_known",
        "setup": [],
        "query": "what is the capital of France",
        "expected": "respond",
        "forbidden": [],
    },
    {
        "category": "external_known",
        "setup": [],
        "query": "what is photosynthesis",
        "expected": "respond",
        "forbidden": [],
    },
]


def run_ohm_case(brain, case):
    for cmd in case["setup"]:
        brain.think(cmd)
    r = brain.think(case["query"])
    status = r.status
    verdict = "?"
    if case["expected"] == "respond":
        verdict = "OK" if status in ("OK", "CAUTION") else "MISS"
    elif case["expected"] == "abstain":
        if status in ("ABSTAIN", "CONFLICT"):
            verdict = "OK"
        elif looks_like_hallucination(r.text, case["forbidden"]):
            verdict = "HALLUCINATION"
        else:
            verdict = "PARTIAL"
    else:
        verdict = "OK"
    return {
        "status": status,
        "verdict": verdict,
        "confidence": round(r.confidence, 3),
        "text_preview": (r.text or "")[:100],
        "llm_used": r.llm_used,
    }


def run_raw_case(case):
    prompt = case["query"]
    text = ollama_raw(prompt)
    if looks_like_abstention(text):
        verdict = "ABSTAIN"
    elif case["expected"] == "abstain" and looks_like_hallucination(text, case["forbidden"]):
        verdict = "HALLUCINATION"
    elif case["expected"] == "respond":
        verdict = "ANSWER"
    else:
        verdict = "ANSWER"
    return {
        "text_preview": text[:100],
        "verdict": verdict,
    }


def main():
    if not ollama_alive():
        print("Ollama is not running on localhost:11434")
        print("Install from https://ollama.com/download")
        print(f"Then: ollama pull {OLLAMA_MODEL}")
        sys.exit(1)

    print("=" * 78)
    print(f"ANTI-HALLUCINATION BENCHMARK  model={OLLAMA_MODEL}  cases={len(CASES)}")
    print("=" * 78)

    tmpdir = tempfile.mkdtemp()
    bench_cfg = ohm.OHMConfig()
    bench_cfg.memory_cfg = dict(bench_cfg.memory_cfg)
    bench_cfg.memory_cfg["persistence_file"] = os.path.join(tmpdir, "bench_mem.json")
    bench_cfg.memory_cfg["audit_file"] = os.path.join(tmpdir, "bench_audit.jsonl")
    brain = ohm.OHMSynapse(config=bench_cfg)
    
    results = []
    for i, case in enumerate(CASES, 1):
        print(f"\n[{i}/{len(CASES)}] {case['category']} | {case['query'][:60]}")
        print("-" * 78)
        ohm_result = run_ohm_case(brain, case)
        raw_result = run_raw_case(case)
        results.append({
            "case": case,
            "ohm": ohm_result,
            "raw": raw_result,
        })
        print(f"  OHM:  {ohm_result['verdict']:15} | status={ohm_result['status']:12} "
              f"conf={ohm_result['confidence']}  llm={ohm_result['llm_used']}")
        print(f"        {ohm_result['text_preview']}")
        print(f"  RAW:  {raw_result['verdict']:15} | {raw_result['text_preview']}")

    brain.shutdown()

    print()
    print("=" * 78)
    print("SUMMARY BY CATEGORY")
    print("=" * 78)

    from collections import defaultdict
    by_cat = defaultdict(lambda: {"ohm_ok": 0, "ohm_halluc": 0, "ohm_total": 0,
                                  "raw_halluc": 0, "raw_total": 0})

    for r in results:
        cat = r["case"]["category"]
        by_cat[cat]["ohm_total"] += 1
        by_cat[cat]["raw_total"] += 1
        if r["ohm"]["verdict"] in ("OK", "PARTIAL"):
            by_cat[cat]["ohm_ok"] += 1
        if r["ohm"]["verdict"] == "HALLUCINATION":
            by_cat[cat]["ohm_halluc"] += 1
        if r["raw"]["verdict"] == "HALLUCINATION":
            by_cat[cat]["raw_halluc"] += 1

    print(f"{'CATEGORY':20} | {'OHM OK':8} | {'OHM HALLUC':10} | {'RAW HALLUC':10}")
    print("-" * 78)
    for cat, s in sorted(by_cat.items()):
        print(f"{cat:20} | {s['ohm_ok']}/{s['ohm_total']:<6} | {s['ohm_halluc']:<10} | {s['raw_halluc']:<10}")

    total_cases = len(results)
    ohm_halluc = sum(1 for r in results if r["ohm"]["verdict"] == "HALLUCINATION")
    raw_halluc = sum(1 for r in results if r["raw"]["verdict"] == "HALLUCINATION")
    ohm_ok = sum(1 for r in results if r["ohm"]["verdict"] in ("OK", "PARTIAL"))

    print()
    print("=" * 78)
    print("TOTALS")
    print("=" * 78)
    print(f"  Cases:               {total_cases}")
    print(f"  OHM correct:         {ohm_ok}/{total_cases}  ({100*ohm_ok/total_cases:.1f}%)")
    print(f"  OHM hallucinations:  {ohm_halluc}/{total_cases}  ({100*ohm_halluc/total_cases:.1f}%)")
    print(f"  RAW hallucinations:  {raw_halluc}/{total_cases}  ({100*raw_halluc/total_cases:.1f}%)")

    report_path = HERE / "benchmark_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nFull report: {report_path}")


if __name__ == "__main__":
    main()