"""Step 3: run the 9 unrepeated fields over a split's test set and write
predictions in the format Google's evaluate.py expects.

Caches every model response to traces/ keyed by filename, so a crashed or
interrupted run resumes for free and re-scoring costs nothing.

Usage:
  uv run python baseline.py DeepForm-kno_template-train_200-test_141-valid_100-SD_0
  uv run python baseline.py <split> --limit 10        # smoke test first
"""
import gzip, json, os, sys, time, urllib.request
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()
BASE_URL = os.environ.get("BASE_URL") or "http://localhost:11434/v1"
MODEL = os.environ.get("MODEL", "qwen3-14b-32k")

SPLIT = sys.argv[1] if len(sys.argv) > 1 else None
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
if not SPLIT:
    sys.exit(__doc__)

SPLIT_PATH = f"data/vrdu/few_shot-splits/{SPLIT}.json"
CACHE_DIR = f"traces/{SPLIT}"
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs("predictions", exist_ok=True)

# The 9 unrepeated fields. Line items are deliberately out of scope, see ADR 0001.
class AdBuy(BaseModel):
    advertiser: Optional[str]
    agency: Optional[str]
    contract_num: Optional[str]
    flight_from: Optional[str]
    flight_to: Optional[str]
    gross_amount: Optional[str]
    product: Optional[str]
    tv_address: Optional[str]
    property: Optional[str]

# Guard against drift between my schema and Google's field list.
META = json.load(open("data/vrdu/main/meta.json"))
declared = {k for k, v in META["entity_appearance_pattern"].items() if v == "unrepeated"}
mine = set(AdBuy.model_fields)
if mine != declared:
    sys.exit(f"schema drift: mine-theirs={mine - declared} theirs-mine={declared - mine}")

test_files = set(json.load(open(SPLIT_PATH))["test"])
print(f"split {SPLIT}: {len(test_files)} test documents")

docs = {}
with gzip.open("data/adbuy.jsonl.gz", "rt") as f:
    for line in f:
        d = json.loads(line)
        if d["filename"] in test_files:
            docs[d["filename"]] = d
print(f"matched {len(docs)} documents in the corpus")

targets = sorted(docs)[:LIMIT] if LIMIT else sorted(docs)
PROMPT = open("prompts/v1.txt").read()

# Ollama's NATIVE /api/chat, not the OpenAI-compatible /v1 path.
# Reason: think=false is ignored on /v1, so qwen3 generates ~3000 tokens of
# hidden reasoning per document at ~21 tok/s, about 2.4 minutes each. On the
# native endpoint the same extraction is ~23 tokens in under a second.
# Structured output still works, via `format` with a JSON schema.
NATIVE_URL = BASE_URL.replace("/v1", "") + "/api/chat"
# Do NOT hand Pydantic's model_json_schema() straight to Ollama. It emits
# {"anyOf":[{"type":"string"},{"type":"null"}]} per field, which compiles to a
# grammar that made generation run away (1787+ tokens and climbing, timing out
# at 300s). The equivalent {"type":["string","null"]} form completes in ~14s.
# Same JSON Schema semantics, very different constrained-decoding behaviour.
# maxLength is load-bearing, not cosmetic. Without it a field is "any string,
# any length", and echoing the source document into one is valid output under
# the grammar. Measured on 05998648: unbounded TIMED OUT at 120s while
# maxLength=120 returned correct values in 6.8s. Constrained decoding
# guarantees VALID output, not SENSIBLE output, and an unconstrained model
# would simply have stopped. 120 chars also states something true about this
# domain: none of these nine values is a paragraph.
FIELDS = list(AdBuy.model_fields)
SCHEMA = {"type": "object",
          "properties": {f: {"type": ["string", "null"], "maxLength": 120}
                         for f in FIELDS},
          "required": FIELDS}

def extract(text):
    body = json.dumps({
        "model": MODEL, "stream": False, "think": False,
        "format": SCHEMA, "options": {"temperature": 0},
        "messages": [{"role": "system", "content": PROMPT},
                     {"role": "user", "content": text}],
    }).encode()
    req = urllib.request.Request(NATIVE_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=240).read(), strict=False)
    return json.loads(resp["message"]["content"], strict=False), resp.get("eval_count", 0)

results, t0, n_cached, failed = {}, time.time(), 0, []
for i, fn in enumerate(targets, 1):
    cache = os.path.join(CACHE_DIR, fn.replace("/", "_") + ".json")
    if os.path.exists(cache):
        pred = json.load(open(cache)); n_cached += 1
    else:
        # Generation time varies from ~15s to several minutes, unpredictably.
        # One retry, then record the document as failed and move on rather than
        # letting a single pathological case block the whole sweep. Failures are
        # counted and reported: a silently skipped document is a lying score.
        pred = None
        for attempt in (1, 2):
            try:
                pred, n_tok = extract(docs[fn]["ocr"]["text"])
                break
            except Exception as e:
                if attempt == 2:
                    failed.append((fn, type(e).__name__))
                    print("    FAILED %s (%s)" % (fn[:20], type(e).__name__), flush=True)
        if pred is None:
            continue
        pred = {k: pred.get(k) for k in AdBuy.model_fields}   # normalise keys
        json.dump(pred, open(cache, "w"))
    # Google's format: list of [entity_name, extracted_entity] where
    # extracted_entity[0] is the text. Nulls are omitted, not sent as empty.
    results[fn] = [[k, [v]] for k, v in pred.items() if v]
    if i % 10 == 0 or i == len(targets):
        el = time.time() - t0
        print(f"  {i}/{len(targets)}  {el:.0f}s elapsed  {n_cached} from cache", flush=True)

out = f"predictions/{SPLIT}-test_predictions.json"
json.dump({"meta": {"model": MODEL, "prompt": "v1"}, "results": results}, open(out, "w"))
print(f"\nwrote {out} ({len(results)} documents)")
if failed:
    print(f"WARNING: {len(failed)} documents failed and are absent from predictions:")
    for fn, err in failed: print(f"  {fn} ({err})")
    print("These count as complete misses in the score. Do not report the")
    print("number without stating this.")
print(f"score it:\n  PYTHONPATH=vendor uv run python -m vrdu.evaluate \\\n"
      f"    -b data/vrdu -e predictions -o eval_results.tsv")
