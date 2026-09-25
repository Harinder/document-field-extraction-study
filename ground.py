"""Step 4: grounding.

A value the model emitted should appear in the source OCR text. If it does not,
the model invented it. This runs entirely off cached predictions, so it costs
no inference and can be re-run freely.

Measures three things:
  1. Groundable rate per field: how often a predicted value is literally present.
  2. Whether ungrounded predictions are more often wrong (does grounding
     actually predict correctness?).
  3. The RECALL FLOOR: gold values not present in the OCR at all, which no
     extraction system reading this text could ever reach.
"""
import gzip, json, os, re, sys
sys.path.insert(0, "vendor")
from vrdu import match_utils as m

SPLIT = "DeepForm-kno_template-train_200-test_141-valid_100-SD_0"
CACHE = f"traces/{SPLIT}"
MATCHERS = {"advertiser":"GeneralStringMatch","agency":"GeneralStringMatch",
            "product":"GeneralStringMatch","property":"GeneralStringMatch",
            "contract_num":"NumericalStringMatch","flight_from":"DateMatch",
            "flight_to":"DateMatch","gross_amount":"PriceMatch",
            "tv_address":"AddressMatch"}

def norm(s):
    """Whitespace-collapse, the same normalisation Google's matchers apply."""
    return " ".join(str(s).split())

def grounded(value, text, text_norm):
    if value is None: return None
    v = str(value)
    if v in text: return "exact"
    if norm(v) in text_norm: return "normalised"
    # last resort: all alphanumerics present in order as a loose check
    stripped = re.sub(r"[^0-9a-zA-Z]", "", v)
    if stripped and stripped in re.sub(r"[^0-9a-zA-Z]", "", text): return "alphanumeric"
    return None

cached = {f[:-5] for f in os.listdir(CACHE)}
docs = {}
with gzip.open("data/adbuy.jsonl.gz", "rt") as fh:
    for line in fh:
        d = json.loads(line)
        if d["filename"] in cached: docs[d["filename"]] = d

stats = {f: {"pred":0, "gnd":0, "ungnd":0, "gnd_right":0, "gnd_wrong":0,
             "ungnd_right":0, "ungnd_wrong":0} for f in MATCHERS}
floor = {f: {"gold":0, "present":0} for f in MATCHERS}

for fn, d in docs.items():
    text = d["ocr"]["text"]; tnorm = norm(text)
    gold = {n: [o[0] for o in occ] for n, occ in d["annotations"] if isinstance(n, str)}
    pred = json.load(open(os.path.join(CACHE, fn + ".json")))
    for f in MATCHERS:
        # recall floor: is each gold value literally in the text?
        for gv in gold.get(f, []):
            floor[f]["gold"] += 1
            if grounded(gv, text, tnorm): floor[f]["present"] += 1
        p = pred.get(f)
        if p is None: continue
        stats[f]["pred"] += 1
        g = grounded(p, text, tnorm)
        gv = gold.get(f, [])
        correct = bool(gv) and getattr(m, MATCHERS[f]).match([p], [[x] for x in gv])
        if g:
            stats[f]["gnd"] += 1
            stats[f]["gnd_right" if correct else "gnd_wrong"] += 1
        else:
            stats[f]["ungnd"] += 1
            stats[f]["ungnd_right" if correct else "ungnd_wrong"] += 1

print(f"{len(docs)} documents\n")
print("=== 1. groundable rate, and does grounding predict correctness? ===")
print("%-14s %5s %6s %7s   %-18s %-18s" % ("FIELD","pred","gnd","ungnd","grounded acc","ungrounded acc"))
for f in sorted(stats, key=lambda x: -stats[x]["ungnd"]):
    s = stats[f]
    ga = s["gnd_right"]/s["gnd"] if s["gnd"] else 0
    ua = s["ungnd_right"]/s["ungnd"] if s["ungnd"] else 0
    print("%-14s %5d %6d %7d   %5.1f%% (%3d/%3d)   %5.1f%% (%3d/%3d)" % (
        f, s["pred"], s["gnd"], s["ungnd"], 100*ga, s["gnd_right"], s["gnd"],
        100*ua, s["ungnd_right"], s["ungnd"]))

tg = sum(s["gnd"] for s in stats.values()); tu = sum(s["ungnd"] for s in stats.values())
tgr = sum(s["gnd_right"] for s in stats.values()); tur = sum(s["ungnd_right"] for s in stats.values())
print("\n  TOTAL        grounded %d (%.1f%% correct)   ungrounded %d (%.1f%% correct)" % (
    tg, 100*tgr/tg if tg else 0, tu, 100*tur/tu if tu else 0))

print("\n=== 2. recall floor: gold values not present in the OCR at all ===")
print("%-14s %6s %9s %8s" % ("FIELD","gold","in text","floor"))
for f in sorted(floor, key=lambda x: floor[x]["present"]/floor[x]["gold"] if floor[x]["gold"] else 1):
    d_ = floor[f]
    if not d_["gold"]: continue
    print("%-14s %6d %9d %7.1f%%" % (f, d_["gold"], d_["present"], 100*d_["present"]/d_["gold"]))
tot = sum(d_["gold"] for d_ in floor.values()); pres = sum(d_["present"] for d_ in floor.values())
print("\n  Overall recall ceiling: %.1f%% (%d of %d gold values are literally in the text)" % (
    100*pres/tot, pres, tot))
