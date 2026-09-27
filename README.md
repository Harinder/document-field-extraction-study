# adbuy-extract

Extracting 9 structured fields from scanned US TV political ad-buy invoices with
a 14B model running locally, scored by the benchmark authors' own evaluator.

Built over four days (2026-09-23 to 2026-09-26) as a deliberate study of one
problem shape: **document field extraction**. The goal was not a high score. The
goal was to understand where this class of system actually breaks, and to be able
to show the evidence.

---

## The number

```
unrepeated-field F1   0.6649  ->  0.7212      (+0.0563)
      precision       0.6223  ->  0.6772
      recall          0.7139  ->  0.7713
```

Everything that number depends on, stated once:

| | |
|---|---|
| **Dataset** | VRDU Ad-buy Forms (Google Research), FCC political advertising public files |
| **Split** | `DeepForm-kno_template-train_200-test_141-valid_100-SD_0`, seed 0 |
| **Denominator** | **141 test documents, 9 unrepeated fields** (141 x 9 = 1269 slots). Not the 5 line-item fields |
| **Labels** | Google's own annotations. Not mine |
| **Scorer** | Google's `vrdu/evaluate.py`, vendored unmodified in `vendor/vrdu/` |
| **Model** | `qwen3:14b` (14.8B params, Q4_K_M) via Ollama, `num_ctx 32768`, temperature 0, `think=false`, per-field `maxLength 120` |
| **Prompt** | `prompts/v4_whose.txt`. Zero-shot, single call, constrained JSON output |
| **Failures** | 0 documents failed or were skipped in any scored run |
| **Cost** | $0. Entirely local inference on one laptop |

The left number is the first prompt I wrote. The right number is the best of four
single-factor prompt arms. Every arm is in `ablation_results.md` with its
hypothesis recorded **before** the run, including the two that made things worse.

### What this number does not cover

- **It is a single-template split.** The public VRDU baseline of 30.05 is *mixed*
  template with all 14 fields. These are different regimes and I do not claim
  the comparison.
- **It excludes the 5 line-item fields entirely.** Those need table-row
  alignment, which is a separate problem I did not solve. Report the unrepeated
  aggregate and the reason why, or the number is a lie by omission: micro F1 on
  all 14 fields is 0.359 and macro is 0.591, because line items dominate the
  instance count and score zero.
- **The metric is more forgiving than "actually right."** `AddressMatch` accepts
  anything within 3 edits. `PriceMatch` tolerates 0.01. `NumericalStringMatch`
  strips every non-digit from `contract_num`, so a different identifier with
  coincidentally equal digits scores as correct. See
  [ADR 0001](docs/adr/0001-what-correct-means.md).
- **All four arms were scored on the same 141 test documents.** So 0.7212 is
  selected-on-test and optimistic. The split's 100-document valid set has never
  been touched and is where a clean confirmation would come from. I ran out of
  scope before doing it, and I would rather say that than quietly present a
  tuned number as a held-out one.
- **`tv_address` has a hard ceiling of 0.90 recall.** 23 of its 231 gold values
  do not appear anywhere in the OCR text. About 10% of that field is impossible
  for any system reading this input.

---

## The finding worth the whole project

I spent step 7 trying to build per-prediction confidence, so that low-confidence
extractions could be routed to a human instead of shipped. Three mechanisms,
two failed, and the reason they failed is the interesting part.

```
signal                     separation              reach
grounding in source text   69.8% vs 0.0% correct   5 of 1230 predictions
field identity             97.1% vs 44.0%          a prior, not confidence
self-consistency (3x)      75.1% vs 33.3%          27 of 360 predictions
```

Self-consistency works. Unanimous answers are 75.1% correct, split answers 33.3%,
and the Wilson 95% intervals do not overlap ([70.2, 79.4] against [18.6, 52.2]),
so the 42-point gap is real even at n=27. It is also nearly twice as efficient as
the trivial baseline of dropping the worst fields outright: **0.43 accuracy points
per percent of coverage sacrificed, against 0.25.**

And it reaches almost nothing. **92.5% of predictions are unanimous at
temperature 0.7.** You pay 3x inference to flag 7.5% of your answers.

Three independent findings explain why:

