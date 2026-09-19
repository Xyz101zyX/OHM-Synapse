import requests
import time

OLLAMA = "http://localhost:11434"

models = [
    "llama3.2:1b", "qwen2.5:3b", "llama3.2:3b",
    "llama3.1:8b", "phi3:latest", "gemma4:latest",
]

print("=" * 70)
print("DIRECT OLLAMA DIAGNOSTIC")
print("=" * 70)

for m in models:
    try:
        t0 = time.time()
        r = requests.post(
            f"{OLLAMA}/api/generate",
            json={"model": m, "prompt": "say hi", "stream": False},
            timeout=300,
        )
        elapsed = time.time() - t0
        data = r.json()
        if "error" in data:
            print(f"  {m:25} ERROR: {data['error'][:60]}")
            continue
        resp = data.get("response", "")
        preview = resp[:60].replace("\n", " ")
        print(f"  {m:25} OK ({elapsed:5.1f}s): {preview!r}")
    except requests.exceptions.ReadTimeout:
        print(f"  {m:25} TIMEOUT after 300s")
    except requests.exceptions.ConnectionError:
        print(f"  {m:25} CONNECTION REFUSED")
    except Exception as e:
        print(f"  {m:25} ERROR: {str(e)[:60]}")