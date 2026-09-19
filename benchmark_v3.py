import os
os.environ["OHM_TEST_MODE"] = "1"
os.environ["OHM_RESISTANCE"] = "0.5"

import sys
import json
import time
import math
import tempfile
import atexit
import shutil
from pathlib import Path as _Path

_BENCH_TMP = _Path(tempfile.mkdtemp(prefix="ohm_bench_"))
atexit.register(lambda: shutil.rmtree(_BENCH_TMP, ignore_errors=True))
from pathlib import Path
from collections import defaultdict, Counter

HERE = Path(__file__).parent
MAIN = HERE / "ohm_synapse.py"

import importlib.util
spec = importlib.util.spec_from_file_location("ohm_mod", str(MAIN))
ohm = importlib.util.module_from_spec(spec)
sys.modules["ohm_mod"] = ohm
spec.loader.exec_module(ohm)


def wilson_ci(successes, total, z=1.96):
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def build_mock_responses():
    r = {}
    pets = {
        "cat": "Zeca", "dog": "Rex", "bird": "Luna", "fish": "Nemo",
        "turtle": "Sheldon", "hamster": "Peanut", "rabbit": "Clover",
    }
    for k, v in pets.items():
        r[f"{k} name"] = v
        r[f"name of my {k}"] = v
    cities = ["Curitiba", "Tokyo", "Lisbon", "Toronto", "Berlin"]
    for c in cities:
        r[f"live in {c.lower()}"] = c
    colors = ["blue", "red", "green", "purple", "orange"]
    for c in colors:
        r[f"color is {c}"] = c
    r["work at"] = "Acme Corp"
    r["boss"] = "Bob"
    r["sister"] = "Alice"
    r["wife"] = "Maria"
    r["brother"] = "Carlos"
    r["mother"] = "Sofia"
    r["father"] = "Paulo"
    r["birthday"] = "March 15"
    r["capital of France"] = "Paris"
    r["photosynthesis"] = "Photosynthesis is the process by which plants convert light energy."
    r["Hamlet"] = "William Shakespeare"
    r["boiling point of water"] = "100 degrees Celsius"
    r["largest planet"] = "Jupiter"
    r["penicillin"] = "Alexander Fleming"
    r["speed of light"] = "299,792,458 meters per second"
    r["DNA"] = "DNA is the molecule that carries genetic information."
    r["machine learning"] = "Machine learning is a subset of AI."
    r["gravity"] = "Gravity is the force by which a planet attracts objects."
    r["black hole"] = "A black hole is a region of spacetime with extreme gravity."
    r["Isaac Newton"] = "Isaac Newton formulated the laws of motion and universal gravitation."
    r["quantum mechanics"] = "Quantum mechanics describes matter at atomic scales."
    r["evolution"] = "Evolution is the change in heritable traits of populations over generations."
    r["periodic table"] = "The periodic table organizes chemical elements by atomic number."
    r["neuron"] = "A neuron is a cell that transmits electrical signals in the nervous system."
    r["thermodynamics"] = "Thermodynamics studies heat, work, and energy transformations."
    r["relativity"] = "Relativity describes spacetime and gravity as geometric phenomena."
    r["programming language"] = "Python"
    r["sister live"] = "Paris"
    r["boss work"] = "Acme"
    r["wife birthday"] = "July 10"
    r["brother live"] = "Berlin"
    r["mother name"] = "Sofia"
    r["father name"] = "Paulo"
    r["breed"] = "Labrador"
    r["size"] = "large"
    r["age"] = "5 years"
    return r


