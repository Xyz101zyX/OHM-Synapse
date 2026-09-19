"""Patch benchmark_multi_model.py: hardware cap for 4GB RAM.

Changes:
  - add --max-models (default 3)
  - add --timeout-per-case (default 90)
  - cap targets list
  - print hardware note at startup
  - apply timeout to each model's cfg
"""

import ast
import pathlib
import shutil
import sys

TARGET = pathlib.Path("benchmark_multi_model.py")
BACKUP = pathlib.Path("benchmark_multi_model.py.before_cap")

if not TARGET.exists():
    print("[abort] benchmark_multi_model.py not found")
    sys.exit(1)

shutil.copy(TARGET, BACKUP)
src = TARGET.read_text(encoding="utf-8")

# ---------------------------------------------------------------- patch 1
# extend argparse
OLD_ARGS = '''    parser.add_argument("--category", default="multi_hop")
    parser.add_argument("--models", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()'''

NEW_ARGS = '''    parser.add_argument("--category", default="multi_hop")
    parser.add_argument("--models", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-models", type=int, default=3,
                        help="hardware cap (4GB RAM); default 3")
    parser.add_argument("--timeout-per-case", type=int, default=90,
                        help="seconds per case per model")
    args = parser.parse_args()'''

if OLD_ARGS not in src:
    print("[abort] argparse block not found")
    sys.exit(1)
src = src.replace(OLD_ARGS, NEW_ARGS, 1)
print("[patch 1] args --max-models, --timeout-per-case added")

# ---------------------------------------------------------------- patch 2
# hardware note + cap
OLD_TARGETS = '''    targets = args.models if args.models else available'''
NEW_TARGETS = '''    targets = args.models if args.models else available

    print()
    print(f"hardware-limited: 4GB RAM, capped at {args.max_models} models")
    if len(targets) > args.max_models:
        dropped = len(targets) - args.max_models
        targets = targets[:args.max_models]
        print(f"  dropped {dropped} model(s) to respect cap")'''

if OLD_TARGETS not in src:
    print("[abort] targets assignment not found")
    sys.exit(1)
src = src.replace(OLD_TARGETS, NEW_TARGETS, 1)
print("[patch 2] hardware cap applied")

# ---------------------------------------------------------------- patch 3
# make_brain receives timeout
OLD_MAKE = '''def make_brain(model):
    cfg = ohm.OHMConfig()
    cfg.llm_cfg = dict(cfg.llm_cfg)
    cfg.llm_cfg["enabled"] = True
    cfg.llm_cfg["provider"] = "ollama"
    cfg.llm_cfg["endpoint"] = OLLAMA_URL
    cfg.llm_cfg["model_name"] = model
    cfg.llm_cfg["timeout"] = 120'''

NEW_MAKE = '''def make_brain(model, timeout=90):
    cfg = ohm.OHMConfig()
    cfg.llm_cfg = dict(cfg.llm_cfg)
    cfg.llm_cfg["enabled"] = True
    cfg.llm_cfg["provider"] = "ollama"
    cfg.llm_cfg["endpoint"] = OLLAMA_URL
    cfg.llm_cfg["model_name"] = model
    cfg.llm_cfg["timeout"] = timeout'''

if OLD_MAKE not in src:
    print("[abort] make_brain block not found")
    sys.exit(1)
src = src.replace(OLD_MAKE, NEW_MAKE, 1)
print("[patch 3] make_brain accepts timeout")

# ---------------------------------------------------------------- patch 4
# propagate timeout into run_model
OLD_RUN = '''            result = run_model(model, cases)'''
NEW_RUN = '''            result = run_model(model, cases,
                               timeout=args.timeout_per_case)'''
if OLD_RUN not in src:
    print("[abort] run_model call not found")
    sys.exit(1)
src = src.replace(OLD_RUN, NEW_RUN, 1)
print("[patch 4] run_model receives timeout")

# ---------------------------------------------------------------- verify
try:
    ast.parse(src)
except SyntaxError as e:
    print(f"[abort] syntax error: {e}")
    sys.exit(1)

TARGET.write_text(src, encoding="utf-8")
print("[ok] wrote benchmark_multi_model.py")