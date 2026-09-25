"""Write the failure cases to a plain text file you can open and fill in."""
import gzip, json, os, random, re, sys
sys.path.insert(0, "vendor")
from vrdu import match_utils as m

FIELD = sys.argv[1] if len(sys.argv) > 1 else "tv_address"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 10
SPLIT = "DeepForm-kno_template-train_200-test_141-valid_100-SD_0"
CACHE = f"traces/{SPLIT}"
MATCH = {"advertiser":"GeneralStringMatch","agency":"GeneralStringMatch",
         "product":"GeneralStringMatch","property":"GeneralStringMatch",
         "contract_num":"NumericalStringMatch","flight_from":"DateMatch",
         "flight_to":"DateMatch","gross_amount":"PriceMatch",
         "tv_address":"AddressMatch"}

cached = {f[:-5] for f in os.listdir(CACHE)}
docs = {}
with gzip.open("data/adbuy.jsonl.gz", "rt") as fh:
    for line in fh:
        d = json.loads(line)
        if d["filename"] in cached: docs[d["filename"]] = d

def before(text, v, w=60):
    if not v: return ""
    i = text.find(str(v).split("\n")[0])
    if i < 0:
        t = " ".join(text.split()); i = t.find(" ".join(str(v).split())[:25])
        if i < 0: return "(value is scattered across the page)"
        text = t
    return text[max(0, i-w):i].replace("\n", " / ").strip()

fails = []
for fn, d in docs.items():
    gold = {n: [o[0] for o in occ] for n, occ in d["annotations"] if isinstance(n, str)}
    pred = json.load(open(os.path.join(CACHE, fn + ".json")))
    p, gv = pred.get(FIELD), gold.get(FIELD, [])
    ok = bool(p) and bool(gv) and getattr(m, MATCH[FIELD]).match([p], [[x] for x in gv])
    if not ok and (p or gv):
        fails.append((fn, p, gv, d["ocr"]["text"]))
random.seed(0); random.shuffle(fails)

out = f"annotations/label_{FIELD}.txt"
os.makedirs("annotations", exist_ok=True)
with open(out, "w") as f:
    f.write(f"LABELLING: {FIELD}   ({len(fails)} failures total, showing {N})\n\n")
    f.write("Put one of these after 'label:' on each case.\n")
    f.write("  incomplete      right value, but truncated (missing city/state/zip)\n")
    f.write("  wrong company   a real address, but the wrong organisation's\n")
    f.write("  not an address  returned something that is not an address\n")
    f.write("  spurious        document has no such field, model returned one anyway\n")
    f.write("  ???             does not fit any of the above (say why)\n")
    f.write("\n" + "=" * 70 + "\n\n")
    for i, (fn, p, gv, text) in enumerate(fails[:N], 1):
        g = gv[0].strip().replace("\n", ", ") if gv else None
        f.write(f"CASE {i}  ({fn[:16]})\n")
        f.write(f"  model gave  : {p!r}\n")
        f.write(f"  text before : ...{before(text, p)}\n")
        f.write(f"  correct is  : {g!r}\n")
        f.write(f"  label: \n\n")
print(f"wrote {out}")
print(f"open it with:  open -e {out}")
