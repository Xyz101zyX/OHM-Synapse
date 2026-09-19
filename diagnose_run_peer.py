import ast, collections, pathlib

src = pathlib.Path("run_peer.py").read_text(encoding="utf-8")
tree = ast.parse(src)

print(len(src.splitlines()), "lines\n")

top = collections.Counter(
    n.name for n in tree.body
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
)
for name, count in top.most_common():
    if count > 1:
        print(f"{count:>4}  {name}")