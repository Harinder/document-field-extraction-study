# Results in full

[Back to the README](../README.md)

## The headline number

```
unrepeated-field F1   0.6649  ->  0.7212      (+0.0563)
      precision       0.6223  ->  0.6772
      recall          0.7139  ->  0.7713
```

Everything that number depends on, in one place:

| setting | value |
|---|---|
| Dataset | VRDU Ad-buy Forms (Google Research), FCC political advertising public files |
| Split | `DeepForm-kno_template-train_200-test_141-valid_100-SD_0`, seed 0 |
| Denominator | 141 test documents, 9 unrepeated fields (1269 slots). Not the 5 line-item fields |
| Labels | Google Research's annotations |
| Scorer | Google Research's `vrdu/evaluate.py`, vendored unmodified in `vendor/vrdu/` |
| Model | `qwen3:14b` (14.8B params, Q4_K_M) via Ollama, `num_ctx 32768`, temperature 0, `think=false`, per-field `maxLength 120` |
| Prompt | `prompts/v4_whose.txt`. Zero-shot, single call, constrained JSON output |
| Failures | 0 documents failed or were skipped in any scored run |
| Cost | $0, entirely local |

The left number is the first prompt I wrote, the right one is the best of three
single-factor revisions. All four are scored in
[`ablation_results.md`](../ablation_results.md), and each revision's hypothesis
was written down before it ran, at the top of its log in `traces/`. None of the
three lowered the overall score, but `v3_complete` made six of the other eight
fields slightly worse.

## What this number does not cover

It is a single-template split. The published VRDU baseline of 30.05 is *mixed*
template across all 14 fields, which is a harder regime, so I am not claiming the
comparison.

It leaves out the five line-item fields, which need table-row alignment that I
did not attempt. This matters more than it sounds: micro F1 across all 14 fields
is 0.359 and macro is 0.591, because line-item instances dominate the corpus and
score zero. The unrepeated aggregate is the only one of the three that describes
what was actually built, which is why it needs its denominator attached every
time it is quoted.

The metric is also more forgiving than "actually right". `AddressMatch` accepts
anything within three edits of gold. `PriceMatch` tolerates 0.01, and its own
docstring example treats `$3.14` and `3.1415926` as equal. `NumericalStringMatch`
strips every non-digit from `contract_num`, so a completely different identifier
whose digits happen to coincide scores as a match. Details in
[ADR 0001](adr/0001-what-correct-means.md).

Two things I would fix before treating 0.7212 as a real result. All four arms
were scored against the same 141 test documents, so it is selected-on-test and
optimistic. And the split's 100-document valid set has never been run, which
means I held nothing back and have no clean surface left to confirm on. Both are
my own doing and I would rather say so than present a tuned number as a held-out
one.

Finally, a correction. I used to report a hard recall ceiling of 0.90 for
`tv_address`, because 23 of its 231 gold values do not appear in the OCR text as
one piece. That was wrong. Google's own character spans place each of the 23 in
two or three separate parts of the text, with other form labels in between, so
they have to be reassembled rather than copied, but every one is on the page.
It is part of why `tv_address` is the worst field (FINDINGS 27).

## Per-field results

Failure is concentrated rather than spread out. Two fields carry most of it.

| field | first prompt | best | delta | note |
|---|---|---|---|---|
| gross_amount | 0.968 | 0.968 | 0 | effectively solved |
| advertiser | 0.868 | 0.897 | +0.029 | |
| product | 0.741 | 0.748 | +0.007 | |
| flight_to | 0.722 | 0.717 | -0.005 | |
| flight_from | 0.698 | 0.682 | -0.016 | |
| contract_num | 0.616 | 0.679 | +0.063 | gained without being named in the prompt |
| property | 0.531 | 0.612 | +0.081 | |
| tv_address | 0.256 | 0.534 | +0.278 | worst field, largest gain |
| agency | 0.512 | 0.581 | +0.069 | P 0.440 / R 0.855 |

Regenerate the table with `uv run python score_arm.py [arm]`. No inference needed.

`agency` and `tv_address` look like the same problem in aggregate and need
opposite fixes. 81% of `agency` failures are documents that contain no agency at
all, so its lever is abstention. 54% of `tv_address` failures are the wrong value
picked off a page carrying four different addresses, so its lever is
disambiguation. If abstention were perfect it would be worth +0.256 on `agency`
and +0.024 on `tv_address`. The same fix, ten times the value on one field, and
nothing in the overall score lets you see that.

## The four arms

| arm | F1 | delta | what changed | what happened |
|---|---|---|---|---|
| `v1_baseline` | 0.6649 | | first prompt, `prompts/v1.txt`, run by `baseline.py` | |
| `v2_abstain` | 0.6784 | +0.0135 | explicit null rule | abstention rose 6x and still reached only a quarter of absent cases |
| `v3_complete` | 0.6810 | +0.0161 | ask for complete multi-line values | hit its target (`tv_address` +0.142) and made six of the other eight fields slightly worse |
| `v4_whose` | 0.7212 | +0.0563 | say which organisation each field refers to | best arm, and it failed at the thing it was written to do |
