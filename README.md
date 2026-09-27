# Document field extraction study

Pulling nine structured fields out of scanned US TV political ad-buy invoices
with a 14B model running on a laptop, scored by the benchmark authors' own
evaluator.

I kept reading about document field extraction without really understanding it,
so I rebuilt one against a public benchmark and wrote down where it breaks.

## At a glance

| | |
|---|---|
| Task | 9 fields per invoice: advertiser, agency, contract number, flight start and end, gross amount, product, station address, property |
| Data | 141 test documents from [VRDU Ad-buy Forms](https://github.com/google-research-datasets/vrdu), with Google Research's labels |
| Scorer | Google Research's evaluator, vendored unmodified in [`vendor/vrdu/`](vendor/vrdu/) |
| Model | `qwen3:14b` through Ollama. One call per document, temperature 0, JSON schema on the output, no fine-tuning, no few-shot examples |
| Result | Unrepeated-field F1 from 0.665 to 0.721 over four prompt revisions |
| Cost | $0, everything runs locally |

## What I found

The score is the least interesting thing in the repo. These are the findings
that survived scrutiny.

1. **The model is confidently wrong, not uncertain.** At temperature 0.7 it
   agrees with itself on 92.5% of predictions, so sampling three times flags
   only 7.5% of answers at 3x the inference cost.
   [Confidence](docs/confidence.md)
2. **The errors are wrong-value selection, not hallucination.** Genuine
   fabrication came to 6 cases in 1239 predictions. I first read the low
   precision as hallucination and would have built the wrong fix.
   [What I got wrong](docs/what-i-got-wrong.md)
3. **A score change never says why.** All three prompt revisions improved F1
   through a mechanism other than the one I designed them for.
   [What I got wrong](docs/what-i-got-wrong.md)
4. **The two worst fields need opposite fixes.** `agency` fails mostly on
   documents that contain no agency, so it needs abstention. `tv_address` fails
   mostly by picking the wrong address off the page, so it needs
   disambiguation. [Results](docs/results.md)
5. **Four infrastructure problems each gave a clean run with wrong numbers.**
   For example, Ollama's default context size silently truncated 10.8% of the
   corpus. [Infrastructure problems](docs/infrastructure-problems.md)

## Results

```
unrepeated-field F1   0.6649  ->  0.7212      (+0.0563)
      precision       0.6223  ->  0.6772
      recall          0.7139  ->  0.7713
```

The left number is the first prompt I wrote. The right one is the best of four
single-factor revisions, all listed in [`ablation_results.md`](ablation_results.md)
with the hypothesis recorded before each run.

| field | first prompt | best | delta |
|---|---|---|---|
| gross_amount | 0.968 | 0.968 | 0 |
| advertiser | 0.868 | 0.897 | +0.029 |
| product | 0.741 | 0.748 | +0.007 |
| flight_to | 0.722 | 0.717 | -0.005 |
| flight_from | 0.698 | 0.682 | -0.016 |
| contract_num | 0.616 | 0.679 | +0.063 |
| property | 0.531 | 0.612 | +0.081 |
| agency | 0.512 | 0.581 | +0.069 |
| tv_address | 0.256 | 0.534 | +0.278 |

### What this number does not cover

- It is a single-template split. The published VRDU baseline is mixed template
  across all 14 fields, which is harder, so I am not claiming the comparison.
- It leaves out the five line-item fields. Across all 14 fields micro F1 is
  0.359 and macro is 0.591.
- The metric is more forgiving than "actually right". An address within three
  edits of gold counts as a match.
  [ADR 0001](docs/adr/0001-what-correct-means.md)
- All four prompts were scored on the same 141 test documents and the valid set
  has never been run, so 0.7212 is selected-on-test and optimistic.
- `tv_address` has a recall ceiling of 0.90, because 23 of its 231 gold values
  do not appear anywhere in the OCR text.

The full version, with every setting the number depends on, is in
[docs/results.md](docs/results.md).

## Run it

Needs [Ollama](https://ollama.com), [uv](https://docs.astral.sh/uv/), about 10GB
of disk for the model and 236MB for the dataset.

**1. Model and dependencies**

```bash
ollama pull qwen3:14b
ollama create qwen3-14b-32k -f Modelfile   # 32k context; the default 4096 truncates 10.8% of the corpus
uv sync
cp .env.example .env
```

**2. Dataset.** It isn't redistributed here. Fetch it from
[google-research-datasets/vrdu](https://github.com/google-research-datasets/vrdu):

```bash
git clone --depth 1 https://github.com/google-research-datasets/vrdu ../vrdu-dataset
mkdir -p data/vrdu/main
cp ../vrdu-dataset/ad-buy-form/main/meta.json data/vrdu/main/
cp -r ../vrdu-dataset/ad-buy-form/few_shot-splits data/vrdu/
cp ../vrdu-dataset/ad-buy-form/main/dataset.jsonl.gz data/adbuy.jsonl.gz   # the scripts read this
gunzip -c data/adbuy.jsonl.gz > data/vrdu/main/dataset.jsonl               # the evaluator reads this
```

**3. Re-score from cache.** Every raw model response is committed under
`traces/`, so this needs no model and takes about four seconds:

```bash
uv run python score_arm.py            # first prompt
uv run python score_arm.py v4_whose   # best prompt
```

**4. Or run the extraction yourself**

```bash
SPLIT=DeepForm-kno_template-train_200-test_141-valid_100-SD_0
uv run python baseline.py $SPLIT --limit 10   # smoke test first
uv run python baseline.py $SPLIT
PYTHONPATH=vendor uv run python -m vrdu.evaluate -b data/vrdu -e predictions -o eval_results.tsv
```

| script | what it does |
|---|---|
| `first_call.py` | walking skeleton, a few documents, provider-agnostic |
| `baseline.py` | full-split runner with retry, timeout and loud failure counting |
| `ablate.py` | one arm per prompt version. Refuses to run without a written hypothesis. Caches per version |
| `score_arm.py` | re-score any arm from cache with no inference. Every number above comes from it |
| `ground.py` | is each predicted value actually in the source text, including reassembled fragments |
| `confidence.py` | risk-coverage curves from free features |
| `selfconsist.py` | N samples above temperature 0, agreement against correctness |
| `annotate.py`, `make_labels.py`, `show.py` | print real documents and failures for hand-labelling |

## Read more

In suggested reading order.

| document | what is in it |
|---|---|
| [ADR 0001, what "correct" means](docs/adr/0001-what-correct-means.md) | what the evaluator actually accepts |
| [ADR 0002, confidence and abstention](docs/adr/0002-confidence-and-abstention.md) | the one real design decision here and why it went the way it did |
| [Results in full](docs/results.md) | every setting behind the number, per-field results, the four arms |
| [What I got wrong](docs/what-i-got-wrong.md) | five mistakes and what each one would have cost |
| [Confidence](docs/confidence.md) | three confidence mechanisms, measured |
| [Infrastructure problems](docs/infrastructure-problems.md) | four ways to get a clean run with wrong numbers |
| [Failure taxonomy](docs/failure-taxonomy.md) | how ten hand-labelled failures predicted all 107 |
| [Still open](docs/open-questions.md) | what is unsolved or untested |
| [`FINDINGS.md`](FINDINGS.md) | 60 numbered findings in the order they were found. Corrections are marked rather than edited away |

## Provenance and licence

Dataset and labels are Google Research's VRDU Ad-buy Forms, a public corpus of
FCC political advertising filings. The evaluator is theirs, vendored unmodified
under Apache 2.0. The model is open-weight `qwen3:14b`. The prompts, harness,
failure taxonomies, grounding and confidence analysis are mine, under the
[MIT licence](LICENSE).

This is a personal study of a public benchmark, built to understand the problem
shape. It uses no proprietary data, documents or code, and is not a product.
