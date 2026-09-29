"""Records sha256 of scoring/cases/ground-truth BEFORE any model output exists. run.py refuses to run if changed."""
import hashlib, json, subprocess
from datetime import datetime, timezone
from pathlib import Path
H = Path(__file__).parent
files = ["scoring.py", "cases.json", "ground_truth.json", "build_data.py"]
assert not (H / "raw" / "_meta.json").exists() and not list((H / "raw").glob("C*.json")), "raw outputs already exist; refusing to (re)freeze"
out = {"frozen_at": datetime.now(timezone.utc).isoformat(), "head_sha": (H / "head_sha.txt").read_text().strip(),
       "sha256": {f: hashlib.sha256((H / f).read_bytes()).hexdigest() for f in files}}
(H / "frozen.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