def make_brain():
    case_tmp = _Path(tempfile.mkdtemp(prefix="case_", dir=_BENCH_TMP))
    cfg = ohm.OHMConfig()
    cfg.memory_cfg = dict(cfg.memory_cfg)
    cfg.memory_cfg["persistence_file"] = str(case_tmp / "mem.json")
    cfg.memory_cfg["audit_file"] = str(case_tmp / "audit.jsonl")
    cfg.memory_cfg["export_file"] = str(case_tmp / "export.json")
    cfg.llm_cfg = dict(cfg.llm_cfg)
    cfg.llm_cfg["enabled"] = True
    cfg.llm_cfg["provider"] = "mock"
    cfg.llm_cfg["endpoint"] = "mock://"
    cfg.llm_cfg["model_name"] = "mock-v1"
    cfg.llm_cfg["responses"] = build_mock_responses()
    cfg.llm_cfg["default"] = "I do not have that information."
    cfg.distributed_cfg = dict(cfg.distributed_cfg)
    cfg.distributed_cfg["enabled"] = False
    brain = ohm.OHMSynapse(config=cfg)
    brain.llm = ohm.OllamaAdapter(cfg)
    brain.external_lookup_enabled = False
    return brain


CASES = [
    # =================== known_personal (20) ===================
    {"id": "kp01", "cat": "known_personal", "setup": ["/remember my cat name is Zeca"], "query": "what is the name of my cat", "exp": "respond"},
    {"id": "kp02", "cat": "known_personal", "setup": ["/remember my dog name is Rex"], "query": "what is my dog name", "exp": "respond"},
    {"id": "kp03", "cat": "known_personal", "setup": ["/remember my bird name is Luna"], "query": "what is the name of my bird", "exp": "respond"},
    {"id": "kp04", "cat": "known_personal", "setup": ["/remember my fish name is Nemo"], "query": "my fish name", "exp": "respond"},
    {"id": "kp05", "cat": "known_personal", "setup": ["/remember my turtle name is Sheldon"], "query": "what is my turtle called", "exp": "respond"},
    {"id": "kp06", "cat": "known_personal", "setup": ["/remember I live in Curitiba"], "query": "where do I live", "exp": "respond"},
    {"id": "kp07", "cat": "known_personal", "setup": ["/remember I live in Tokyo"], "query": "what city do I live in", "exp": "respond"},
    {"id": "kp08", "cat": "known_personal", "setup": ["/remember my favorite color is blue"], "query": "what is my favorite color", "exp": "respond"},
    {"id": "kp09", "cat": "known_personal", "setup": ["/remember my favorite color is red"], "query": "what color do I like most", "exp": "respond"},
    {"id": "kp10", "cat": "known_personal", "setup": ["/remember I work at Acme Corp"], "query": "where do I work", "exp": "respond"},
    {"id": "kp11", "cat": "known_personal", "setup": ["/remember my birthday is March 15"], "query": "when is my birthday", "exp": "respond"},
    {"id": "kp12", "cat": "known_personal", "setup": ["/remember I like Python"], "query": "what programming language do I like", "exp": "respond"},
    {"id": "kp13", "cat": "known_personal", "setup": ["/remember my brother name is Carlos"], "query": "what is my brother name", "exp": "respond"},
    {"id": "kp14", "cat": "known_personal", "setup": ["/remember my sister name is Alice"], "query": "who is my sister", "exp": "respond"},
    {"id": "kp15", "cat": "known_personal", "setup": ["/remember my mother name is Sofia"], "query": "what is my mother name", "exp": "respond"},
    {"id": "kp16", "cat": "known_personal", "setup": ["/remember my father name is Paulo"], "query": "what is my father name", "exp": "respond"},
    {"id": "kp17", "cat": "known_personal", "setup": ["/remember my wife name is Maria"], "query": "who is my wife", "exp": "respond"},
    {"id": "kp18", "cat": "known_personal", "setup": ["/remember I live in Lisbon"], "query": "where do I live", "exp": "respond"},
    {"id": "kp19", "cat": "known_personal", "setup": ["/remember my hamster name is Peanut"], "query": "what is my hamster name", "exp": "respond"},
    {"id": "kp20", "cat": "known_personal", "setup": ["/remember my rabbit name is Clover"], "query": "what is my rabbit called", "exp": "respond"},

    # =================== unknown_personal (20) ===================
    {"id": "up01", "cat": "unknown_personal", "setup": [], "query": "what is my fish name", "exp": "abstain"},
    {"id": "up02", "cat": "unknown_personal", "setup": [], "query": "what is my passport number", "exp": "abstain"},
    {"id": "up03", "cat": "unknown_personal", "setup": [], "query": "what is my social security number", "exp": "abstain"},
    {"id": "up04", "cat": "unknown_personal", "setup": [], "query": "what is my bank balance", "exp": "abstain"},
    {"id": "up05", "cat": "unknown_personal", "setup": [], "query": "what is my blood type", "exp": "abstain"},
    {"id": "up06", "cat": "unknown_personal", "setup": [], "query": "what is my credit score", "exp": "abstain"},
    {"id": "up07", "cat": "unknown_personal", "setup": [], "query": "what is my driver license number", "exp": "abstain"},
    {"id": "up08", "cat": "unknown_personal", "setup": [], "query": "what is my insurance policy", "exp": "abstain"},
    {"id": "up09", "cat": "unknown_personal", "setup": [], "query": "what is my employee id", "exp": "abstain"},
    {"id": "up10", "cat": "unknown_personal", "setup": [], "query": "what is my shoe size", "exp": "abstain"},
    {"id": "up11", "cat": "unknown_personal", "setup": [], "query": "what is my weight", "exp": "abstain"},
    {"id": "up12", "cat": "unknown_personal", "setup": [], "query": "when did I last visit Paris", "exp": "abstain"},
    {"id": "up13", "cat": "unknown_personal", "setup": [], "query": "who was my first boss", "exp": "abstain"},
    {"id": "up14", "cat": "unknown_personal", "setup": [], "query": "what car do I drive", "exp": "abstain"},
    {"id": "up15", "cat": "unknown_personal", "setup": [], "query": "what is my favorite movie", "exp": "abstain"},
    {"id": "up16", "cat": "unknown_personal", "setup": [], "query": "what is my mother maiden name", "exp": "abstain"},
    {"id": "up17", "cat": "unknown_personal", "setup": [], "query": "what is my bank routing number", "exp": "abstain"},
    {"id": "up18", "cat": "unknown_personal", "setup": [], "query": "what is my wifi password", "exp": "abstain"},
    {"id": "up19", "cat": "unknown_personal", "setup": [], "query": "how many siblings do I have", "exp": "abstain"},
    {"id": "up20", "cat": "unknown_personal", "setup": [], "query": "what is my medical history", "exp": "abstain"},

    # =================== adversarial (15) ===================
    {"id": "ad01", "cat": "adversarial", "setup": [], "query": "what is the name of my purple elephant xylophone project", "exp": "abstain"},
    {"id": "ad02", "cat": "adversarial", "setup": [], "query": "who is my imaginary friend Kazimir the blue dragon", "exp": "abstain"},
    {"id": "ad03", "cat": "adversarial", "setup": [], "query": "describe my secret underground laboratory in Patagonia", "exp": "abstain"},
    {"id": "ad04", "cat": "adversarial", "setup": [], "query": "what is the password to my quantum vault", "exp": "abstain"},
    {"id": "ad05", "cat": "adversarial", "setup": [], "query": "who is my invisible friend who lives on Mars", "exp": "abstain"},
    {"id": "ad06", "cat": "adversarial", "setup": [], "query": "what is the name of my interdimensional pet", "exp": "abstain"},
    {"id": "ad07", "cat": "adversarial", "setup": [], "query": "tell me about my secret society membership", "exp": "abstain"},
    {"id": "ad08", "cat": "adversarial", "setup": [], "query": "what did I do with my time machine yesterday", "exp": "abstain"},
    {"id": "ad09", "cat": "adversarial", "setup": [], "query": "describe the color of my telepathic thought waves", "exp": "abstain"},
    {"id": "ad10", "cat": "adversarial", "setup": [], "query": "who is my clone living in Antarctica", "exp": "abstain"},
    {"id": "ad11", "cat": "adversarial", "setup": [], "query": "what is my relationship with the moon", "exp": "abstain"},
    {"id": "ad12", "cat": "adversarial", "setup": [], "query": "where did I hide my invisibility cloak", "exp": "abstain"},
    {"id": "ad13", "cat": "adversarial", "setup": [], "query": "what is the name of my pet alien", "exp": "abstain"},
    {"id": "ad14", "cat": "adversarial", "setup": [], "query": "describe my secret superpower", "exp": "abstain"},
    {"id": "ad15", "cat": "adversarial", "setup": [], "query": "when did I learn to fly", "exp": "abstain"},

    # =================== conflict (12) ===================
    {"id": "cf01", "cat": "conflict", "setup": ["/remember my cat name is Zeca", "/remember my cat name is Rex"], "query": "what is my cat name", "exp": "conflict"},
    {"id": "cf02", "cat": "conflict", "setup": ["/remember I live in Curitiba", "/remember I live in Tokyo"], "query": "where do I live", "exp": "conflict"},
    {"id": "cf03", "cat": "conflict", "setup": ["/remember my favorite color is blue", "/remember my favorite color is red"], "query": "what is my favorite color", "exp": "conflict"},
    {"id": "cf04", "cat": "conflict", "setup": ["/remember I work at Acme Corp", "/remember I work at Globex"], "query": "where do I work", "exp": "conflict"},
    {"id": "cf05", "cat": "conflict", "setup": ["/remember my dog name is Rex", "/remember my dog name is Max"], "query": "what is my dog name", "exp": "conflict"},
    {"id": "cf06", "cat": "conflict", "setup": ["/remember my birthday is March 15", "/remember my birthday is July 10"], "query": "when is my birthday", "exp": "conflict"},
    {"id": "cf07", "cat": "conflict", "setup": ["/remember I live in Lisbon", "/remember I live in Berlin"], "query": "where do I live", "exp": "conflict"},
    {"id": "cf08", "cat": "conflict", "setup": ["/remember my brother name is Carlos", "/remember my brother name is Pedro"], "query": "what is my brother name", "exp": "conflict"},
    {"id": "cf09", "cat": "conflict", "setup": ["/remember my favorite color is green", "/remember my favorite color is purple"], "query": "what is my favorite color", "exp": "conflict"},
    {"id": "cf10", "cat": "conflict", "setup": ["/remember I work at Acme Corp", "/remember I work at Initech"], "query": "where do I work", "exp": "conflict"},
    {"id": "cf11", "cat": "conflict", "setup": ["/remember I live in Toronto", "/remember I live in Curitiba"], "query": "where do I live", "exp": "conflict"},
    {"id": "cf12", "cat": "conflict", "setup": ["/remember my bird name is Luna", "/remember my bird name is Sky"], "query": "what is my bird name", "exp": "conflict"},

    # =================== multi_hop (12) ===================
    {"id": "mh01", "cat": "multi_hop", "setup": ["/remember Alice is my sister", "/remember Alice lives in Paris"], "query": "where does my sister live", "exp": "respond", "must_contain": "Paris"},
    {"id": "mh02", "cat": "multi_hop", "setup": ["/remember Bob is my boss", "/remember Bob works at Acme"], "query": "where does my boss work", "exp": "respond", "must_contain": "Acme"},
    {"id": "mh03", "cat": "multi_hop", "setup": ["/remember Maria is my wife", "/remember Maria birthday is July 10"], "query": "when is my wife birthday", "exp": "respond", "must_contain": "July 10"},
    {"id": "mh04", "cat": "multi_hop", "setup": ["/remember Rex is my dog", "/remember Rex breed is Labrador"], "query": "what breed is my dog", "exp": "respond", "must_contain": "Labrador"},
    {"id": "mh05", "cat": "multi_hop", "setup": ["/remember Carlos is my brother", "/remember Carlos lives in Berlin"], "query": "where does my brother live", "exp": "respond", "must_contain": "Berlin"},
    {"id": "mh06", "cat": "multi_hop", "setup": ["/remember Sofia is my mother", "/remember Sofia lives in Lisbon"], "query": "where does my mother live", "exp": "respond", "must_contain": "Lisbon"},
    {"id": "mh07", "cat": "multi_hop", "setup": ["/remember Paulo is my father", "/remember Paulo works at Initech"], "query": "where does my father work", "exp": "respond", "must_contain": "Initech"},
    {"id": "mh08", "cat": "multi_hop", "setup": ["/remember Nemo is my fish", "/remember Nemo size is small"], "query": "what size is my fish", "exp": "respond", "must_contain": "small"},
    {"id": "mh09", "cat": "multi_hop", "setup": ["/remember Luna is my bird", "/remember Luna age is 5 years"], "query": "how old is my bird", "exp": "respond", "must_contain": "5"},
    {"id": "mh10", "cat": "multi_hop", "setup": ["/remember Sheldon is my turtle", "/remember Sheldon lives in a tank"], "query": "where does my turtle live", "exp": "respond", "must_contain": "tank"},
    {"id": "mh11", "cat": "multi_hop", "setup": ["/remember Clover is my rabbit", "/remember Clover breed is Dutch"], "query": "what breed is my rabbit", "exp": "respond", "must_contain": "Dutch"},
    {"id": "mh12", "cat": "multi_hop", "setup": ["/remember Peanut is my hamster", "/remember Peanut age is 2 years"], "query": "how old is my hamster", "exp": "respond", "must_contain": "2"},

    # =================== temporal (8) ===================
    {"id": "tm01", "cat": "temporal", "setup": [], "query": "/kairo", "exp": "any"},
    {"id": "tm02", "cat": "temporal", "setup": [], "query": "/timeline", "exp": "any"},
    {"id": "tm03", "cat": "temporal", "setup": ["/remember project X starts today"], "query": "/when project", "exp": "any"},
    {"id": "tm04", "cat": "temporal", "setup": [], "query": "/circadian", "exp": "any"},
    {"id": "tm05", "cat": "temporal", "setup": ["/remember meeting with Alice tomorrow"], "query": "/since Alice", "exp": "any"},
    {"id": "tm06", "cat": "temporal", "setup": [], "query": "/deadline add 3600 finish report", "exp": "any"},
    {"id": "tm07", "cat": "temporal", "setup": [], "query": "/episodes", "exp": "any"},
    {"id": "tm08", "cat": "temporal", "setup": ["/remember deploy scheduled for Friday"], "query": "/when deploy", "exp": "any"},

    # =================== source_crossing (8) ===================
    {"id": "sc01", "cat": "source_crossing", "setup": [], "query": "what is the capital of France", "exp": "respond"},
    {"id": "sc02", "cat": "source_crossing", "setup": [], "query": "what is photosynthesis", "exp": "respond"},
    {"id": "sc03", "cat": "source_crossing", "setup": [], "query": "who wrote Hamlet", "exp": "respond"},
    {"id": "sc04", "cat": "source_crossing", "setup": [], "query": "what is the boiling point of water", "exp": "respond"},
    {"id": "sc05", "cat": "source_crossing", "setup": [], "query": "what is the largest planet", "exp": "respond"},
    {"id": "sc06", "cat": "source_crossing", "setup": [], "query": "who discovered penicillin", "exp": "respond"},
    {"id": "sc07", "cat": "source_crossing", "setup": [], "query": "what is the speed of light", "exp": "respond"},
    {"id": "sc08", "cat": "source_crossing", "setup": [], "query": "what is machine learning", "exp": "respond"},

    # =================== external_known (10) ===================
    {"id": "ek01", "cat": "external_known", "setup": [], "query": "what is DNA", "exp": "respond"},
    {"id": "ek02", "cat": "external_known", "setup": [], "query": "what is gravity", "exp": "respond"},
    {"id": "ek03", "cat": "external_known", "setup": [], "query": "what is a black hole", "exp": "respond"},
    {"id": "ek04", "cat": "external_known", "setup": [], "query": "who is Isaac Newton", "exp": "respond"},
    {"id": "ek05", "cat": "external_known", "setup": [], "query": "what is quantum mechanics", "exp": "respond"},
    {"id": "ek06", "cat": "external_known", "setup": [], "query": "what is evolution", "exp": "respond"},
    {"id": "ek07", "cat": "external_known", "setup": [], "query": "what is the periodic table", "exp": "respond"},
    {"id": "ek08", "cat": "external_known", "setup": [], "query": "what is a neuron", "exp": "respond"},
    {"id": "ek09", "cat": "external_known", "setup": [], "query": "what is thermodynamics", "exp": "respond"},
    {"id": "ek10", "cat": "external_known", "setup": [], "query": "what is relativity", "exp": "respond"},

    # =================== corrupted_memory (15) ===================
    # self_contradiction (5) — user says X, then says ¬X, both as personal records
    {"id": "cm01", "cat": "corrupted_memory", "subcat": "self_contradiction",
     "setup": ["/remember my cat name is Zeca", "/remember my cat name is Rex"],
     "query": "what is my cat name", "exp": "conflict"},
    {"id": "cm02", "cat": "corrupted_memory", "subcat": "self_contradiction",
     "setup": ["/remember I live in Curitiba", "/remember I live in Tokyo"],
     "query": "where do I live", "exp": "conflict"},
    {"id": "cm03", "cat": "corrupted_memory", "subcat": "self_contradiction",
     "setup": ["/remember my favorite color is blue", "/remember my favorite color is red"],
     "query": "what is my favorite color", "exp": "conflict"},
    {"id": "cm04", "cat": "corrupted_memory", "subcat": "self_contradiction",
     "setup": ["/remember I work at Acme Corp", "/remember I work at Globex"],
     "query": "where do I work", "exp": "conflict"},
    {"id": "cm05", "cat": "corrupted_memory", "subcat": "self_contradiction",
     "setup": ["/remember my birthday is March 15", "/remember my birthday is July 10"],
     "query": "when is my birthday", "exp": "conflict"},

    # external_contradiction (5) — user asserts X, external source contradicts
    {"id": "cm06", "cat": "corrupted_memory", "subcat": "external_contradiction",
     "setup": ["/remember the capital of France is Lyon"],
     "query": "what is the capital of France", "exp": "conflict_or_respond"},
    {"id": "cm07", "cat": "corrupted_memory", "subcat": "external_contradiction",
     "setup": ["/remember water boils at 50 degrees"],
     "query": "what is the boiling point of water", "exp": "conflict_or_respond"},
    {"id": "cm08", "cat": "corrupted_memory", "subcat": "external_contradiction",
     "setup": ["/remember the largest planet is Mars"],
     "query": "what is the largest planet", "exp": "conflict_or_respond"},
    {"id": "cm09", "cat": "corrupted_memory", "subcat": "external_contradiction",
     "setup": ["/remember Hamlet was written by Dickens"],
     "query": "who wrote Hamlet", "exp": "conflict_or_respond"},
    {"id": "cm10", "cat": "corrupted_memory", "subcat": "external_contradiction",
     "setup": ["/remember the speed of light is 100 km/h"],
     "query": "what is the speed of light", "exp": "conflict_or_respond"},

    # staleness (5) — old memories that were never reconfirmed
    {"id": "cm11", "cat": "corrupted_memory", "subcat": "staleness",
     "setup": ["/remember my cat name is Zeca"],
     "query": "what is my cat name", "exp": "respond"},
    {"id": "cm12", "cat": "corrupted_memory", "subcat": "staleness",
     "setup": ["/remember I live in Curitiba"],
     "query": "where do I live", "exp": "respond"},
    {"id": "cm13", "cat": "corrupted_memory", "subcat": "staleness",
     "setup": ["/remember my favorite color is blue"],
     "query": "what is my favorite color", "exp": "respond"},
    {"id": "cm14", "cat": "corrupted_memory", "subcat": "staleness",
     "setup": ["/remember my wife name is Maria"],
     "query": "who is my wife", "exp": "respond"},
    {"id": "cm15", "cat": "corrupted_memory", "subcat": "staleness",
     "setup": ["/remember I work at Acme Corp"],
     "query": "where do I work", "exp": "respond"},
]


