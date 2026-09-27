"""Score any cached arm without re-running inference.

Every arm's raw responses live under traces/<split>[__<arm>]/, one JSON per
document, so any number in the README can be regenerated from cache:

  uv run python score_arm.py                # v1 baseline
  uv run python score_arm.py v4_whose
"""
import json, os, sys
sys.path.insert(0, "vendor")
from vrdu import benchmark_utils

SPLIT = "DeepForm-kno_template-train_200-test_141-valid_100-SD_0"
FIELDS = ["advertiser","agency","contract_num","flight_from","flight_to",
          "gross_amount","product","tv_address","property"]

ARM = sys.argv[1] if len(sys.argv) > 1 else None
cache = f"traces/{SPLIT}__{ARM}" if ARM else f"traces/{SPLIT}"
if not os.path.isdir(cache): sys.exit(f"no cache at {cache}")

results = {}
for name in sorted(os.listdir(cache)):
    if not name.endswith(".json"): continue
    p = json.load(open(os.path.join(cache, name)))
    results[name[:-5]] = [[k, [v]] for k, v in p.items() if k in FIELDS and v]

b = benchmark_utils.DataUtils("data/vrdu/main/")
b.update_splits(f"data/vrdu/few_shot-splits/{SPLIT}.json")
res = benchmark_utils.evaluate({"meta": {"arm": ARM or "v1_baseline"},
                                "results": results}, b)

print(f"arm {ARM or 'v1_baseline'}   {len(results)} documents scored from cache")
print("  unrepeated F1 %.4f  P %.4f  R %.4f" % (res["unrepeated_f1"],
      res["unrepeated_precision"], res["unrepeated_recall"]))
for f in FIELDS:
    print("    %-14s F1 %.3f  P %.3f  R %.3f" % (f, res[f+"_f1"], res[f+"_precision"], res[f+"_recall"]))
