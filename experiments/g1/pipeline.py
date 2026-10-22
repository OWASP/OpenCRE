import sqlite3, subprocess, sys, os
from pathlib import Path
import postfilter as P
os.environ["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
repos = sys.argv[1:]
db = sqlite3.connect("graph.sqlite")
mx = lambda: db.execute("select coalesce(max(id),0) from fact").fetchone()[0]
m0 = mx()
subprocess.run([sys.executable, "extract.py", *repos], check=True)
db = sqlite3.connect("graph.sqlite"); m1 = mx()
P.pass1(db, m0, m1); db.commit()
subprocess.run([sys.executable, "extract2.py", *repos], check=True)
db = sqlite3.connect("graph.sqlite"); m2 = mx()
P.pass2(db, m1, m2); db.commit()
subprocess.run([sys.executable, "verify.py", str(m1)], check=True)
Path("ranges.txt").write_text(f"{m0} {m1} {m2}\n")
print("RANGES", m0, m1, m2)
