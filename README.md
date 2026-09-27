# Document field extraction study

Pulling nine structured fields out of scanned US TV political ad-buy invoices
with a 14B model running on a laptop, scored by the benchmark authors' own
evaluator.

I kept reading about document field extraction without really understanding it,
so I rebuilt one against a public benchmark and wrote down where it breaks.

## At a glance

| aspect | detail |
|---|---|
| Task | 9 fields per invoice: advertiser, agency, contract number, flight start and end, gross amount, product, station address, property |
| Data | 141 test documents from [VRDU Ad-buy Forms](https://github.com/google-research-datasets/vrdu), with Google Research's labels |
| Scorer | Google Research's evaluator, vendored unmodified in [`vendor/vrdu/`](vendor/vrdu/) |
| Model | `qwen3:14b` through Ollama. One call per document, temperature 0, JSON schema on the output, no fine-tuning, no few-shot examples |
| Result | Unrepeated-field F1 from 0.665 to 0.721 over three prompt revisions |
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
5. **Four infrastructure problems never said what was wrong.** For example, at
   Ollama's default context size 10.8% of the corpus would have been silently
   truncated. [Infrastructure problems](docs/infrastructure-problems.md)

## Results

```
unrepeated-field F1   0.6649  ->  0.7212      (+0.0563)
      precision       0.6223  ->  0.6772
      recall          0.7139  ->  0.7713
```

The left number is the first prompt I wrote. The right one is the best of three
single-factor revisions. All four are scored in
[`ablation_results.md`](ablation_results.md), and each revision's hypothesis was
written down before it ran, at the top of its log in `traces/`.

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
- `tv_address` is hard partly because the OCR tears addresses apart: 23 of its
  231 gold values are split across two or three places in the text. I first read
  these as missing and reported a 0.90 recall ceiling, which was wrong. Google's
  own character spans show every one of them is on the page.

The full version, with every setting the number depends on, is in
[docs/results.md](docs/results.md).

## Run it

Needs [Ollama](https://ollama.com), [uv](https://docs.astral.sh/uv/), about 10GB
of disk for the model and 236MB for the dataset. The clone in step 2 is over
500MB on its own, because it includes the PDFs and the other corpus, and can be
deleted once the files are copied.

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

**4. Or run the extraction yourself.** `baseline.py` reuses any response already
in `traces/`, and the committed cache holds all 141, so move it aside first or
nothing reaches the model. The full run took about 32 minutes on my laptop.

```bash
SPLIT=DeepForm-kno_template-train_200-test_141-valid_100-SD_0
mv traces/$SPLIT traces/$SPLIT.committed      # otherwise every document comes from cache
uv run python baseline.py $SPLIT --limit 10   # smoke test first
uv run python baseline.py $SPLIT
uv run python score_arm.py                    # unrepeated F1 for your run
PYTHONPATH=vendor uv run python -m vrdu.evaluate -b data/vrdu -e predictions -o eval_results.tsv   # 14-field micro and macro F1
```

| script | what it does |
|---|---|
| `first_call.py` | walking skeleton, a few documents, provider-agnostic |
| `baseline.py` | full-split runner with retry, timeout and loud failure counting |
| `ablate.py` | one arm per prompt version. Refuses to run without a written hypothesis. Caches per version |
| `score_arm.py` | re-score any arm from cache with no inference. The unrepeated F1, precision, recall and per-field scores above come from it |
| `ground.py` | is each predicted value actually in the source text, including reassembled fragments |
| `confidence.py` | risk-coverage curves from free features |
| `selfconsist.py` | N samples above temperature 0, agreement against correctness |
| `annotate.py`, `make_labels.py`, `show.py` | read real documents and failures by hand: `show.py` prints one document, `annotate.py` walks through failures, `make_labels.py` wrote the label sheets in `annotations/` |
| `check_format.py` | builds a predictions file from whatever is cached, to check the evaluator accepts the format before a long run |

Other things at the top level:

| path | what it is |
|---|---|
| `prompts/` | every prompt version. `v1.txt` (read by `baseline.py`) and `v1_baseline.txt` are the same first prompt under two names |
| `traces/` | every raw model response, one JSON per document and one folder per prompt arm, plus the self-consistency samples and the run logs |
| `predictions/` | the first prompt's run in the evaluator's input format, written by `baseline.py` |
| `predictions-ablate/` | the last arm `ablate.py` scored, which was `v4_whose` |
| `predictions-probe/` | `check_format.py`'s output from when one document was cached |
| `eval_results.tsv` | the evaluator's output for `predictions/`: 14-field micro and macro F1 |
| `annotations/` | my labels for 10 `tv_address` and 10 `agency` failures, behind the [failure taxonomy](docs/failure-taxonomy.md) |
| `Modelfile` | the 32k-context model definition used in step 1 |

## Read more

In suggested reading order.

| document | what is in it |
|---|---|
| [ADR 0001, what "correct" means](docs/adr/0001-what-correct-means.md) | what the evaluator actually accepts |
| [ADR 0002, confidence and abstention](docs/adr/0002-confidence-and-abstention.md) | the one real design decision here and why it went the way it did |
| [Results in full](docs/results.md) | every setting behind the number, per-field results, the four arms |
| [What I got wrong](docs/what-i-got-wrong.md) | five mistakes and what each one would have cost |
| [Confidence](docs/confidence.md) | three confidence mechanisms, measured |
| [Infrastructure problems](docs/infrastructure-problems.md) | four problems outside the model that never said what was wrong |
| [Failure taxonomy](docs/failure-taxonomy.md) | how ten hand-labelled failures predicted all 107 |
| [Still open](docs/open-questions.md) | what is unsolved or untested |
| [`FINDINGS.md`](FINDINGS.md) | 60 numbered findings in the order they were found. Corrections are marked rather than edited away |

## Provenance and licence

Dataset and labels are Google Research's VRDU Ad-buy Forms, a public corpus of
FCC political advertising filings. The evaluator is theirs, vendored unmodified
under Apache 2.0. The model is open-weight `qwen3:14b`. The prompts, harness,
failure taxonomies, grounding and confidence analysis are mine, under the
[MIT licence](LICENSE).

I built it with Claude Code as a pair programmer, and its co-author line appears
on some commits in the git log.

This is a personal study of a public benchmark, built to understand the problem
shape. It uses no proprietary data, documents or code, and is not a product.
