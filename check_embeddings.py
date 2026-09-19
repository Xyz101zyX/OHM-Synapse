import sys
from pathlib import Path

HERE = Path(__file__).parent

try:
    from sentence_transformers import SentenceTransformer
    print("[ok]   sentence-transformers installed")
except ImportError:
    print("[FAIL] sentence-transformers NOT installed")
    print("       run: pip install sentence-transformers")
    sys.exit(1)

try:
    import numpy as np
    print("[ok]   numpy installed")
except ImportError:
    print("[FAIL] numpy not installed")
    sys.exit(1)

print("       loading model (first run downloads ~80MB)...")
try:
    model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    dim = model.get_sentence_embedding_dimension()
    print(f"[ok]   model loaded, dim={dim}")

    v1 = model.encode("Alice is my sister", normalize_embeddings=True)
    v2 = model.encode("where does my sibling live", normalize_embeddings=True)
    v3 = model.encode("photosynthesis converts light", normalize_embeddings=True)

    sim_sister = float(np.dot(v1, v2))
    sim_other = float(np.dot(v1, v3))

    print(f"       sim(sister, sibling) = {sim_sister:.3f}")
    print(f"       sim(sister, photosynthesis) = {sim_other:.3f}")
    if sim_sister > sim_other + 0.15:
        print("[ok]   semantic discrimination works")
    else:
        print("[warn] discrimination weak")
except Exception as e:
    print(f"[FAIL] model error: {e}")
    sys.exit(1)

print()
print("NEXT:")
print("  1. pip install sentence-transformers")
print("  2. python patch_embeddings.py")
print("  3. python -m unittest test_embeddings -v")
print("  4. python benchmark_v3.py")