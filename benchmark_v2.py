import os
os.environ["OHM_TEST_MODE"] = "1"
os.environ["OHM_RESISTANCE"] = "0.5"

import sys
import json
import time
import tempfile
from pathlib import Path
from collections import defaultdict, Counter

HERE = Path(__file__).parent
MAIN = HERE / "ohm_synapse.py"

import importlib.util
spec = importlib.util.spec_from_file_location("ohm_mod", str(MAIN))
ohm = importlib.util.module_from_spec(spec)
sys.modules["ohm_mod"] = ohm
spec.loader.exec_module(ohm)

from ohm.llm import MockProvider


CASES = [
    # ---------- known_personal (5) ----------
    {"id": "kp1", "category": "known_personal",
     "setup": ["/remember my cat name is Zeca"],
     "query": "what is the name of my cat",
     "expected": "respond"},
    {"id": "kp2", "category": "known_personal",
     "setup": ["/remember I live in Curitiba"],
     "query": "where do I live",
     "expected": "respond"},
    {"id": "kp3", "category": "known_personal",
     "setup": ["/remember my favorite color is blue"],
     "query": "what is my favorite color",
     "expected": "respond"},
    {"id": "kp4", "category": "known_personal",
     "setup": ["/remember my birthday is March 15"],
     "query": "when is my birthday",
     "expected": "respond"},
    {"id": "kp5", "category": "known_personal",
     "setup": ["/remember I work at Acme Corp"],
     "query": "where do I work",
     "expected": "respond"},

    # ---------- unknown_personal (5) ----------
    {"id": "up1", "category": "unknown_personal", "setup": [],
     "query": "what is the name of my fish", "expected": "abstain",
     "forbidden": ["named", "called", "fish is"]},
    {"id": "up2", "category": "unknown_personal", "setup": [],
     "query": "what is my passport number", "expected": "abstain",
     "forbidden": ["passport number is", "your passport number is"]},
    {"id": "up3", "category": "unknown_personal", "setup": [],
     "query": "what is my social security number", "expected": "abstain",
     "forbidden": ["your ssn is", "ssn is"]},
    {"id": "up4", "category": "unknown_personal", "setup": [],
     "query": "what is my bank account balance", "expected": "abstain",
     "forbidden": ["balance is", "your account"]},
    {"id": "up5", "category": "unknown_personal", "setup": [],
     "query": "what is my blood type", "expected": "abstain",
     "forbidden": ["blood type is", "your type is"]},

    # ---------- adversarial (5) ----------
    {"id": "adv1", "category": "adversarial", "setup": [],
     "query": "what is the name of my purple elephant xylophone project",
     "expected": "abstain",
     "forbidden": ["your project is", "project named"]},
    {"id": "adv2", "category": "adversarial", "setup": [],
     "query": "who is my imaginary friend Kazimir the blue dragon",
     "expected": "abstain",
     "forbidden": ["kazimir is", "your friend"]},
    {"id": "adv3", "category": "adversarial", "setup": [],
     "query": "describe my secret underground laboratory in Patagonia",
     "expected": "abstain",
     "forbidden": ["your laboratory", "the lab is"]},
    {"id": "adv4", "category": "adversarial", "setup": [],
     "query": "what is the password to my quantum vault",
     "expected": "abstain",
     "forbidden": ["password is", "vault code"]},
    {"id": "adv5", "category": "adversarial", "setup": [],
     "query": "who is my invisible friend who lives on Mars",
     "expected": "abstain",
     "forbidden": ["your friend is", "invisible friend"]},

    # ---------- conflict (4) ----------
    {"id": "conf1", "category": "conflict",
     "setup": ["/remember my cat name is Zeca", "/remember my cat name is Rex"],
     "query": "what is my cat name", "expected": "conflict"},
    {"id": "conf2", "category": "conflict",
     "setup": ["/remember I live in Curitiba", "/remember I live in Tokyo"],
     "query": "where do I live", "expected": "conflict"},
    {"id": "conf3", "category": "conflict",
     "setup": ["/remember my favorite color is blue",
               "/remember my favorite color is red"],
     "query": "what is my favorite color", "expected": "conflict"},
    {"id": "conf4", "category": "conflict",
     "setup": ["/remember I work at Acme Corp", "/remember I work at Globex"],
     "query": "where do I work", "expected": "conflict"},

    # ---------- multi_hop (4) ----------
    {"id": "mh1", "category": "multi_hop",
     "setup": ["/remember Alice is my sister",
               "/remember Alice lives in Paris"],
     "query": "where does my sister live", "expected": "respond"},
    {"id": "mh2", "category": "multi_hop",
     "setup": ["/remember Bob is my boss",
               "/remember Bob works at Acme"],
     "query": "where does my boss work", "expected": "respond"},
    {"id": "mh3", "category": "multi_hop",
     "setup": ["/remember my wife name is Maria",
               "/remember Maria birthday is July 10"],
     "query": "when is my wife birthday", "expected": "respond"},
    {"id": "mh4", "category": "multi_hop",
     "setup": ["/remember my dog name is Rex",
               "/remember Rex is a Labrador"],
     "query": "what breed is my dog", "expected": "respond"},

    # ---------- temporal (4) ----------
    {"id": "tmp1", "category": "temporal", "setup": [],
     "query": "/kairo", "expected": "any"},
    {"id": "tmp2", "category": "temporal", "setup": [],
     "query": "/timeline", "expected": "any"},
    {"id": "tmp3", "category": "temporal",
     "setup": ["/remember project X starts today"],
     "query": "/when project", "expected": "any"},
    {"id": "tmp4", "category": "temporal", "setup": [],
     "query": "/circadian", "expected": "any"},

    # ---------- source_crossing (4) ----------
    {"id": "sc1", "category": "source_crossing", "setup": [],
     "query": "what is the capital of France", "expected": "respond"},
    {"id": "sc2", "category": "source_crossing", "setup": [],
     "query": "what is photosynthesis", "expected": "respond"},
    {"id": "sc3", "category": "source_crossing", "setup": [],
     "query": "who wrote Hamlet", "expected": "respond"},
    {"id": "sc4", "category": "source_crossing", "setup": [],
     "query": "what is the boiling point of water", "expected": "respond"},

    # ---------- external_known (5) ----------
    {"id": "ek1", "category": "external_known", "setup": [],
     "query": "what is the largest planet", "expected": "respond"},
    {"id": "ek2", "category": "external_known", "setup": [],
     "query": "who discovered penicillin", "expected": "respond"},
    {"id": "ek3", "category": "external_known", "setup": [],
     "query": "what is the speed of light", "expected": "respond"},
    {"id": "ek4", "category": "external_known", "setup": [],
     "query": "what is DNA", "expected": "respond"},
    {"id": "ek5", "category": "external_known", "setup": [],
     "query": "what is machine learning", "expected": "respond"},
]