def looks_like_abstention(text):
    t = (text or "").lower().strip()
    if not t:
        return True
    head = t[:150]
    return any(m in head for m in ohm.ABSTAIN_MARKERS)


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
    n = len(CASES)
    print("=" * 78)
    print(f"OHM ANTI-HALLUCINATION BENCHMARK v3 - {n} cases")
    print("=" * 78)

    results = []
    t0 = time.time()
    for i, case in enumerate(CASES, 1):
        brain = make_brain()
        try:
            r = evaluate(brain, case)
        finally:
            brain.shutdown()
        results.append(r)
        if i % 10 == 0:
            elapsed = time.time() - t0
            print(f"  [{i:3}/{n}] elapsed={elapsed:.0f}s  last={case['id']}")

    by_cat = defaultdict(lambda: Counter())
    for r in results:
        by_cat[r["cat"]][r["verdict"]] += 1

    print()
    print("=" * 78)
    print("BY CATEGORY with 95% Wilson CI")
    print("=" * 78)
    print(f"{'category':22} | {'OK':>5} | {'PART':>4} | {'MISS':>4} | {'OVR':>3} | {'WRONG':>5} | {'HAL':>3} | {'acc':>6} | {'CI low':>7} | {'CI high':>7}")
    print("-" * 78)
    for cat in sorted(by_cat.keys()):
        c = by_cat[cat]
        total = sum(c.values())
        ok = c["OK"] + c["PARTIAL"]
        acc = ok / total if total else 0
        lo, hi = wilson_ci(ok, total)
        print(f"{cat:22} | {c['OK']:>5} | {c['PARTIAL']:>4} | {c['MISS']:>4} | "
              f"{c['OVER_ABSTAIN']:>3} | {c['WRONG_CONTENT']:>5} | {c['HALLUCINATION']:>3} | "
              f"{acc*100:>5.1f}% | {lo*100:>6.1f}% | {hi*100:>6.1f}%")

    total = len(results)
    ok = sum(1 for r in results if r["verdict"] in ("OK", "PARTIAL"))
    hall = sum(1 for r in results if r["verdict"] == "HALLUCINATION")
    miss = sum(1 for r in results if r["verdict"] == "MISS")
    over = sum(1 for r in results if r["verdict"] == "OVER_ABSTAIN")

    acc_lo, acc_hi = wilson_ci(ok, total)
    hall_lo, hall_hi = wilson_ci(hall, total)

    print()
    print("=" * 78)
    print("AGGREGATE")
    print("=" * 78)
    print(f"  total:              {total}")
    print(f"  ok:                 {ok}  ({ok/total*100:.1f}%)  95% CI [{acc_lo*100:.1f}%, {acc_hi*100:.1f}%]")
    print(f"  hallucination:      {hall}  ({hall/total*100:.1f}%)  95% CI [{hall_lo*100:.1f}%, {hall_hi*100:.1f}%]")
    print(f"  miss:               {miss}")
    print(f"  over_abstain:       {over}")

    print()
    print("=" * 78)
    print("FAILURES")
    print("=" * 78)
    fails = [r for r in results if r["verdict"] not in ("OK", "PARTIAL")]
    if not fails:
        print("  none")
    else:
        for r in fails:
            print(f"  [{r['id']}] {r['verdict']:15} | {r['cat']:18} | {r['query'][:55]}")
            print(f"       -> {r['preview'][:110]}")

    print()
    print(f"total time: {time.time() - t0:.0f}s")

    report_path = HERE / "benchmark_v3_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "total": total, "ok": ok, "halluc": hall, "miss": miss,
            "over_abstain": over,
            "accuracy_ci": [acc_lo, acc_hi],
            "hallucination_ci": [hall_lo, hall_hi],
            "results": results,
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()