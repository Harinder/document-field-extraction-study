"""Step 7: does sampling disagreement predict error?

Samples each document N times at temperature 0.7 using the best prompt, then
asks: when the samples agree, is the answer more likely to be right?

This is the first confidence signal that varies WITHIN a field, which is what
findings 48 to 52 said was missing.

  uv run python selfconsist.py 40 3      # 40 documents, 3 samples each
"""
import gzip, json, os, re, sys, time, urllib.request
from collections import Counter
sys.path.insert(0, "vendor")
from vrdu import match_utils as m
from dotenv import load_dotenv

load_dotenv()
NDOCS = int(sys.argv[1]) if len(sys.argv) > 1 else 40
NSAMP = int(sys.argv[2]) if len(sys.argv) > 2 else 3
TEMP = 0.7
MODEL = os.environ.get("MODEL", "qwen3-14b-32k")
NATIVE = (os.environ.get("BASE_URL") or "http://localhost:11434/v1").replace("/v1","") + "/api/chat"
SPLIT = "DeepForm-kno_template-train_200-test_141-valid_100-SD_0"
FIELDS = ["advertiser","agency","contract_num","flight_from","flight_to",
          "gross_amount","product","tv_address","property"]
MATCH = {"advertiser":"GeneralStringMatch","agency":"GeneralStringMatch",
         "product":"GeneralStringMatch","property":"GeneralStringMatch",
         "contract_num":"NumericalStringMatch","flight_from":"DateMatch",
         "flight_to":"DateMatch","gross_amount":"PriceMatch",
         "tv_address":"AddressMatch"}
SCHEMA = {"type":"object","properties":{f:{"type":["string","null"],"maxLength":120} for f in FIELDS},"required":FIELDS}
PROMPT = open("prompts/v4_whose.txt").read()
CACHE = f"traces/{SPLIT}__selfconsist_t{TEMP}"
os.makedirs(CACHE, exist_ok=True)

def call(text, seed):
    body = json.dumps({"model":MODEL,"stream":False,"think":False,"format":SCHEMA,
        "options":{"temperature":TEMP,"seed":seed},
        "messages":[{"role":"system","content":PROMPT},{"role":"user","content":text}]}).encode()
    req = urllib.request.Request(NATIVE, data=body, headers={"Content-Type":"application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=240).read(), strict=False)
    return json.loads(r["message"]["content"], strict=False)

test = set(json.load(open(f"data/vrdu/few_shot-splits/{SPLIT}.json"))["test"])
docs = {}
with gzip.open("data/adbuy.jsonl.gz","rt") as fh:
    for line in fh:
        d = json.loads(line)
        if d["filename"] in test: docs[d["filename"]] = d
targets = sorted(docs)[:NDOCS]
print(f"{len(targets)} documents x {NSAMP} samples at temperature {TEMP}")

t0 = time.time()
for i, fn in enumerate(targets, 1):
    for s in range(NSAMP):
        c = os.path.join(CACHE, f"{fn}__s{s}.json")
        if os.path.exists(c): continue
        try:
            json.dump(call(docs[fn]["ocr"]["text"], 1000+s), open(c,"w"))
        except Exception as e:
            print(f"  FAILED {fn[:14]} s{s} ({type(e).__name__})", flush=True)
    if i % 10 == 0: print(f"  {i}/{len(targets)}  {time.time()-t0:.0f}s", flush=True)

def norm(v): return re.sub(r"[^0-9a-z]","",str(v).lower()) if v is not None else "<null>"

buckets = {}
for fn in targets:
    gold = {n:[o[0] for o in occ] for n,occ in docs[fn]["annotations"] if isinstance(n,str)}
    samples = []
    for s in range(NSAMP):
        c = os.path.join(CACHE, f"{fn}__s{s}.json")
        if os.path.exists(c): samples.append(json.load(open(c)))
    if len(samples) < NSAMP: continue
    for f in FIELDS:
        vals = [sm.get(f) for sm in samples]
        cnt = Counter(norm(v) for v in vals)
        top, agree = cnt.most_common(1)[0]
        majority = next(v for v in vals if norm(v) == top)
        gv = gold.get(f, [])
        if majority is None:
            correct = not gv
        else:
            correct = bool(gv) and getattr(m, MATCH[f]).match([majority], [[x] for x in gv])
        buckets.setdefault(agree, []).append(correct)

print(f"\n=== does agreement predict correctness? ({NSAMP} samples) ===")
print("  %-22s %8s %10s" % ("samples agreeing", "n", "accuracy"))
for a in sorted(buckets, reverse=True):
    b = buckets[a]
    print("  %d of %d agree%-11s %8d %9.1f%%" % (a, NSAMP, "", len(b), 100*sum(b)/len(b)))
allv = [x for b in buckets.values() for x in b]
print("  %-22s %8d %9.1f%%" % ("(all)", len(allv), 100*sum(allv)/len(allv)))
