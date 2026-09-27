"""Print the full OCR text of one document, plus its gold labels.

  uv run python show.py 300535fe          # partial filename is fine

This is what the MODEL saw. Not the PDF, not the layout, just the text.
"""
import gzip, json, os, sys
if len(sys.argv) < 2:
    sys.exit(__doc__)
key = sys.argv[1]
CACHE = "traces/DeepForm-kno_template-train_200-test_141-valid_100-SD_0"
with gzip.open("data/adbuy.jsonl.gz", "rt") as fh:
    for line in fh:
        d = json.loads(line)
        if d["filename"].startswith(key):
            break
    else:
        sys.exit(f"no document starting with {key}")

print("=" * 78)
print("FILE:", d["filename"])
print("PDF: ", d["file_path"])
print("=" * 78)
print("\n--- GOLD LABELS ---")
for n, occ in d["annotations"]:
    if isinstance(n, str):
        print("  %-14s %r" % (n, [o[0].strip() for o in occ][:3]))
rows = [e for e in d["annotations"] if not isinstance(e[0], str)]
if rows:
    print("  %-14s %d line-item rows (not extracted, see ADR 0001)" % ("line_item", len(rows)))

p = os.path.join(CACHE, d["filename"] + ".json")
if os.path.exists(p):
    print("\n--- WHAT THE MODEL PREDICTED (v1 prompt) ---")
    for k, v in json.load(open(p)).items():
        print("  %-14s %r" % (k, v))

print("\n--- FULL OCR TEXT (what the model actually read) ---\n")
print(d["ocr"]["text"])
