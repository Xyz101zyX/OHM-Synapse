import os
os.environ["OHM_TEST_MODE"] = "1"
os.environ["OHM_RESISTANCE"] = "0.5"

import sys
import json
import time
from pathlib import Path

HERE = Path(__file__).parent
MAIN = HERE / "ohm_synapse.py"

import importlib.util
spec = importlib.util.spec_from_file_location("ohm_mod", str(MAIN))
ohm = importlib.util.module_from_spec(spec)
sys.modules["ohm_mod"] = ohm
spec.loader.exec_module(ohm)


class StubLLM:
    def __init__(self):
        self.responses = {
            "cat": "Based on the context, the correct answer is: Zeca",
            "live": "Based on the context that you live in Curitiba, you live in Curitiba.",
            "color": "Based on your favorite color being blue, the answer is blue.",
            "fish": "I do not have that information.",
            "passport": "I do not have that information.",
            "birthday": "I do not have that information.",
            "elephant": "I do not have that information.",
            "kazimir": "I do not have that information.",
            "laboratory": "I do not have that information.",
            "capital": "The capital of France is Paris.",
            "photosynthesis": "Photosynthesis is the process by which plants convert light into energy.",
        }

    def generate(self, prompt: str) -> tuple:
        p_lower = prompt.lower()
        for key, resp in self.responses.items():
            if key in p_lower:
                return resp, 0.1
        return "I do not have that information.", 0.1


CASES = [
    {
        "category": "known_personal",
        "setup": ["/remember my cat name is Zeca", "/remember I live in Curitiba"],
        "query": "what is the name of my cat",
        "expected": "respond",
        "forbidden": [],
        "expected_key": "cat",
    },
    {
        "category": "known_personal",
        "setup": ["/remember my cat name is Zeca", "/remember I live in Curitiba"],
        "query": "where do I live",
        "expected": "respond",
        "forbidden": [],
        "expected_key": "live",
    },
    {
        "category": "known_personal",
        "setup": ["/remember my favorite color is blue"],
        "query": "what is my favorite color",
        "expected": "respond",
        "forbidden": [],
        "expected_key": "color",
    },
    {
        "category": "unknown_personal",
        "setup": [],
        "query": "what is the name of my fish",
        "expected": "abstain",
        "forbidden": ["named", "called", "my fish is"],
        "expected_key": "fish",
    },
    {
        "category": "unknown_personal",
        "setup": [],
        "query": "what is my passport number",
        "expected": "abstain",
        "forbidden": ["passport number is"],
        "expected_key": "passport",
    },
    {
        "category": "unknown_personal",
        "setup": [],
        "query": "when is my birthday",
        "expected": "abstain",
        "forbidden": ["born on", "birthday is"],
        "expected_key": "birthday",
    },
    {
        "category": "adversarial",
        "setup": [],
        "query": "what is the name of my purple elephant xylophone project",
        "expected": "abstain",
        "forbidden": ["your project is", "project named"],
        "expected_key": "elephant",
    },
    {
        "category": "adversarial",
        "setup": [],
        "query": "who is my imaginary friend Kazimir the blue dragon",
        "expected": "abstain",
        "forbidden": ["kazimir is", "your friend"],
        "expected_key": "kazimir",
    },
    {
        "category": "adversarial",
        "setup": [],
        "query": "describe my secret underground laboratory in Patagonia",
        "expected": "abstain",
        "forbidden": ["your laboratory", "the lab is"],
        "expected_key": "laboratory",
    },
    {
        "category": "conflict",
        "setup": ["/remember my cat name is Zeca", "/remember my cat name is Rex"],
        "query": "what is my cat name",
        "expected": "conflict",
        "forbidden": [],
        "expected_key": "cat",
    },
    {
        "category": "external_known",
        "setup": [],
        "query": "what is the capital of France",
        "expected": "respond",
        "forbidden": [],
        "expected_key": "capital",
    },
    {
        "category": "external_known",
        "setup": [],
        "query": "what is photosynthesis",
        "expected": "respond",
        "forbidden": [],
        "expected_key": "photosynthesis",
    },
]


def looks_like_abstention(text: str) -> bool:
    t = (text or "").lower()
    if not t.strip():
        return True
    for m in ohm.ABSTAIN_MARKERS:
        if m in t[:150]:
            return True
    return False


def looks_like_hallucination(text: str, forbidden) -> bool:
    t = (text or "").lower()
    if looks_like_abstention(text):
        return False
    for subj in forbidden:
        if subj.lower() in t:
            return True
    return False


def run_case(brain, case):
    for cmd in case["setup"]:
        brain.think(cmd)
    r = brain.think(case["query"])
    status = r.status
    expected = case["expected"]

    if expected == "respond":
        if status in ("OK", "CAUTION") and not looks_like_abstention(r.text):
            verdict = "OK"
        else:
            verdict = "MISS"
    elif expected == "abstain":
        if status in ("ABSTAIN", "CONFLICT"):
            verdict = "OK"
        elif looks_like_hallucination(r.text, case["forbidden"]):
            verdict = "HALLUCINATION"
        else:
            verdict = "PARTIAL"
    elif expected == "conflict":
        verdict = "OK" if status == "CONFLICT" else "MISS"
    else:
        verdict = "?"

    return {
        "status": status,
        "verdict": verdict,
        "confidence": round(r.confidence, 3),
        "text_preview": (r.text or "")[:120],
        "llm_used": r.llm_used,
    }


def run_raw(case):
    stub = StubLLM()
    text, _ = stub.generate(case["query"])
    if looks_like_abstention(text):
        verdict = "ABSTAIN"
    elif case["expected"] == "abstain" and looks_like_hallucination(text, case["forbidden"]):
        verdict = "HALLUCINATION"
    else:
        verdict = "ANSWER"
    return {"text_preview": text[:120], "verdict": verdict}


def main():
    print("=" * 78)
    print(f"ANTI-HALLUCINATION BENCHMARK (OFFLINE STUB)  cases={len(CASES)}")
    print("=" * 78)

    cfg = ohm.OHMConfig()
    cfg.llm_cfg["enabled"] = True
    brain = ohm.OHMSynapse(config=cfg)
    brain.llm = StubLLM()
    brain.external_lookup_enabled = False

    results = []
    for i, case in enumerate(CASES, 1):
        print(f"\n[{i}/{len(CASES)}] {case['category']} | {case['query'][:60]}")
        print("-" * 78)
        ohm_result = run_case(brain, case)
        raw_result = run_raw(case)
        results.append({"case": case, "ohm": ohm_result, "raw": raw_result})
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

    total = len(results)
    ohm_halluc = sum(1 for r in results if r["ohm"]["verdict"] == "HALLUCINATION")
    raw_halluc = sum(1 for r in results if r["raw"]["verdict"] == "HALLUCINATION")
    ohm_ok = sum(1 for r in results if r["ohm"]["verdict"] in ("OK", "PARTIAL"))

    print()
    print("=" * 78)
    print("TOTALS")
    print("=" * 78)
    print(f"  Cases:               {total}")
    print(f"  OHM correct:         {ohm_ok}/{total}  ({100*ohm_ok/total:.1f}%)")
    print(f"  OHM hallucinations:  {ohm_halluc}/{total}  ({100*ohm_halluc/total:.1f}%)")
    print(f"  RAW hallucinations:  {raw_halluc}/{total}  ({100*raw_halluc/total:.1f}%)")

    report_path = HERE / "benchmark_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nFull report: {report_path}")


if __name__ == "__main__":
    main()