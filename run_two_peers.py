import sys
import time
import subprocess
from pathlib import Path

HERE = Path(__file__).parent


def launch_peer(name, port, reset=False):
    cmd = [
        sys.executable,
        str(HERE / "run_peer.py"),
        "--name", name,
        "--port", str(port),
    ]
    if reset:
        cmd.append("--reset")
    print(f"[launcher] starting {name} on port {port}")
    return subprocess.Popen(cmd, cwd=str(HERE))


def main():
    print("=" * 70)
    print("OHM PHASE 9 - TWO PEERS (process isolation)")
    print("=" * 70)
    print()
    print("Prerequisites:")
    print("  1. Broker running in another terminal: python run_local_broker.py")
    print("  2. pip install cryptography paho-mqtt gradio")
    print()

    p_a = launch_peer("peer-a", 7860)
    time.sleep(3)
    p_b = launch_peer("peer-b", 7861)

    print()
    print("=" * 70)
    print("PEER A: http://localhost:7860")
    print("PEER B: http://localhost:7861")
    print("=" * 70)
    print("node_ids will appear in child process output.")
    print("Ctrl+C to stop both.")
    print("=" * 70)

    try:
        while True:
            if p_a.poll() is not None:
                print("[launcher] peer-a exited")
                break
            if p_b.poll() is not None:
                print("[launcher] peer-b exited")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (p_a, p_b):
            if proc.poll() is None:
                proc.terminate()
        for proc in (p_a, p_b):
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        print("shutdown complete")


if __name__ == "__main__":
    main()