- At temperature 0, two runs gave **byte-identical** field predictions (finding 11).
- When the model returns null it is **right 100% of the time**, 0 false
  abstentions across 187 present-field cases in two arms (finding 37).
- At temperature 0.7 it **will not disagree with itself** (finding 54).

**The model is stable in its errors, not uncertain about them.** It is
confidently wrong. That single property explains why a prompt asking it to
abstain reached only 25% of the cases it should have, why grounding separates
nothing, and why no sampling method will surface most of the errors. Systematic
errors need a different instrument than uncertainty estimates.

The likely cause is a tradeoff nobody mentions when recommending strict schema
modes: **constrained decoding collapses the sampling distribution.** With a JSON
grammar, a 120-character bound and one obvious candidate on the page, the set of
valid next tokens is small, and temperature can only spread probability across
choices that still exist. Structured output bought guaranteed-parseable answers
and cost the ability to measure uncertainty by sampling. Untested here. Testing
it means sampling without the schema and comparing diversity, which is the first
experiment I would run next.

---

## Per-field results

Failure is concentrated, not spread. Two fields carry most of it.

| field | baseline | best arm | delta | note |
|---|---|---|---|---|
| gross_amount | 0.968 | 0.968 | 0 | effectively solved |
| advertiser | 0.868 | 0.897 | +0.029 | |
| product | 0.741 | 0.748 | +0.007 | |
| flight_to | 0.722 | 0.717 | -0.005 | |
| flight_from | 0.698 | 0.682 | -0.016 | |
| contract_num | 0.616 | 0.679 | +0.063 | gained without being named in the prompt |
| property | 0.531 | 0.612 | +0.081 | |
| **tv_address** | **0.256** | **0.534** | **+0.278** | worst field, largest gain, ceiling 0.620 |
| **agency** | **0.512** | **0.581** | **+0.069** | P 0.440 / R 0.855: answers when it should not |

Regenerate this table from cache with `uv run python score_arm.py [arm]`. No
inference required.

`agency` and `tv_address` look similar in aggregate and need **opposite** fixes.
81% of `agency` failures are documents with no agency at all, so its lever is
abstention. 54% of `tv_address` failures are the wrong value picked off a page
carrying four addresses, so its lever is disambiguation. Projected effect of
perfect abstention: `agency` +0.256, `tv_address` +0.024. **The same fix is worth
ten times more on one field than the other,** and the overall score gives you no
way to see that.

### The ablation

| arm | unrep F1 | delta | what changed | what actually happened |
|---|---|---|---|---|
| `v1_baseline` | 0.6649 | | first prompt | |
| `v2_abstain` | 0.6784 | +0.0135 | explicit null rule | predicted +0.02 to +0.03. Abstention rose 6x but reached only 25% of absent cases |
| `v3_complete` | 0.6810 | +0.0161 | ask for complete multi-line values | hit its target (`tv_address` +0.142) and made **6 of 9 other fields slightly worse** |
| **`v4_whose`** | **0.7212** | **+0.0563** | name which organisation each field refers to | best arm, and **it failed at its stated purpose** |

---

## Five things I got wrong

This section is the actual content of the project.

**1. I read a precision of 0.384 as hallucination.** It was not. A grounding
check proved that all 138 `agency` predictions were real text copied off the
page. The model was not inventing values, it was **selecting the wrong ones**.
Fabrication turned out to be 6 cases in 1239 predictions, 0.5%. Those two
diagnoses call for completely different fixes: abstention and thresholds for
one, disambiguation and retrieval for the other. I would have built the wrong
thing.

**2. My grounding check was itself wrong, and only reading one document found
it.** On document `300535fe` the model predicted `16 Cypress Ave Wheeling, WV
26003` and my check said "not in document", meaning invented. The OCR reads:

```
... Billing Calendar: / Broadcast / 16 Cypress Ave / EOM/EOC /
    Billing Cycle: / Agency Commission: / Wheeling, WV 26003 / 15% ...
```

Both halves are present, torn apart, with unrelated form labels interleaved. The
model had correctly **reassembled a real address from scattered fragments** and my
contiguous-substring check scored competent behaviour as fabrication. Corrected:
of 55 flagged, 49 were reassembly and 6 were genuine. No aggregate metric could
have surfaced this. The F1 said "tv_address is bad" and the grounding check said
"27 inventions". Both were true-ish and both pointed the wrong way.

