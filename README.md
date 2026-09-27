# adbuy-extract

Pulling nine structured fields out of scanned US TV political ad-buy invoices
with a 14B model running on a laptop, scored by the benchmark authors' own
evaluator.

## Summary

### Why

Document field extraction is a problem I kept reading about without really
understanding, so I rebuilt one against a public benchmark. VRDU ships its own
annotations and its own evaluator, so correctness here is whatever Google's match
functions say it is, which removes most of the ways a project like this quietly
flatters its author.

The other reason is that "the model got better at extraction" is a claim I have
seen made a lot and explained almost never. I wanted the version where you can
say which failure mode moved and by how much.

### What

Nine fields off FCC political advertising invoices: advertiser, agency, contract
number, flight start and end, gross amount, product, station address, property.
141 test documents from VRDU Ad-buy Forms, using Google Research's annotations
and their evaluator, vendored here unmodified.

The score went from 0.665 to 0.721 unrepeated F1 across four prompt revisions.
That is the least interesting thing in the repo. The rest is a record of where
this kind of system actually breaks, which turned out not to be where I expected,
and of four infrastructure problems that would each have produced a clean-looking
run with wrong numbers in it.

### How

One call per document to `qwen3:14b` through Ollama. Temperature 0, a JSON schema
constraining the output, no fine-tuning and no few-shot examples. Everything runs
locally at zero API cost.

Then four rounds of the same loop: score, read actual failures by hand, name the
categories that show up, write down what a fix should do before doing it, change
exactly one thing, then check whether the thing you predicted is the thing that
happened. That last step is the one that kept catching me out.

Every raw model response is cached per prompt version, so any number below
regenerates off disk in about four seconds without new inference.

---

## The number

```
unrepeated-field F1   0.6649  ->  0.7212      (+0.0563)
      precision       0.6223  ->  0.6772
      recall          0.7139  ->  0.7713
```

Everything that number depends on, in one place:

| | |
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

The left number is the first prompt I wrote, the right one is the best of four
single-factor revisions. All four are in `ablation_results.md` with the
hypothesis recorded before the run, including the two that made things worse.

### What this number does not cover

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
[ADR 0001](docs/adr/0001-what-correct-means.md).

Two things I would fix before treating 0.7212 as a real result. All four arms
were scored against the same 141 test documents, so it is selected-on-test and
optimistic. And the split's 100-document valid set has never been run, which
means I held nothing back and have no clean surface left to confirm on. Both are
my own doing and I would rather say so than present a tuned number as a held-out
one.

Finally, `tv_address` has a hard recall ceiling of 0.90. Twenty-three of its 231
gold values do not appear anywhere in the OCR text, so roughly a tenth of that
field is unreachable for any system reading this input.

---

## Per-field results

Failure is concentrated rather than spread out. Two fields carry most of it.

| field | first prompt | best | delta | |
|---|---|---|---|---|
| gross_amount | 0.968 | 0.968 | 0 | effectively solved |
| advertiser | 0.868 | 0.897 | +0.029 | |
| product | 0.741 | 0.748 | +0.007 | |
| flight_to | 0.722 | 0.717 | -0.005 | |
| flight_from | 0.698 | 0.682 | -0.016 | |
| contract_num | 0.616 | 0.679 | +0.063 | gained without being named in the prompt |
| property | 0.531 | 0.612 | +0.081 | |
| tv_address | 0.256 | 0.534 | +0.278 | worst field, largest gain, ceiling 0.620 |
| agency | 0.512 | 0.581 | +0.069 | P 0.440 / R 0.855 |

Regenerate the table with `uv run python score_arm.py [arm]`. No inference needed.

`agency` and `tv_address` look like the same problem in aggregate and need
opposite fixes. 81% of `agency` failures are documents that contain no agency at
all, so its lever is abstention. 54% of `tv_address` failures are the wrong value
picked off a page carrying four different addresses, so its lever is
disambiguation. If abstention were perfect it would be worth +0.256 on `agency`
and +0.024 on `tv_address`. The same fix, ten times the value on one field, and
nothing in the overall score lets you see that.

