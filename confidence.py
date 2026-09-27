"""Step 7: can we tell good answers from bad ones without re-running the model?

Builds a confidence score from features already available in the cached
predictions, then draws a risk-coverage curve: if we keep only the top X% most
confident answers, how accurate are they?

No new inference. Runs on the v4_whose arm (the best prompt).
"""
import gzip, json, os, re, sys
sys.path.insert(0, "vendor")
from vrdu import match_utils as m

ARM = sys.argv[1] if len(sys.argv) > 1 else "v4_whose"
SPLIT = "DeepForm-kno_template-train_200-test_141-valid_100-SD_0"
CACHE = f"traces/{SPLIT}__{ARM}" if ARM != "v1_baseline" else f"traces/{SPLIT}"
MATCH = {"advertiser":"GeneralStringMatch","agency":"GeneralStringMatch",
         "product":"GeneralStringMatch","property":"GeneralStringMatch",
         "contract_num":"NumericalStringMatch","flight_from":"DateMatch",
         "flight_to":"DateMatch","gross_amount":"PriceMatch",
         "tv_address":"AddressMatch"}

test = set(json.load(open(f"data/vrdu/few_shot-splits/{SPLIT}.json"))["test"])
docs = {}
with gzip.open("data/adbuy.jsonl.gz", "rt") as fh:
    for line in fh:
        d = json.loads(line)
        if d["filename"] in test: docs[d["filename"]] = d

def grounding(v, text):
    """How well does this value sit in the source text? Higher is better."""
    s = str(v)
    if s in text: return 3                                   # exact
    if " ".join(s.split()) in " ".join(text.split()): return 2   # whitespace-only diff
    ta = re.sub(r"[^0-9a-zA-Z]", "", text)
    ws = [re.sub(r"[^0-9a-zA-Z]", "", w) for w in s.split()]
    ws = [w for w in ws if w]
    if ws and all(w in ta for w in ws): return 1             # reassembled from fragments
    return 0                                                  # not present at all

rows = []
for fn, d in docs.items():
    p = os.path.join(CACHE, fn + ".json")
    if not os.path.exists(p): continue
    text = d["ocr"]["text"]
    gold = {n: [o[0] for o in occ] for n, occ in d["annotations"] if isinstance(n, str)}
    pred = json.load(open(p))
    for f, matcher in MATCH.items():
        v = pred.get(f)
        if v is None: continue                 # abstentions are not scored here
        gv = gold.get(f, [])
        correct = bool(gv) and getattr(m, matcher).match([v], [[x] for x in gv])
        rows.append({"field": f, "value": str(v), "correct": correct,
                     "ground": grounding(v, text)})

n = len(rows); acc = sum(r["correct"] for r in rows)/n
print(f"arm {ARM}: {n} non-null predictions, {100*acc:.1f}% correct overall\n")

print("=== single features: does each separate right from wrong? ===")
for name, key, vals in [("grounding score", "ground", [3,2,1,0])]:
    print(f"  {name}:")
    for v in vals:
        sub = [r for r in rows if r[key] == v]
        if sub:
            print("    %-14s %4d predictions  %5.1f%% correct" % (
                {3:"exact",2:"whitespace",1:"reassembled",0:"absent"}[v],
                len(sub), 100*sum(x["correct"] for x in sub)/len(sub)))

print("\n=== per-field base rates (the strongest single signal) ===")
for f in sorted(MATCH, key=lambda x: -sum(r["correct"] for r in rows if r["field"]==x)/max(1,len([r for r in rows if r["field"]==x]))):
    sub = [r for r in rows if r["field"] == f]
    if sub:
        print("  %-14s %4d  %5.1f%% correct" % (f, len(sub), 100*sum(r["correct"] for r in sub)/len(sub)))

# ---------------------------------------------------------------------------
# Risk-coverage curve.
#
# LEAKAGE WARNING, stated up front: the per-field rates used to rank below are
# computed on the SAME data being scored. That inflates the curve and the
# numbers are illustrative only. The honest version fits rates on the split's
# valid set (100 documents, never used so far) and reports on test. That run
# has not been done yet, see docs/open-questions.md.
# ---------------------------------------------------------------------------
field_rate = {}
for f in MATCH:
    sub = [r for r in rows if r["field"] == f]
    field_rate[f] = sum(r["correct"] for r in sub)/len(sub) if sub else 0

GROUND_W = {3: 0.0, 2: -0.25, 1: -0.35, 0: -0.60}
for r in rows:
    r["conf"] = field_rate[r["field"]] + GROUND_W[r["ground"]]

ranked = sorted(rows, key=lambda r: -r["conf"])
print("\n=== risk-coverage curve (LEAKY, see warning in source) ===")
print("  %8s %10s %10s %12s" % ("coverage", "kept", "accuracy", "errors kept"))
for pct in [100, 90, 80, 70, 60, 50, 40, 30]:
    k = int(len(ranked) * pct / 100)
    sub = ranked[:k]
    a = sum(r["correct"] for r in sub)/len(sub)
    print("  %7d%% %10d %9.1f%% %12d" % (pct, k, 100*a, len(sub)-sum(r["correct"] for r in sub)))

print("\n=== what abstaining on the worst fields alone would give ===")
order = sorted(MATCH, key=lambda f: field_rate[f])
kept = list(rows)
print("  %-28s %8s %10s" % ("keeping", "preds", "accuracy"))
print("  %-28s %8d %9.1f%%" % ("all 9 fields", len(kept), 100*sum(r['correct'] for r in kept)/len(kept)))
for i in range(1, 5):
    drop = set(order[:i])
    sub = [r for r in rows if r["field"] not in drop]
    print("  %-28s %8d %9.1f%%" % ("drop " + ", ".join(order[:i]), len(sub),
          100*sum(r["correct"] for r in sub)/len(sub)))