**3. All three prompt arms improved the score via a mechanism other than the one
I designed them for.** Every time. Arm 1 aimed at abstention and accidentally
improved completeness. Arm 2 aimed at completeness, hit it, and converted its
fixed cases into a new failure category. Arm 3 aimed at disambiguation, **did not
achieve it at all**, and delivered the largest formatting fix of the three. An F1
delta tells you *if* something changed, never *why*. All three would have been
written up as confirmed hypotheses if I had stopped at the score. A
per-failure-mode breakdown is the only thing that caught it.

**4. "One factor at a time" is harder than it sounds with prompts.** I changed one
file and believed that was one variable. Rewording the null rule also changed
copying behaviour, so two effects moved at once and partly cancelled: 6 cases
gained, 3 lost on the same field. A prompt is a single artifact but not a single
variable.

**5. I predicted the wrong ordering of what prompting buys.** I concluded from arm
2 that instructions about output *shape* land well and instructions about
*decisions* do not. Arm 3 was neither, and beat both. Revised, on this task:

```
semantic clarity  (what the field MEANS)    largest, and broadly positive
output shape      (how to format it)        moderate, narrow, with real costs
decisions         (when to abstain)         smallest
```

`contract_num` gained +0.063 without appearing in the prompt at all, which
supports the semantic reading: clarifying the document's cast of organisations
helped a field that was never mentioned.

---

## Four infrastructure failures that would have silently corrupted results

Not model behaviour. All four produce a green run that is quietly wrong, which is
the failure mode worth rehearsing.

**Ollama loads at `num_ctx 4096` regardless of what the model supports.**
`qwen3:14b` supports 40960. At 4096, **69 of 641 documents (10.8%) are silently
truncated.** No error, no warning, just missing text and inexplicable failures on
the longest documents. Fixed in the `Modelfile`, committed.

**Non-determinism is large and qwen3 defaults to temperature 0.6.** Two identical
runs disagreed on `contract_num` (`950658-1` then `0129`), `advertiser` (null then
correct) and `product`. Every run was a sample, not an answer. An informal 8/12
could have been 6/12 or 10/12. Two prompts cannot be compared on one run each.

**Thinking mode cannot be disabled through Ollama's OpenAI-compatible `/v1`
endpoint.** Neither `think=false` nor an in-prompt directive works; it is baked
into the chat template. That is roughly 3000 hidden reasoning tokens per
document, about 10x wall clock, on a pure copying task. The native `/api/chat`
endpoint honours it, and structured output still works there.

**Unbounded strings under grammar constraint run away.** A schema saying
`{"type": ["string", "null"]}` places no length bound, so echoing the entire
source document into one field is perfectly valid output. Decisive one-variable
test on document `05998648`:

```
maxLength 120   ->  6.8s, 169 tokens, correct values
unbounded       ->  TIMEOUT at 120s
```

**Constrained decoding guarantees the output is VALID, not that it is SENSIBLE**,
and an unconstrained model would simply have stopped talking. This is a failure
mode strict schema modes *introduce* rather than prevent. Adding `maxLength`
turned the split from an estimated 18 hours into 16 minutes. It is also not a
workaround: an advertiser name is short and a flight date is eight characters.
The schema had been asserting that any of them could be a paragraph.

---

## Method: how the failure taxonomy was built

Ten `tv_address` failures, randomly sampled at seed 0 and not cherry-picked, were
hand-labelled with no categories supplied in advance. The categories that emerged
were then applied to all 107.

| category | 10-case sample | all 107 |
|---|---|---|
| wrong company | 40% | 43.9% |
| incomplete | 30% | 25.2% |
| spurious (no address on page) | 20% | 20.6% |
| not an address (returned a call sign) | 10% | 10.3% |
| missed entirely | 0% | 0.0% |

**Ten hand-labelled cases predicted 107 to within a few points on every
category.** Labelling everything was never necessary. Labelling nothing would
have left a 0.256 F1 undiagnosed. Repeating the exercise on `agency` produced a
*different* category set, which is itself the finding: the two worst fields fail
for unrelated reasons.

