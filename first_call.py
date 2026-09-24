"""First call. 6 fields, 5 documents, no scoring. Look at the output.

TODO(you): after reading meta.json, revise the schema and prompts/v1.txt.
The field set below is a first guess, not the answer.
"""
import gzip, json, os, sys
from typing import Optional
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

sys.path.insert(0, "vendor")
from vrdu import match_utils          # Google's matchers, not my own logic
MATCHERS = {
    "advertiser": "GeneralStringMatch", "agency": "GeneralStringMatch",
    "product": "GeneralStringMatch",    "property": "GeneralStringMatch",
    "contract_num": "NumericalStringMatch",
    "flight_from": "DateMatch",         "flight_to": "DateMatch",
    "gross_amount": "PriceMatch",       "tv_address": "AddressMatch",
}

def official_match(field, predicted, gold_values):
    """True if `predicted` matches any gold occurrence, per Google's rules."""
    if predicted is None or not gold_values:
        return predicted is None and not gold_values
    cls = getattr(match_utils, MATCHERS[field])
    return cls.match([predicted], [[g] for g in gold_values])

load_dotenv()

# Provider is config, not code. Flip by editing .env only.
#   OpenAI:     leave BASE_URL unset
#   Muse Spark: BASE_URL=https://api.meta.ai/v1  MODEL=muse-spark-1.1
BASE_URL = os.environ.get("BASE_URL") or None
MODEL    = os.environ.get("MODEL", "gpt-5")   # TODO: pin a dated snapshot
API_KEY  = os.environ.get("OPENAI_API_KEY") or os.environ.get("MODEL_API_KEY")
N_DOCS   = int(os.environ.get("N_DOCS", "5"))

if not API_KEY:
    sys.exit("No API key, set OPENAI_API_KEY or MODEL_API_KEY in .env")

class AdBuy(BaseModel):
    advertiser: Optional[str]
    product: Optional[str]
    property: Optional[str]      # the station call sign
    contract_num: Optional[str]
    flight_from: Optional[str]
    gross_amount: Optional[str]

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
PROMPT = open("prompts/v1.txt").read()

with gzip.open("data/adbuy.jsonl.gz", "rt") as f:
    docs = [json.loads(next(f)) for _ in range(N_DOCS)]

total_in = total_out = 0
results = []
for d in docs:
    # chat.completions works on OpenAI, Ollama, Muse Spark, anything
    # OpenAI-compatible. responses.parse() is OpenAI-only.
    r = client.chat.completions.parse(
        model=MODEL,
        messages=[{"role": "system", "content": PROMPT},
                  {"role": "user", "content": d["ocr"]["text"]}],
        response_format=AdBuy,
        # temperature 0 reduces (does not eliminate) run-to-run variance.
        # qwen3 defaults to 0.6, which made the same prompt give three
        # different contract_num answers across two runs. See FINDINGS 7.
        temperature=0,
        # NOTE: think=False is NOT honoured on Ollama's /v1 endpoint, and
        # /no_think in the prompt does not work either. Thinking is baked
        # into the chat template. Costs ~3k output tokens per document in
        # wall-clock, not money. Open item; also a week 7 ablation arm.
    )
    pred = r.choices[0].message.parsed.model_dump()
    # Unrepeated fields have a string key. Line-item rows have a LIST key
    # (the tuple of fields in that row), skipped here, see ADR 0001.
    gold = {name: sorted({o[0].strip() for o in occs})
            for name, occs in d["annotations"] if isinstance(name, str)}

    print("=" * 78)
    print(d["filename"])
    print("%-2s %-15s %-28s %s" % ("", "FIELD", "PREDICTED", "GOLD"))
    for k in pred:
        g = gold.get(k, [])
        ok = official_match(k, pred[k], g)
        mark = "OK" if ok else "XX"
        results.append(ok)
        print("%-2s %-15s %-28r %r" % (mark, k, pred[k], g[:2] if g else None))
    total_in += r.usage.prompt_tokens
    total_out += r.usage.completion_tokens

print("=" * 72)
print("tokens: %d in / %d out across %d docs" % (total_in, total_out, N_DOCS))
print("model returned:", r.model)
print("matched %d/%d fields (informal, real scoring comes from the evaluator)" % (sum(results), len(results)))
