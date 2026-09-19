OHM-Synapse
Epistemic digital twin — layered personal memory, 3-stage pipeline, P2P sync with E2EE.
Focus: zero hallucination in personal queries.

⚠️ Research artifact (v0.0.3). Not a product. No peer review.

[![tests](https://github.com/Xyz101zyX/OHM-Synapse/actions/workflows/tests.yml/badge.svg)](https://github.com/Xyz101zyX/OHM-Synapse/actions/workflows/tests.yml)

Results (benchmark v3, n=120)
Metric
Value
Hallucination	0.0%
Accuracy	90.8% (109/120)
Unit tests	230/230 ✅
Multi-hop	0/12 ❌ (known limitation)
Peer boot time	0.36s

Quick Start
bash

git clone https://github.com/Xyz101zyX/OHM-Synapse.git
cd OHM-Synapse
pip install -e .

# Check status
python journey.py

# Run peer (terminal 1: broker)
python run_local_broker.py

# Terminal 2: headless peer
ohm init my_peer
ohm setup-auth my_peer
ohm login my_peer
ohm run my_peer --headless --port 7900