### The four arms

| arm | F1 | delta | what changed | what happened |
|---|---|---|---|---|
| `v1_baseline` | 0.6649 | | first prompt | |
| `v2_abstain` | 0.6784 | +0.0135 | explicit null rule | abstention rose 6x and still reached only a quarter of absent cases |
| `v3_complete` | 0.6810 | +0.0161 | ask for complete multi-line values | hit its target (`tv_address` +0.142) and made six of the other eight fields slightly worse |
| `v4_whose` | 0.7212 | +0.0563 | say which organisation each field refers to | best arm, and it failed at the thing it was written to do |

---

## Confidence, and why it didn't work

A model that is 68% correct per prediction is not useful on its own. It becomes
useful if it can tell you which 20% to send to a human, so I spent a step trying
to build per-prediction confidence. Three mechanisms, measured rather than
assumed:

```
signal                     separation              reach
grounding in source text   69.8% vs 0.0% correct   5 of 1230 predictions
field identity             97.1% vs 44.0%          a prior, not confidence
self-consistency (3x)      75.1% vs 33.3%          27 of 360 predictions
```

Self-consistency is the one that works. Unanimous answers across three samples
are 75.1% correct and split answers 33.3%, and the Wilson 95% intervals don't
overlap ([70.2, 79.4] against [18.6, 52.2]), so a 42-point gap holds up even at
n=27. Per unit of coverage given away it is nearly twice as efficient as the
trivial alternative of dropping the worst fields outright: 0.43 accuracy points
per percent, against 0.25.

It also barely fires. 92.5% of predictions are unanimous at temperature 0.7, so
you pay 3x inference to flag 7.5% of your answers.

Three separate measurements turned out to be saying the same thing. Temperature 0
gives byte-identical predictions across runs. When the model returns null it is
right 100% of the time, zero false abstentions across 187 present-field cases in
two arms. And at temperature 0.7 it will not disagree with itself.

The model is stable in its errors rather than uncertain about them. It is
confidently wrong, which is why a prompt asking it to abstain reached a quarter
of the cases it should have, why grounding separates almost nothing, and why no
amount of sampling will surface most of the errors. Systematic errors need a
corrective instrument, not an estimator.

There is a suspect for the cause, and it is self-inflicted. Constrained decoding
with a JSON grammar, a 120-character bound and one obvious candidate on the page
leaves very few valid next tokens at each step, and temperature can only spread
probability across choices that still exist. Structured output bought guaranteed
parseable answers and plausibly cost the ability to measure uncertainty by
sampling. That tradeoff appears in none of the "always use strict schema mode"
advice I read. It is untested here; testing it means sampling without the schema
and comparing diversity, which is the first experiment I would run next.

[ADR 0002](docs/adr/0002-confidence-and-abstention.md) has the full comparison
and the routing decision that came out of it.

---

## What I got wrong

**I read a precision of 0.384 as hallucination.** It wasn't. A grounding check
showed all 138 `agency` predictions were real text copied off the page, and
genuine fabrication came to 6 cases in 1239 predictions. The model was selecting
wrong values, not inventing them. Those two diagnoses call for completely
different fixes, thresholds and abstention for one, disambiguation and retrieval
for the other, so I would have built the wrong thing.

**My grounding check was itself wrong, and only reading a document by hand found
it.** On document `300535fe` the model predicted `16 Cypress Ave Wheeling, WV
26003` and my check called it invented. The OCR reads:

```
... Billing Calendar: / Broadcast / 16 Cypress Ave / EOM/EOC /
    Billing Cycle: / Agency Commission: / Wheeling, WV 26003 / 15% ...
```

Both halves are there, torn apart, with unrelated form labels sitting between the
street line and the city line. The model had correctly reassembled a real address
from fragments and my contiguous-substring check scored that as fabrication. Of
55 flagged predictions, 49 were reassembly and 6 were real. No aggregate would
have surfaced this. The F1 said "tv_address is bad" and the grounding check said
"27 inventions", and both were true enough to be misleading.

