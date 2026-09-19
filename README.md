# OHM-Synapse

**Epistemic digital twin** — layered personal memory, anti-hallucination
pipeline, and peer-to-peer sync with end-to-end encryption.

> ⚠️ **Research artifact (v0.0.4).** Not a product. No peer review.
> See [Limitations](#limitations) before deploying anywhere real.

[![tests](https://github.com/Xyz101zyX/OHM-Synapse/actions/workflows/tests.yml/badge.svg)](https://github.com/Xyz101zyX/OHM-Synapse/actions/workflows/tests.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

---

## What it is

OHM-Synapse stores facts about you in **four memory layers**, each with
different trust rules. When you ask a question, it decides whether to
answer from memory (no LLM), abstain, or call the LLM with validated
context. It never asserts without grounding.

**Result:** 0% hallucination in 120 structured test cases.

It also syncs memory between peers over MQTT with E2EE, so two
devices can share facts without a central server.

---

## Quick start (5 minutes)

### 1. Install

```bash
git clone https://github.com/Xyz101zyX/OHM-Synapse.git
cd OHM-Synapse
pip install -e .
If you don't have the repo:

bash
pip install git+https://github.com/Xyz101zyX/OHM-Synapse.git
2. Verify installation
bash
ohm version
Expected:

text
ohm-synapse 0.0.1
python 3.14.x
data home: /home/<user>/.ohm        (Linux/macOS)
data home: C:\Users\<user>\.ohm     (Windows)
3. Create your first peer
A "peer" is one identity — your local instance.

bash
ohm init my_peer
Expected:

text
[ok] peer 'my_peer' initialized at ~/.ohm/peers/my_peer

next steps:
  1. start broker:    ohm broker
  2. start peer:      ohm run my_peer
  3. check status:    ohm status my_peer
4. Configure authentication (optional but recommended)
bash
ohm setup-auth my_peer
You will be asked for:

A password (min 6 chars) — type it twice

Three personal recovery questions and their answers

A recovery phrase (12 words) — write it down. Shown only once.

5. Log in
bash
ohm login my_peer
Your session token is stored at ~/.ohm/sessions/my_peer.token.

6. Start the broker (Terminal 1)
The broker is the local MQTT hub that lets peers find each other.

bash
python run_local_broker.py
Leave it running. Expected:

text
LOCAL MQTT BROKER RUNNING
  bind: tcp://0.0.0.0:1883
7. Start the peer (Terminal 2)
bash
ohm run my_peer --headless --port 7900
Expected:

text
[my_peer] node_id = <16 hex chars>
[my_peer] port = 7900
[my_peer] mqtt_enabled = True
[my_peer] chat_enabled = True
[my_peer] mode = headless
[http] listening on 127.0.0.1:7900
Leave it running.

8. Talk to your peer (Terminal 3)
bash
# Load your session token into an env var
set /p TOKEN=<"%USERPROFILE%\.ohm\sessions\my_peer.token"       :: Windows
export TOKEN=$(cat ~/.ohm/sessions/my_peer.token)                :: Linux/macOS

# Health check (public, no auth)
curl http://127.0.0.1:7900/ping
# {"ok": true}

# Store a fact
curl -X POST http://127.0.0.1:7900/think \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"/remember my cat name is Zeca"}'
# {"status": "REMEMBER", ...}

# Ask about it
curl -X POST http://127.0.0.1:7900/think \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"what is my cat name"}'
# {"status": "OK", "text": "my cat name is Zeca", "llm_used": false}

# Ask something it doesn't know
curl -X POST http://127.0.0.1:7900/think \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"what is my fish name"}'
# {"status": "ABSTAIN", ...}
That's the core loop: remember → recall → abstain when unknown.

Full command reference
Peer management
Command	What it does
ohm init <name>	Create a peer's data directory
ohm init <name> --force	Recreate (wipes existing data)
ohm list	List all registered peers
ohm status <name>	Show whether a peer is running
ohm stop <name>	Stop a running peer
Authentication
Command	What it does
ohm setup-auth <name>	Set password + 3 questions + recovery phrase
ohm auth-status <name>	Show auth configuration
ohm login <name>	Create a session token (valid 168h)
ohm logout <name>	Revoke the current session
ohm recover <name>	Reset password via questions or phrase
Running peers
Command	What it does
ohm run <name>	Start with Gradio UI (default port 7860)
ohm run <name> --headless --port 7900	Start headless (HTTP only)
ohm broker	Start local MQTT broker
ohm two-peers --headless	Start peer-a and peer-b on 7860/7861
Chat
Command	What it does
ohm chat <from> <peer_id> "message"	Send an E2EE message
/peers (via HTTP)	List known peers
/ask <peer> <query>	Ask another peer
/read <peer>	Read a peer's shared memory
HTTP API reference
All endpoints run on the peer's port (default 7900).

Endpoint	Method	Auth	Purpose
/ping	GET	No	Health check
/status	GET	Yes	Peer status (node_id, mqtt, chat)
/think	POST	Yes	Run the 3-stage pipeline
/chat_handshake	POST	Yes	Initiate ECDH with a peer
/chat_send	POST	Yes	Send an encrypted message
/chat_history	POST	Yes	Read conversation history
/think commands
Prefix the query with a slash for commands:

Command	Effect
/remember <text>	Store as PERSONAL_RECORD
/forget <id>	Delete a memory by ID
/correct <id> <text>	Supersede an existing memory
/promote <id> <layer>	Change a memory's layer
/audit [topic]	List stored memories
/export	Dump all memory as JSON
/help	List all commands
Any query without a slash goes through the pipeline (recall →
grounding → reasoning) and returns OK, CAUTION, ABSTAIN, or
CONFLICT.

How it decides
text
your query
    │
    ▼
[1] RECALL         find similar memories
    │
    ▼
[2] GROUNDING      is any of them about the same subject?
    │
    ├── yes → return the fact directly (no LLM)
    │
    ├── no  → abstain
    │
    └── partial → call LLM with validated context
Why this matters: if the pipeline has the fact, it doesn't ask the
LLM to paraphrase it. Paraphrasing is where hallucination starts. When
the LLM is used, it sees only context that already passed subject match.

Configuration
Environment variables
Variable	Default	Purpose
OHM_HOME	~/.ohm	Where peer data lives
OHM_TEST_MODE	unset	1 disables LLM for tests
OHM_RESISTANCE	0.5	Weight for anti-hallucination bias
LLM providers
OHM supports any LLM via the adapter layer. Set it in the peer config
or via /threshold (coming soon):

python
cfg.llm_cfg = {
    "enabled": True,
    "provider": "ollama",       # or "openai", "anthropic", "mock"
    "endpoint": "http://localhost:11434",
    "model_name": "llama3.2:1b",
}
Supported providers: Ollama, OpenAI, Anthropic, Google,
Mock (deterministic, for tests).

Thresholds
Current defaults:

python
thresholds = {
    "grounding": 0.20,          # minimum score to consider a memory grounded
    "confidence_respond": 0.80, # confidence to answer without caution
    "confidence_caution": 0.50, # confidence to answer with caution
}
See DESIGN.md §8.2 for why these values are a hypothesis,
not a fact.

Memory layers
Layer	Persists	Used for grounding	Example
PERSONAL_RECORD	Yes	Yes	"my cat name is Zeca"
FACT_EXTERNAL	Yes	Yes	Wikipedia lookup
INFERENCE	Yes	With caution	Derived conclusion
EPHEMERAL	No	No	LLM response (discarded)
Key rule: the LLM's own output never becomes a permanent memory.
This prevents contamination of future grounding decisions.

P2P sync
Two peers can share PERSONAL_RECORD memory over MQTT:

bash
# Terminal 1 — broker
python run_local_broker.py

# Terminal 2 — peer A
ohm run peer_a --headless --port 7900

# Terminal 3 — peer B
ohm run peer_b --headless --port 7901

# Terminal 4 — do a handshake from A to B
curl -X POST http://127.0.0.1:7900/chat_handshake \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{"peer":"<node_id_of_b>"}'
# {"ok": true}

# Store a fact in A — B receives it via MQTT within ~3 seconds
curl -X POST http://127.0.0.1:7900/think \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{"query":"/remember project X starts today"}'

# After a few seconds, B has it too
curl -X POST http://127.0.0.1:7901/think \
  -H "Authorization: Bearer $TOKEN_B" \
  -H "Content-Type: application/json" \
  -d '{"query":"/audit"}'
The node_id is printed when each peer starts.

What syncs and what doesn't
Layer	Syncs?
PERSONAL_RECORD	✅
FACT_EXTERNAL	✅
INFERENCE	❌ (local only)
EPHEMERAL	❌ (never persisted)
Messages are encrypted with ECDH P-256 + AES-GCM. The private key
is generated on first boot and stored in ~/.ohm/.

Gradio UI
For a graphical interface:

bash
ohm run my_peer
Open http://localhost:7860. You get:

Pipeline tab — send /remember, what is my cat name, etc.

Chat tab — E2EE messages to other peers

Audit tab — browse stored memory

⚠️ Known limitation: the UI opens without an auth prompt even
when auth is configured. This is a Gradio 6.0 issue (tracked in
DESIGN.md §8.13). Only run on a trusted network.

Development
Run tests
bash
python run_tests.py
Expected: TOTAL checked=230 ok=230 failed=0 (~5 min).

Verify full project
bash
python check_all.py                # syntax + mypy + import
python verify_all.py --skip phase8 # 12-phase audit (fast)
python journey.py                  # state of all phases
Run benchmarks
bash
python benchmark_offline.py        # fast, no LLM
python benchmark_v3.py             # 120 cases (~8 min)
Results are written to benchmark_v3_report.json.

Project structure
text
ohm_synapse.py      core pipeline
ohm_chat.py         E2EE chat
ohm_kairos.py       temporal module
ohm_embeddings.py   vector search (lazy-loaded)
ohm_auth.py         auth
ohm_ui.py           Gradio UI
ohm_cli.py          CLI
ohm/                internal package (19 modules)
run_peer.py         headless executor
run_local_broker.py MQTT broker
See DESIGN.md for the full operator's guide.

Results
Benchmark v3 — 120 cases, mock LLM:

Metric	Value	95% CI
Accuracy	109/120 (90.8%)	[84.3%, 94.8%]
Hallucination	0/120 (0.0%)	[0.0%, 3.1%]
Misses	11	—
Per category:

Category	OK / Total
known_personal	20/20
unknown_personal	20/20
adversarial	15/15
conflict	12/12
temporal	8/8
source_crossing	8/8
external_known	10/10
corrupted_memory	15/15
multi_hop	0/12
Reproduce with python benchmark_v3.py.

Limitations
Known
Multi-hop: 0/12 in every model tested. Combining two memories
(Alice is my sister + Alice lives in Paris) is not implemented.
Models <3B don't compensate.

UI auth: Gradio 6.0 limitation, no auth prompt.

No ECDSA signature on memory_delta: integrity is guaranteed by
MQTT+TLS, not end-to-end signatures.

Threshold is overfit: 0.20 was chosen against a benchmark written
by the same author. See DESIGN.md §8.2.

Hardware
Tested on 4GB RAM. Capped at 3 local models in parallel.
For multi-hop, use a cloud LLM adapter.

Not proven
No user study. Benchmark is synthetic.

No external peer review.

Validity is internal only.

Troubleshooting
ohm run hangs on first start
The sentence-transformers model (~90 MB) downloads on the first
embedding call. Wait 1-2 minutes, or pre-download it:

bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2', device='cpu')"
Unauthorized on every /status call
The session token expired or was revoked. Log in again:

bash
ohm login my_peer
set /p TOKEN=<"%USERPROFILE%\.ohm\sessions\my_peer.token"
MQTT connection failed
Broker not running. Start it in a separate terminal:

bash
python run_local_broker.py
what is my fish name returns CAUTION with the cat's memory
This was fixed in v0.0.4. If you see it again, run:

bash
python run_tests.py --only test_ohm,test_ohm_extended
If those pass, the pipeline is fine and the issue is likely stale
memory. Wipe the store:

bash
del "%USERPROFILE%\.ohm\peers\my_peer\mem.json"
pip install -e . fails on Windows with cffi errors
Install build tools:

bash
pip install --upgrade pip setuptools wheel
pip install cryptography --only-binary :all:
pip install -e .
Contributing
Small project, no PRs accepted without tests. Open an issue first to
discuss the change.

Before sending a PR:

bash
python run_tests.py       # must pass 230/230
python check_all.py       # must pass 110/110
If a change breaks a test, fix the code — not the test.

Citation
bibtex
@misc{ohm-synapse-2026,
  title  = {OHM-Synapse: Epistemic Digital Twin with Anti-Hallucination Pipeline},
  author = {Xyz101zyX},
  year   = {2026},
  url    = {https://github.com/Xyz101zyX/OHM-Synapse}
}
License
Apache License 2.0 — see LICENSE and NOTICE.

Patent grant included (Apache 2.0 §3). Commercial and academic use
permitted. Modifications must declare changes.

text

## Como substituir

```bat
:: Backup do README atual
copy README.md README.md.old

:: Substituir (abrir notepad, colar o conteúdo, salvar como README.md)
notepad README.md
Commit + push
bat
git add README.md
git commit -m "docs: complete README with quick start, API reference, troubleshooting"
git push origin main