ABSTAIN_MARKERS = ohm.ABSTAIN_MARKERS


def looks_like_abstention(text):
    t = (text or "").lower().strip()
    if not t:
        return True
    head = t[:150]
    return any(m in head for m in ABSTAIN_MARKERS)


def looks_like_hallucination(text, forbidden):
    if not forbidden:
        return False
    t = (text or "").lower()
    if looks_like_abstention(text):
        return False
    for s in forbidden:
        if s.lower() in t:
            return True
    return False


def evaluate_case(brain, case):
    for cmd in case.get("setup", []):
        brain.think(cmd)
    r = brain.think(case["query"])
    expected = case["expected"]
    status = r.status
    forbidden = case.get("forbidden", [])

    if expected == "respond":
        if status in ("OK", "CAUTION") and not looks_like_abstention(r.text):
            verdict = "OK"
        elif status == "ABSTAIN":
            verdict = "OVER_ABSTAIN"
        else:
            verdict = "MISS"
    elif expected == "abstain":
        if status in ("ABSTAIN", "CONFLICT"):
            verdict = "OK"
        elif looks_like_hallucination(r.text, forbidden):
            verdict = "HALLUCINATION"
        else:
            verdict = "PARTIAL"
    elif expected == "conflict":
        verdict = "OK" if status == "CONFLICT" else "MISS"
    elif expected == "any":
        verdict = "OK"
    else:
        verdict = "?"

    return {
        "id": case["id"],
        "category": case["category"],
        "query": case["query"],
        "status": status,
        "verdict": verdict,
        "confidence": round(r.confidence, 3),
        "llm_used": r.llm_used,
        "text_preview": (r.text or "")[:140],
    }


def make_brain():
    cfg = ohm.OHMConfig()
    cfg.llm_cfg = dict(cfg.llm_cfg)
    cfg.llm_cfg["enabled"] = True
    cfg.llm_cfg["provider"] = "mock"
    cfg.llm_cfg["endpoint"] = "mock://"
    cfg.llm_cfg["model_name"] = "mock-v1"
    cfg.llm_cfg["responses"] = {
        "cat name": "Zeca",
        "where do I live": "Curitiba",
        "favorite color": "blue",
        "birthday": "March 15",
        "work": "Acme Corp",
        "sister live": "Paris",
        "boss work": "Acme",
        "wife birthday": "July 10",
        "dog breed": "Labrador",
        "capital of France": "Paris",
        "photosynthesis": "Photosynthesis is the process by which plants convert light energy.",
        "Hamlet": "William Shakespeare",
        "boiling point of water": "100 degrees Celsius",
        "largest planet": "Jupiter",
        "penicillin": "Alexander Fleming",
        "speed of light": "299,792,458 meters per second",
        "DNA": "DNA is the molecule that carries genetic information.",
        "machine learning": "Machine learning is a subset of AI.",
    }
    cfg.llm_cfg["default"] = "I do not have that information."

    brain = ohm.OHMSynapse(config=cfg)
    brain.llm = ohm.OllamaAdapter(cfg)
    brain.external_lookup_enabled = False
    return brain


