# tools/bump_version.py
from pathlib import Path

p = Path("version.txt")
v = (p.read_text().strip() if p.exists() else "2.3.0")
a, b, c = [int(x) for x in v.split(".")]
c += 1
nv = f"{a}.{b}.{c}"
p.write_text(nv + "\n")
print(nv)