**All three prompt revisions improved the score through a mechanism other than
the one I designed them for.** Every time. Arm 1 aimed at abstention and
accidentally improved completeness. Arm 2 aimed at completeness, hit it, and
converted its fixed cases into a new failure category. Arm 3 aimed at
disambiguation, didn't achieve it at all, and delivered the biggest formatting fix
of the three. An F1 delta tells you whether something changed and never why. All
three would have gone down as confirmed hypotheses if I had stopped at the score,
and only the per-failure-mode breakdown caught it.

**"One factor at a time" is harder than it sounds with prompts.** I changed one
file and assumed that was one variable. Rewording the null rule also changed
copying behaviour, so two effects moved at once and partly cancelled each other:
six cases gained, three lost, on the same field. A prompt is a single artifact but
not a single variable.

**I predicted the wrong ordering of what prompting buys.** After arm 2 I
concluded that instructions about output shape land well and instructions about
decisions don't. Arm 3 was neither and beat both. The revised ordering, on this
task:

```
semantic clarity  (what the field MEANS)    largest, and broadly positive
output shape      (how to format it)        moderate, narrow, with real costs
decisions         (when to abstain)         smallest
```

`contract_num` gained +0.063 without appearing in the prompt at all, which is the
best evidence for the semantic reading. Clarifying the document's cast of
organisations helped a field nobody mentioned.

---

## Four infrastructure problems worth knowing about

None of these are model behaviour. All four produce a run that finishes cleanly
and reports the wrong thing, which is the failure mode worth rehearsing.

Ollama loads models at `num_ctx 4096` regardless of what the model supports.
`qwen3:14b` supports 40960. At 4096, 69 of 641 documents get silently truncated,
10.8% of the corpus, with no error and no warning, just missing text and
inexplicable failures on the longest documents. Fixed in the `Modelfile`, which
is committed for exactly that reason.

Non-determinism is large, and qwen3 defaults to temperature 0.6. Two identical
runs disagreed on `contract_num` (`950658-1` then `0129`), on `advertiser` (null
then correct) and on `product`. Every run was a sample rather than an answer, so
an informal 8-of-12 could have been 6 or 10, and two prompts can't be compared on
one run each.

Thinking mode can't be disabled through Ollama's OpenAI-compatible `/v1`
endpoint. Neither `think=false` nor an in-prompt directive works, because it is
baked into the chat template. That is around 3000 hidden reasoning tokens per
document and roughly 10x wall clock on what is fundamentally a copying task. The
native `/api/chat` endpoint honours it and structured output still works there.

Unbounded strings under grammar constraint run away. A schema saying
`{"type": ["string", "null"]}` sets no length bound, so echoing the entire source
document into one field is perfectly valid output. The decisive one-variable test,
on document `05998648`:

```
maxLength 120   ->  6.8s, 169 tokens, correct values
unbounded       ->  TIMEOUT at 120s
```

Constrained decoding guarantees the output is valid, not that it is sensible, and
an unconstrained model would simply have stopped talking. This is a failure mode
strict schema modes introduce rather than prevent. Adding `maxLength` turned the
split from an estimated 18 hours into 16 minutes, and it isn't a workaround
either: an advertiser name is short and a flight date is eight characters. The
schema had been asserting that any of them could be a paragraph.

---

## How the failure taxonomy was built

Ten `tv_address` failures, sampled at seed 0 and not cherry-picked, hand-labelled
with no categories decided in advance. The categories that came out of those ten
were then applied to all 107.

| category | 10-case sample | all 107 |
|---|---|---|
| wrong company | 40% | 43.9% |
| incomplete | 30% | 25.2% |
| spurious (no address on the page) | 20% | 20.6% |
| not an address (returned a call sign) | 10% | 10.3% |
| missed entirely | 0% | 0.0% |

Ten cases predicted 107 to within a few points on every category. Labelling
everything was never necessary and labelling nothing would have left a 0.256 F1
undiagnosed. Repeating the exercise on `agency` produced a different category set
entirely, which is its own finding: the two worst fields fail for unrelated
reasons and I would have missed that by pooling them.