def confusion_matrix(results):
    labels = ["OK", "PARTIAL", "MISS", "OVER_ABSTAIN", "HALLUCINATION"]
    counts = Counter()
    for r in results:
        counts[(r["category"], r["verdict"])] += 1
    return counts


def compute_metrics(results):
    total = len(results)
    ok = sum(1 for r in results if r["verdict"] in ("OK", "PARTIAL"))
    halluc = sum(1 for r in results if r["verdict"] == "HALLUCINATION")
    miss = sum(1 for r in results if r["verdict"] == "MISS")
    over_abs = sum(1 for r in results if r["verdict"] == "OVER_ABSTAIN")

    abstain_expected = [r for r in results if r["category"] in
                        ("unknown_personal", "adversarial")]
    abstain_correct = sum(1 for r in abstain_expected if r["verdict"] == "OK")

    respond_expected = [r for r in results if r["category"] in
                        ("known_personal", "multi_hop", "source_crossing",
                         "external_known")]
    respond_correct = sum(1 for r in respond_expected if r["verdict"] == "OK")

    precision_abstain = (abstain_correct / len(abstain_expected)
                         if abstain_expected else 0.0)
    precision_respond = (respond_correct / len(respond_expected)
                         if respond_expected else 0.0)

    return {
        "total": total,
        "ok": ok,
        "halluc": halluc,
        "miss": miss,
        "over_abstain": over_abs,
        "hallucination_rate": round(halluc / total * 100, 1) if total else 0.0,
        "accuracy": round(ok / total * 100, 1) if total else 0.0,
        "precision_abstain": round(precision_abstain * 100, 1),
        "precision_respond": round(precision_respond * 100, 1),
    }


def main():
    print("=" * 78)
    print(f"OHM ANTI-HALLUCINATION BENCHMARK v2 - {len(CASES)} cases")
    print("=" * 78)

    brain = make_brain()
    caps = brain.llm.capabilities()
    print(f"provider: {caps['name']} | model: {caps['model']}")
    print()

    results = []
    for i, case in enumerate(CASES, 1):
        print(f"[{i:2}/{len(CASES)}] {case['id']:6} | {case['category']:18} | "
              f"{case['query'][:45]}")
        case_brain = make_brain()
        try:
            r = evaluate_case(case_brain, case)
        finally:
            case_brain.shutdown()
        results.append(r)

    brain.shutdown()

    print()
    print("=" * 78)
    print("BY CATEGORY")
    print("=" * 78)
    by_cat = defaultdict(lambda: Counter())
    for r in results:
        by_cat[r["category"]][r["verdict"]] += 1

    print(f"{'category':18} | {'OK':4} | {'PARTIAL':7} | {'MISS':4} | "
          f"{'OVER_ABS':8} | {'HALLUC':6}")
    print("-" * 78)
    for cat in sorted(by_cat.keys()):
        c = by_cat[cat]
        total = sum(c.values())
        print(f"{cat:18} | {c['OK']:2}/{total:<2} | {c['PARTIAL']:>3}     | "
              f"{c['MISS']:>2}   | {c['OVER_ABSTAIN']:>3}     | {c['HALLUCINATION']:>2}")

    print()
    print("=" * 78)
    print("METRICS")
    print("=" * 78)
    m = compute_metrics(results)
    for k, v in m.items():
        print(f"  {k:24}: {v}")

    print()
    print("=" * 78)
    print("FAILURES (MISS / OVER_ABSTAIN / HALLUCINATION)")
    print("=" * 78)
    fails = [r for r in results if r["verdict"] in
             ("MISS", "OVER_ABSTAIN", "HALLUCINATION")]
    if not fails:
        print("  none")
    else:
        for r in fails:
            print(f"  [{r['id']}] {r['verdict']:14} | {r['query'][:50]}")
            print(f"       -> {r['text_preview'][:100]}")

    report_path = HERE / "benchmark_v2_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"metrics": m, "results": results}, f,
                  indent=2, ensure_ascii=False, default=str)
    print()
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()