---

## What is still open

Recorded rather than quietly dropped.

- **Wrong-value selection is unsolved and is now the whole problem.** 50 of
  `tv_address`'s 63 remaining failures. Three prompt arms moved it +3, -0 and +3.
  Prompting does not touch it. It needs a different mechanism: span retrieval, a
  two-stage approach that locates the station block first, or per-field few-shot
  examples.
- **The valid split (100 documents) has never been run.** Both the risk-coverage
  curve and the arm selection are therefore fitted on the data they are scored
  on. This is the first thing I would fix.
- **Whether constrained decoding causes the sampling collapse** (see above).
- **Timing anomaly, unexplained.** Arm 1 took 4.9 hours against a 23-minute
  projection measured from its own first 20 documents. Rate degraded from ~13s to
  ~150s per document partway through and stayed there. Same machine, same model,
  same settings as a baseline run that did 141 documents in 1905s. Not
  investigated.
- **Does schema breadth hurt?** Expanding one call from 6 fields to 9 caused four
  fields to start returning null, including one that had been correct. Splitting
  into two calls of 4 and 5 is an untested arm.
- **Line items.** 5 fields, variable per-row field sets, median ~12 rows. The
  row-matching key is a judgement call worth several points.

---

## Reproduce it

Requires [Ollama](https://ollama.com), [uv](https://docs.astral.sh/uv/), and about
10GB of disk for the model plus 236MB for the dataset.

```bash
ollama pull qwen3:14b
ollama create qwen3-14b-32k -f Modelfile   # 32k context. The default 4096 truncates 10.8% of the corpus
uv sync
cp .env.example .env                        # BASE_URL=http://localhost:11434/v1  MODEL=qwen3-14b-32k
```

The dataset is not redistributed here. Fetch VRDU Ad-buy Forms into `data/vrdu/`
from [google-research/vrdu](https://github.com/google-research/google-research/tree/master/vrdu).
Note that `evaluate.py` and its helpers live in the **google-research** repo, not
in the dataset repo; they are vendored unmodified in `vendor/vrdu/`.

```bash
uv run python baseline.py                   # full split, caches every response under traces/
PYTHONPATH=vendor uv run python -m vrdu.evaluate -b data/vrdu -e predictions -o eval_results.tsv
```

| script | what it does |
|---|---|
| `first_call.py` | walking skeleton, one document, provider-agnostic |
| `baseline.py` | full-split runner with retry, timeout and loud failure counting |
| `ablate.py` | one arm per prompt version. **Refuses to run without a written hypothesis.** Caches per version |
| `ground.py` | is each predicted value actually present in the source text, including reassembled fragments |
| `confidence.py` | risk-coverage curves from free features |
| `selfconsist.py` | N samples at temperature > 0, agreement against correctness |
| `score_arm.py` | re-score any arm from cache, no inference. Every number in this README comes from it |
| `annotate.py`, `make_labels.py`, `show.py` | print real documents and failures for hand-labelling |

Runs are cached per prompt version under `traces/`, so every number here is
re-scorable without re-running inference.

---

## Reading order

1. [`docs/adr/0001-what-correct-means.md`](docs/adr/0001-what-correct-means.md),
   what the evaluator accepts. Read the scoring code before designing anything.
2. [`docs/adr/0002-confidence-and-abstention.md`](docs/adr/0002-confidence-and-abstention.md),
   the one real design decision, and why it went the way it did.
3. [`ablation_results.md`](ablation_results.md), every arm with its prior hypothesis.
4. [`FINDINGS.md`](FINDINGS.md), 60 numbered findings in the order they were
   found, including the ones later corrected. Corrections are marked, not edited
   away.

---

## Provenance and scope

Dataset and labels are Google Research's VRDU Ad-buy Forms, a public corpus of
FCC political advertising filings. The evaluator is theirs, vendored unmodified.
The model is open-weight `qwen3:14b`. Prompts, harness, failure taxonomies,
grounding and confidence analysis are mine.

This is a personal study of a well-known public benchmark, built to understand
the problem shape. It uses no proprietary data, documents, or code, and is not a
product.