---

## Still open

Recorded rather than quietly dropped.

Wrong-value selection is unsolved and is now essentially the whole problem, 50 of
`tv_address`'s 63 remaining failures. Three prompt arms moved it by +3, -0 and
+3, so prompting does not touch it. It needs a different mechanism: span
retrieval, a two-stage approach that locates the station block first, or per-field
few-shot examples.

The valid split has never been run, so both the arm selection and the
risk-coverage curve are fitted on the data they were scored on. First thing I
would fix.

Whether constrained decoding caused the sampling collapse, as described above.

One unexplained timing anomaly. Arm 1 took 4.9 hours against a 23-minute
projection measured from its own first 20 documents. The rate degraded from about
13s to about 150s per document partway through and stayed there, on the same
machine and settings as a baseline run that did 141 documents in 1905s. Not
investigated.

Whether schema breadth hurts. Expanding one call from 6 fields to 9 made four
fields start returning null, including one that had been correct. Splitting into
two calls of 4 and 5 is an untested arm.

Line items: 5 fields, variable per-row field sets, a median of about 12 rows per
document. The row-matching key is a judgement call worth several points of score.

---

## Setup

Needs [Ollama](https://ollama.com), [uv](https://docs.astral.sh/uv/), about 10GB
of disk for the model and 236MB for the dataset.

```bash
ollama pull qwen3:14b
ollama create qwen3-14b-32k -f Modelfile   # 32k context; the default 4096 truncates 10.8% of the corpus
uv sync
cp .env.example .env                        # BASE_URL=http://localhost:11434/v1  MODEL=qwen3-14b-32k
```

The dataset isn't redistributed here. Fetch VRDU Ad-buy Forms into `data/vrdu/`
from [google-research/vrdu](https://github.com/google-research/google-research/tree/master/vrdu).
One thing that cost me a day: `evaluate.py` and its helpers live in the
**google-research** repo, not in the dataset repo. They are vendored unmodified
in `vendor/vrdu/`.

```bash
uv run python baseline.py                   # full split, caches every response under traces/
PYTHONPATH=vendor uv run python -m vrdu.evaluate -b data/vrdu -e predictions -o eval_results.tsv
```

| script | what it does |
|---|---|
| `first_call.py` | walking skeleton, one document, provider-agnostic |
| `baseline.py` | full-split runner with retry, timeout and loud failure counting |
| `ablate.py` | one arm per prompt version. Refuses to run without a written hypothesis. Caches per version |
| `score_arm.py` | re-score any arm from cache with no inference. Every number above comes from it |
| `ground.py` | is each predicted value actually in the source text, including reassembled fragments |
| `confidence.py` | risk-coverage curves from free features |
| `selfconsist.py` | N samples above temperature 0, agreement against correctness |
| `annotate.py`, `make_labels.py`, `show.py` | print real documents and failures for hand-labelling |

---

## Reading order

1. [`docs/adr/0001-what-correct-means.md`](docs/adr/0001-what-correct-means.md),
   what the evaluator actually accepts. Read the scoring code before designing
   anything.
2. [`docs/adr/0002-confidence-and-abstention.md`](docs/adr/0002-confidence-and-abstention.md),
   the one real design decision here and why it went the way it did.
3. [`ablation_results.md`](ablation_results.md), every arm with the hypothesis
   that preceded it.
4. [`FINDINGS.md`](FINDINGS.md), 60 numbered findings in the order they were
   found, including the ones later corrected. Corrections are marked rather than
   edited away.

## Provenance and scope

Dataset and labels are Google Research's VRDU Ad-buy Forms, a public corpus of
FCC political advertising filings. The evaluator is theirs, vendored unmodified.
The model is open-weight `qwen3:14b`. The prompts, harness, failure taxonomies,
grounding and confidence analysis are mine.

This is a personal study of a public benchmark, built to understand the problem
shape. It uses no proprietary data, documents or code, and is not a product.
