"""Build a predictions file from whatever is cached and run Google's evaluator.

The score will be terrible (most documents are missing) but that is not the
point: this answers whether the FILE FORMAT is accepted, in seconds rather
than after a multi-hour run.
"""
import json, os, sys, glob

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
