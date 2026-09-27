"""Format probe: build a predictions file from whatever is cached, so Google's
evaluator can be tried on it before a full run exists. It does not run the
evaluator itself.

I wrote it when only a few documents were cached, so the score meant nothing.
The point was whether the FILE FORMAT is accepted, in seconds rather than
after a multi-hour run.

  uv run python check_format.py <split>
  PYTHONPATH=vendor uv run python -m vrdu.evaluate -b data/vrdu -e predictions-probe -o /tmp/probe.tsv
"""
import json, os, sys, glob

if len(sys.argv) < 2:
    sys.exit(__doc__)
SPLIT = sys.argv[1]
cache_dir = f"traces/{SPLIT}"
files = glob.glob(os.path.join(cache_dir, "*.json"))
if not files:
    sys.exit(f"nothing cached yet in {cache_dir}")

results = {}
for path in files:
    fn = os.path.basename(path)[:-5]          # strip .json, restore .pdf name
    pred = json.load(open(path))
    results[fn] = [[k, [v]] for k, v in pred.items() if v]

os.makedirs("predictions-probe", exist_ok=True)
out = f"predictions-probe/{SPLIT}-test_predictions.json"
json.dump({"meta": {"probe": True}, "results": results}, open(out, "w"))
print(f"built {out} from {len(results)} cached documents")
print(f"sample entry: {json.dumps(list(results.values())[0][:2])}")
