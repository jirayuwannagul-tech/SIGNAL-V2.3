import sys, ast, re, hashlib
from pathlib import Path
from collections import defaultdict, deque
from difflib import SequenceMatcher

EXCLUDE_DIRS = {
    ".venv","venv",".venv311","venv311","__pycache__", ".git",".pytest_cache",
    "node_modules","dist","build"
}

def iter_py_files(root: Path):
    for p in root.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        yield p

def read_text(p: Path) -> str:
    raw = p.read_bytes()
    txt = raw.decode("utf-8", errors="replace")
    return txt.replace("\r\n","\n").replace("\r","\n")

def module_name(root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)

def norm_ast_dump(fn_node: ast.AST) -> str:
    # normalize: remove lineno/col_offset/end_lineno/end_col_offset + ctx
    def strip(n):
        if isinstance(n, ast.AST):
            for a in ("lineno","col_offset","end_lineno","end_col_offset"):
                if hasattr(n, a):
                    setattr(n, a, None)
            if hasattr(n, "ctx"):
                setattr(n, "ctx", None)
            for k,v in ast.iter_fields(n):
                if isinstance(v, list):
                    for item in v:
                        strip(item)
                else:
                    strip(v)
    n2 = ast.fix_missing_locations(fn_node)
    strip(n2)
    return ast.dump(n2, include_attributes=False)

def hash_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()[:16]

def get_func_signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    a = fn.args
    def arg_names(args):
        return [x.arg for x in args]
    parts = []
    parts += arg_names(a.posonlyargs)
    parts += arg_names(a.args)
    if a.vararg: parts.append("*" + a.vararg.arg)
    parts += [x.arg for x in a.kwonlyargs]
    if a.kwarg: parts.append("**" + a.kwarg.arg)
    return f"{fn.name}({', '.join(parts)})"

def extract_imports(tree: ast.AST):
    imports = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                imports.append(a.name)
        elif isinstance(n, ast.ImportFrom):
            if n.module:
                imports.append(n.module)
    return imports

