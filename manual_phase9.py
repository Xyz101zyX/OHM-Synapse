import os
os.environ["OHM_RESISTANCE"] = "0.5"

import sys
import time
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
MAIN = HERE / "ohm_synapse.py"

import importlib.util
spec = importlib.util.spec_from_file_location("ohm_mod", str(MAIN))
ohm = importlib.util.module_from_spec(spec)
sys.modules["ohm_mod"] = ohm
spec.loader.exec_module(ohm)


def make_brain(name):
    tmpdir = tempfile.mkdtemp(prefix=f"ohm_manual_{name}_")
    cfg = ohm.OHMConfig()
    cfg.memory_cfg = dict(cfg.memory_cfg)
    cfg.memory_cfg["persistence_file"] = os.path.join(tmpdir, "mem.json")
    cfg.memory_cfg["audit_file"] = os.path.join(tmpdir, "audit.jsonl")
    cfg.memory_cfg["export_file"] = os.path.join(tmpdir, "export.json")
    cfg.distributed_cfg = dict(cfg.distributed_cfg)
    cfg.distributed_cfg["mqtt_broker"] = "localhost"
    cfg.distributed_cfg["mqtt_port"] = 1883
    cfg.distributed_cfg["sync_interval"] = 3
    cfg.security_cfg = dict(cfg.security_cfg)
    cfg.security_cfg["require_tls"] = False
    cfg.security_cfg["allow_public_broker"] = True
    cfg.security_cfg["node_key_file"] = os.path.join(tmpdir, "node_keys.pem")
    b = ohm.OHMSynapse(config=cfg)
    b.external_lookup_enabled = False
    b.llm = None
    return b


def wait_until(predicate, timeout, label):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            print(f"  [ok] {label} ({time.time() - (deadline - timeout):.1f}s)")
            return True
        time.sleep(0.3)
    print(f"  [FAIL] {label} (timeout {timeout}s)")
    return False


def main():
    print("=" * 70)
    print("FASE 9 MANUAL E2E TEST")
    print("=" * 70)

    peer_a = make_brain("a")
    peer_b = make_brain("b")
    print(f"peer-a node_id = {peer_a.node_id}")
    print(f"peer-b node_id = {peer_b.node_id}")
    print()

    if peer_a.node_id == peer_b.node_id:
        print("[FAIL] peers share node_id - key isolation broken")
        peer_a.shutdown(); peer_b.shutdown(); return

    if not peer_a.mqtt.enabled:
        print("[FAIL] MQTT offline. Rode: python run_local_broker.py")
        peer_a.shutdown(); peer_b.shutdown(); return

    print("-- 1. descoberta via MQTT --")
    if not wait_until(
        lambda: peer_b.node_id in peer_a.known_peers and peer_a.node_id in peer_b.known_peers,
        15, "peers se descobriram"
    ):
        peer_a.shutdown(); peer_b.shutdown(); return

    print()
    print("-- 2. handshake ECDH bidirecional --")
    peer_a.chat.send_handshake(peer_b.node_id)
    if not wait_until(
        lambda: peer_b.node_id in peer_a.chat._session_keys and peer_a.node_id in peer_b.chat._session_keys,
        15, "chaves derivadas em ambos lados"
    ):
        peer_a.shutdown(); peer_b.shutdown(); return

    print()
    print("-- 3. envio cifrado peer-a -> peer-b --")
    result = peer_a.chat.send(peer_b.node_id, "ola do peer A (AES-GCM)")
    print(f"  status: {result.get('status')}")
    if result.get("status") != "SENT":
        peer_a.shutdown(); peer_b.shutdown(); return
    if not wait_until(
        lambda: len(peer_b.chat.get_history(peer_a.node_id)) >= 1,
        10, "peer-b recebeu a mensagem"
    ):
        peer_a.shutdown(); peer_b.shutdown(); return
    h = peer_b.chat.get_history(peer_a.node_id)[-1]
    print(f"  conteudo no peer-b: {h['content']}")

    print()
    print("-- 4. resposta cifrada peer-b -> peer-a --")
    result = peer_b.chat.send(peer_a.node_id, "ola do peer B (AES-GCM)")
    print(f"  status: {result.get('status')}")
    if result.get("status") != "SENT":
        peer_a.shutdown(); peer_b.shutdown(); return
    if not wait_until(
        lambda: any("peer B" in e["content"] for e in peer_a.chat.get_history(peer_b.node_id)),
        10, "peer-a recebeu a resposta"
    ):
        peer_a.shutdown(); peer_b.shutdown(); return

    print()
    print("-- 5. memoria pessoal propaga via MQTT --")
    peer_a.think("/remember meu gato se chama Zeca")
    peer_a.last_sync_time = 0
    if not wait_until(
        lambda: any("zeca" in (v.get("content", "") or "").lower()
                    for v in peer_b.memory.store.values()),
        20, "peer-b recebeu a memoria"
    ):
        peer_a.shutdown(); peer_b.shutdown(); return

    print()
    print("-- 6. resumo --")
    print(f"  peer-a sessions: {list(peer_a.chat._session_keys.keys())}")
    print(f"  peer-b sessions: {list(peer_b.chat._session_keys.keys())}")
    print(f"  peer-a history com peer-b: {len(peer_a.chat.get_history(peer_b.node_id))} entradas")
    print(f"  peer-b history com peer-a: {len(peer_b.chat.get_history(peer_a.node_id))} entradas")

    peer_a.shutdown()
    peer_b.shutdown()
    print()
    print("=" * 70)
    print("TODOS OS PASSOS PASSARAM")
    print("=" * 70)


if __name__ == "__main__":
    main()