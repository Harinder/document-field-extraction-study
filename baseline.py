"""Step 3: run the 9 unrepeated fields over a split's test set and write
predictions in the format Google's evaluate.py expects.

Caches every model response to traces/ keyed by filename, so a crashed or
interrupted run resumes for free and re-scoring costs nothing.

Usage:
  uv run python baseline.py DeepForm-kno_template-train_200-test_141-valid_100-SD_0
  uv run python baseline.py <split> --limit 10        # smoke test first
"""
import gzip, json, os, sys, time
from typing import Optional
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()
BASE_URL = os.environ.get("BASE_URL") or None
MODEL = os.environ.get("MODEL", "gpt-5")
API_KEY = os.environ.get("OPENAI_API_KEY") or os.environ.get("MODEL_API_KEY")

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
client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
PROMPT = open("prompts/v1.txt").read()

results, t0, n_cached = {}, time.time(), 0
for i, fn in enumerate(targets, 1):
    cache = os.path.join(CACHE_DIR, fn.replace("/", "_") + ".json")
    if os.path.exists(cache):
        pred = json.load(open(cache)); n_cached += 1
    else:
        r = client.chat.completions.parse(
            model=MODEL,
            messages=[{"role": "system", "content": PROMPT},
                      {"role": "user", "content": docs[fn]["ocr"]["text"]}],
            response_format=AdBuy,
            temperature=0,
        )
        pred = r.choices[0].message.parsed.model_dump()
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
print(f"score it:\n  PYTHONPATH=vendor uv run python -m vrdu.evaluate \\\n"
      f"    -b data/vrdu -e predictions -o eval_results.tsv")