def resolve_local_module(root: Path, mod: str):
    # map "app.services.x" -> root/app/services/x.py
    p = root / Path(*mod.split("."))
    if p.with_suffix(".py").exists():
        return p.with_suffix(".py")
    if (p / "__init__.py").exists():
        return p / "__init__.py"
    return None

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    entry = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    files = list(iter_py_files(root))
    parsed = {}          # file -> tree
    modmap = {}          # module -> file
    file2mod = {}        # file -> module

    # Parse
    syntax_errors = []
    for f in files:
        try:
            src = read_text(f)
            tree = ast.parse(src, filename=str(f))
            parsed[f] = (src, tree)
            m = module_name(root, f)
            modmap[m] = f
            file2mod[f] = m
        except SyntaxError as e:
            syntax_errors.append(f"{f}:{e.lineno}:{e.offset} SyntaxError: {e.msg}")

    print(f"Root: {root}")
    if syntax_errors:
        print("\n(0) Syntax errors:")
        for e in syntax_errors: print(" ", e)
        return

    # (A) Shadowing: same def name in same module (last wins)
    shadow = defaultdict(list)  # file -> [(name, line1, line2..)]
    for f,(src,tree) in parsed.items():
        defs = defaultdict(list)
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs[n.name].append(n.lineno)
        for name, lines in defs.items():
            if len(lines) > 1:
                shadow[f].append((name, lines))

    # (B) Flask route collisions (decorators)
    routes = defaultdict(list)  # (path, methods_tuple) -> [(file,line,func)]
    route_pat = re.compile(r"""@app\.route\(\s*(['"])(.+?)\1(?:\s*,\s*methods\s*=\s*\[([^\]]+)\])?""")
    for f,(src,tree) in parsed.items():
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not n.decorator_list: continue
                for d in n.decorator_list:
                    try:
                        text = ast.get_source_segment(src, d) or ""
                    except Exception:
                        text = ""
                    m = route_pat.search(text)
                    if m:
                        path = m.group(2)
                        methods_raw = m.group(3)
                        if methods_raw:
                            methods = tuple(sorted([x.strip().strip("'\"") for x in methods_raw.split(",") if x.strip()]))
                        else:
                            methods = ("GET",)
                        routes[(path, methods)].append((str(f), n.lineno, n.name))

    route_dups = {k:v for k,v in routes.items() if len(v) > 1}

    # (C) Duplicate / Similar functions across workspace
    func_index = []  # (file, lineno, qualname, sig, norm_dump, hash, src_segment)
    for f,(src,tree) in parsed.items():
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                dump = norm_ast_dump(n)
                h = hash_str(dump)
                seg = ast.get_source_segment(src, n) or ""
                sig = get_func_signature(n)
                func_index.append((f, n.lineno, n.name, sig, dump, h, seg))

    by_hash = defaultdict(list)
    for item in func_index:
        by_hash[item[5]].append(item)

    identical = {h:v for h,v in by_hash.items() if len(v) > 1}

    # Similarity (heavy): compare same-name or same-signature only
    by_name = defaultdict(list)
    by_sig = defaultdict(list)
    for it in func_index:
        by_name[it[2]].append(it)
        by_sig[it[3]].append(it)

    similar_hits = []  # (score, a, b)
    def consider_group(group):
        items = group
        if len(items) < 2: return
        for i in range(len(items)):
            for j in range(i+1, len(items)):
                a = items[i]; b = items[j]
                if a[0] == b[0]:  # same file handled by shadowing already
                    continue
                # compare normalized dumps (structure) first
                s = similarity(a[4], b[4])
                if s >= 0.92 and a[5] != b[5]:
                    similar_hits.append((s, a, b))

    for nm, items in by_name.items():
        if len(items) >= 2:
            consider_group(items)
    for sg, items in by_sig.items():
        if len(items) >= 2:
            consider_group(items)

    similar_hits.sort(reverse=True, key=lambda x: x[0])

    # (D) Import graph + reachable files from entrypoint
    imports_graph = defaultdict(set)  # file -> set(files)
    for f,(src,tree) in parsed.items():
        imps = extract_imports(tree)
        for mod in imps:
            # only resolve local modules
            target = resolve_local_module(root, mod)
            if target and target in parsed:
                imports_graph[f].add(target)

    reachable = set()
    if entry:
        entry = entry.resolve()
        if not entry.exists():
            print(f"\n[WARN] entry not found: {entry}")
        else:
            q = deque([entry])
            while q:
                cur = q.popleft()
                if cur in reachable: continue
                reachable.add(cur)
                for nxt in imports_graph.get(cur, []):
                    if nxt not in reachable:
                        q.append(nxt)

    # REPORT
    print("\n(1) Shadowing (def ชื่อซ้ำในไฟล์เดียวกัน -> ตัวท้ายทับตัวก่อน)")
    if not shadow:
        print("  OK: none")
    else:
        for f, items in shadow.items():
            print(f"  {f}")
            for name, lines in items:
                print(f"    - {name}: lines {lines}")

    print("\n(2) Route collisions (@app.route path+methods ซ้ำ)")
    if not route_dups:
        print("  OK: none")
    else:
        for (path, methods), locs in sorted(route_dups.items()):
            print(f"  - {path} {methods}")
            for ff, ln, fn in locs:
                print(f"    {ff}:{ln} {fn}")

    print("\n(3) Identical functions (โค้ดเหมือนกันเป๊ะ)")
    if not identical:
        print("  OK: none")
    else:
        for h, items in identical.items():
            print(f"  - hash={h} count={len(items)}")
            for f,ln,name,sig,_,_,_ in items:
                print(f"    {f}:{ln} {sig}")

    print("\n(4) Highly similar functions (โครงสร้างคล้ายกันมาก >=0.92)")
    if not similar_hits:
        print("  OK: none")
    else:
        for s,a,b in similar_hits[:30]:
            af,al,an,asig,_,_,_ = a
            bf,bl,bn,bsig,_,_,_ = b
            print(f"  - score={s:.3f}")
            print(f"    A: {af}:{al} {asig}")
            print(f"    B: {bf}:{bl} {bsig}")

    if entry:
        print(f"\n(5) Reachability from entrypoint: {entry}")
        print(f"  reachable_files = {len(reachable)} / all_files = {len(files)}")
        dead = [f for f in files if f not in reachable]
        # show only within root, sorted
        dead = sorted(dead, key=lambda x: str(x))
        print("  possibly-unreferenced (by import graph only):")
        for f in dead[:60]:
            print(f"   - {f}")
        if len(dead) > 60:
            print(f"   ... (+{len(dead)-60} more)")

if __name__ == "__main__":
    main()
