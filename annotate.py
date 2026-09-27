"""Step 5: open-coding tool.

Walks you through FAILURES one at a time, shows where the predicted value and
the gold value each appear in the document, and captures a free-text note.

Deliberately offers NO categories. You invent them afterwards from your own
notes. Categories chosen before looking encode your priors, not the system's
behaviour.

  uv run python annotate.py              # random failures, all fields
  uv run python annotate.py tv_address   # one field only
  uv run python annotate.py --stats      # progress so far

Keys: type a note and Enter to save. Blank to skip. 'q', 'quit' or 'exit' to
stop (resumable).
"""
import gzip, json, os, random, sys
sys.path.insert(0, "vendor")
from vrdu import match_utils as m

SPLIT = "DeepForm-kno_template-train_200-test_141-valid_100-SD_0"
CACHE = f"traces/{SPLIT}"
NOTES = "annotations/open_coding.jsonl"
MATCHERS = {"advertiser":"GeneralStringMatch","agency":"GeneralStringMatch",
            "product":"GeneralStringMatch","property":"GeneralStringMatch",
            "contract_num":"NumericalStringMatch","flight_from":"DateMatch",
            "flight_to":"DateMatch","gross_amount":"PriceMatch",
            "tv_address":"AddressMatch"}
os.makedirs("annotations", exist_ok=True)

if "--stats" in sys.argv:
    done = [json.loads(l) for l in open(NOTES)] if os.path.exists(NOTES) else []
    print(f"{len(done)} cases coded")
    from collections import Counter
    for f, c in Counter(d["field"] for d in done).most_common():
        print(f"  {f:<14} {c}")
    sys.exit()

only = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
seen = {(json.loads(l)["doc"], json.loads(l)["field"])
        for l in open(NOTES)} if os.path.exists(NOTES) else set()

cached = {f[:-5] for f in os.listdir(CACHE)}
docs = {}
with gzip.open("data/adbuy.jsonl.gz", "rt") as fh:
    for line in fh:
        d = json.loads(line)
        if d["filename"] in cached: docs[d["filename"]] = d

def context(text, needle, width=90):
    """Show where a value sits in the document, with surrounding text."""
    if not needle: return "(none)"
    i = text.find(str(needle))
    if i < 0:
        i = " ".join(text.split()).find(" ".join(str(needle).split()))
        if i < 0: return "NOT FOUND IN DOCUMENT"
        text = " ".join(text.split())
    s, e = max(0, i - width), min(len(text), i + len(str(needle)) + width)
    return "..." + text[s:e].replace("\n", " / ") + "..."

failures = []
for fn, d in docs.items():
    gold = {n: [o[0] for o in occ] for n, occ in d["annotations"] if isinstance(n, str)}
    pred = json.load(open(os.path.join(CACHE, fn + ".json")))
    for f in MATCHERS:
        if only and f != only: continue
        if (fn, f) in seen: continue
        p, gv = pred.get(f), gold.get(f, [])
        ok = bool(p) and bool(gv) and getattr(m, MATCHERS[f]).match([p], [[x] for x in gv])
        if not ok and (p or gv):
            failures.append((fn, f, p, gv))

random.seed(0)                      # reproducible sample, not cherry-picked
random.shuffle(failures)
print(f"{len(failures)} uncoded failures" + (f" in {only}" if only else "") + "\n")

out = open(NOTES, "a")
for i, (fn, f, p, gv) in enumerate(failures, 1):
    text = docs[fn]["ocr"]["text"]
    print("=" * 78)
    print(f"[{i}/{len(failures)}]  {f}   {fn[:16]}")
    print(f"\n  PREDICTED: {p!r}")
    print(f"    context: {context(text, p)}")
    print(f"\n  GOLD:      {gv[:2] if gv else None}")
    print(f"    context: {context(text, gv[0] if gv else None)}")
    try:
        note = input("\n  note (blank=skip, q=quit) > ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if note.lower() in ("q", "quit", "exit"): break
    if note:
        out.write(json.dumps({"doc": fn, "field": f, "pred": p,
                              "gold": gv, "note": note}) + "\n")
        out.flush()
out.close()
print("\nnotes in", NOTES)
