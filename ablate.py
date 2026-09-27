"""Step 6: one-factor-at-a-time ablation.

Each arm changes exactly ONE thing from the baseline, and you must state your
hypothesis before it runs. Results append to ablation_results.md, including
arms that make things worse.

  uv run python ablate.py v2_abstain "abstention fix should recover most of
      agency's 69 spurious predictions, predicted agency F1 0.512 -> ~0.768"

  uv run python ablate.py v2_abstain "<hypothesis>" --limit 50   # faster directional read
"""
import gzip, json, os, sys, time, urllib.request
from dotenv import load_dotenv

load_dotenv()
BASE_URL = os.environ.get("BASE_URL") or "http://localhost:11434/v1"
MODEL = os.environ.get("MODEL", "qwen3-14b-32k")
SPLIT = "DeepForm-kno_template-train_200-test_141-valid_100-SD_0"
FIELDS = ["advertiser","agency","contract_num","flight_from","flight_to",
          "gross_amount","product","tv_address","property"]
SCHEMA = {"type":"object",
          "properties":{f:{"type":["string","null"],"maxLength":120} for f in FIELDS},
          "required":FIELDS}

if len(sys.argv) < 3:
    sys.exit(__doc__)
PROMPT_V = sys.argv[1]
HYPOTHESIS = sys.argv[2]
LIMIT = int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else None

prompt_path = f"prompts/{PROMPT_V}.txt"
if not os.path.exists(prompt_path): sys.exit(f"no such prompt: {prompt_path}")
PROMPT = open(prompt_path).read()

# Cache is keyed by prompt version so arms never reuse each other's answers.
CACHE = f"traces/{SPLIT}__{PROMPT_V}"
os.makedirs(CACHE, exist_ok=True)
NATIVE = BASE_URL.replace("/v1","") + "/api/chat"

def extract(text):
    body = json.dumps({"model":MODEL,"stream":False,"think":False,"format":SCHEMA,
        "options":{"temperature":0},
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
targets = sorted(docs)[:LIMIT] if LIMIT else sorted(docs)

print(f"arm: {PROMPT_V}   {len(targets)} documents")
print(f"hypothesis: {HYPOTHESIS}\n")
t0, failed = time.time(), []
for i, fn in enumerate(targets, 1):
    c = os.path.join(CACHE, fn + ".json")
    if os.path.exists(c): continue
    try:
        pred = extract(docs[fn]["ocr"]["text"])
        json.dump({k: pred.get(k) for k in FIELDS}, open(c,"w"))
    except Exception as e:
        failed.append(fn); print(f"  FAILED {fn[:18]} ({type(e).__name__})", flush=True)
    if i % 20 == 0: print(f"  {i}/{len(targets)}  {time.time()-t0:.0f}s", flush=True)

# score with Google's evaluator
sys.path.insert(0,"vendor")
from vrdu import benchmark_utils
results = {}
for fn in targets:
    c = os.path.join(CACHE, fn + ".json")
    if not os.path.exists(c): continue
    p = json.load(open(c))
    results[fn] = [[k,[v]] for k,v in p.items() if v]
os.makedirs("predictions-ablate", exist_ok=True)
outp = f"predictions-ablate/{SPLIT}-test_predictions.json"
json.dump({"meta":{"arm":PROMPT_V},"results":results}, open(outp,"w"))

b = benchmark_utils.DataUtils("data/vrdu/main/")
b.update_splits(f"data/vrdu/few_shot-splits/{SPLIT}.json")
res = benchmark_utils.evaluate(json.load(open(outp)), b)

line = "| %s | %.4f | %.4f | %.4f | %s |" % (PROMPT_V, res["unrepeated_f1"],
       res["unrepeated_precision"], res["unrepeated_recall"], f"{len(targets)} docs")
hdr = "| arm | unrep F1 | precision | recall | n |\n|---|---|---|---|---|\n"
if not os.path.exists("ablation_results.md"):
    open("ablation_results.md","w").write("# Ablation results\n\nOne factor changed per arm.\n\n" + hdr)
open("ablation_results.md","a").write(line + "\n")

print(f"\n  unrepeated F1 {res['unrepeated_f1']:.4f}  P {res['unrepeated_precision']:.4f}  R {res['unrepeated_recall']:.4f}")
print("\n  per field:")
for f in FIELDS:
    print("    %-14s F1 %.3f  P %.3f  R %.3f" % (f, res[f+"_f1"], res[f+"_precision"], res[f+"_recall"]))
if failed: print(f"\n  WARNING: {len(failed)} documents failed")
