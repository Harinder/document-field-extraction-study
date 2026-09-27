# ADR 0002. How this system decides what not to answer

**Status:** accepted, with a known gap (see Consequences)

**Supersedes nothing. Depends on** [ADR 0001](0001-what-correct-means.md).

## Context

The extractor is 67.7% correct per prediction on its best prompt. Any real
deployment of a 68%-correct extractor needs to answer one question: **which
predictions do we trust, and which go to a human?**

That question is not the same as "make the model better". A system that is 68%
correct across the board is unusable. A system that is 68% correct overall but
can identify its bad 20% is a usable system with a review queue attached to it.

So the design decision is not about the prompt. It is: **what is the abstention
mechanism, and what does it cost?**

Four candidate signals were available on this stack. Each was measured rather
than assumed.

## Options considered

### 1. Prompted abstention. Tell the model to return null when unsure.

Measured as ablation arm `v2_abstain`. On the 72 test documents with no `agency`
at all:

```
baseline   returned null   3/72  ( 4.2%)
v2_abstain returned null  18/72  (25.0%)
```

Six times more abstention, and still only a quarter of the cases. Projected gain
from perfect abstention was +0.256 on `agency`; actual was +0.040, about 16% of
it.

**But:** on the 187 cases where the field IS present, both arms abstained **zero**
times. When this model says null, it is right 100% of the time. The problem is
not that it cannot judge absence. It is **biased toward answering**.

Verdict: real, free, and caps out low. Keep it. Do not rely on it.

### 2. Grounding. Reject any value not present in the source text.

```
grounded, exact match       1160 preds   69.8% correct
whitespace difference         37 preds   40.5%
reassembled from fragments    28 preds   28.6%
absent from document           5 preds    0.0%
```

Monotonic and clean. Also nearly useless as a ranking signal, because 94% of
predictions are exact matches. As a hard reject rule on the 5 absent cases it is
free and costs zero correct answers.

**Critical implementation note.** A naive contiguous-substring check is wrong on
this corpus. The OCR tears multi-line values apart and interleaves unrelated form
labels between the street line and the city line, so a correctly reassembled
address looks like a fabrication. My first version of this check reported 55
ungrounded predictions. After handling non-contiguous matches: 49 reassembly, 6
genuine. **An unfixed version of this check would have rejected competent
behaviour 89% of the time it fired.**

Verdict: adopt as a hard filter. It is a rule, not a tuned threshold, which is
what makes it cheap to trust.

### 3. Per-field prior. Route by which field it is.

```
gross_amount 97.1%   advertiser 89.4%   product 72.1%
contract_num 68.4%   flight_to  65.9%   flight_from 63.0%
property     56.1%   tv_address 51.2%   agency     44.0%
```

A 53-point spread, and by far the strongest number available. It is also **not
confidence.** It cannot tell you which `agency` prediction is good, only that
`agency` is bad on average. A risk-coverage curve built on it is field-dropping
with extra steps: at 70% coverage, simply deleting the three worst fields
outright **beats** the curve (76.1% against 75.6%).

Verdict: use it for capacity planning and for setting per-field review policy.
Do not report it as per-prediction confidence.

### 4. Self-consistency. Sample 3 times at temperature 0.7, measure agreement.

```
3 of 3 agree   333 preds   75.1% correct   Wilson 95% CI [70.2, 79.4]
disagreement    27 preds   33.3% correct   Wilson 95% CI [18.6, 52.2]
```

A 42-point gap with non-overlapping intervals, so it holds at n=27. **0.43
accuracy points gained per percent of coverage sacrificed, against 0.25 for the
field prior.** It is also the only signal measured here that varies *within* a
field, which is the property the other three lack.

And it flags 27 of 360 predictions. **92.5% are unanimous.** You pay 3x inference
to identify 7.5% of your answers as suspect.

Verdict: the only real confidence signal on this stack, and its reach is too
narrow to carry a review policy by itself.

### Not available

Token logprobs are not exposed on Ollama's native `/api/chat` path, which is the
path required to disable thinking mode (finding 15, and [infrastructure problems](../infrastructure-problems.md)). So the
cheapest and best-calibrated signal in the literature is off the table as a
direct consequence of an unrelated infrastructure decision. Worth stating
plainly: **the endpoint choice foreclosed the confidence approach.**

## Decision

Route in this order, cheapest first:

1. **Hard reject** any prediction not groundable in the source text, including
   non-contiguous reassembly. Free, applied to every prediction.
2. **Per-field policy.** `gross_amount` and `advertiser` auto-accept. `agency`,
   `tv_address` and `property` go to review by default. This is a prior about
   fields, declared as such.
3. **Self-consistency only where the 3x cost is justified**, which on this corpus
   means the mid-tier fields where a prior is not decisive. Not globally.
4. **Prompted abstention stays in the prompt** because it is free and strictly
   positive, while explicitly not being counted on for more than a quarter of
   absent cases.

## Rationale, and the finding that drove it

Three measurements independently say the same thing:

- Temperature 0 gives **byte-identical** predictions across runs (finding 11).
- The model **never abstains wrongly**, 0 of 187 present cases (finding 37).
- At temperature 0.7 it **will not disagree with itself**, 92.5% unanimous
  (finding 54).

**This model is stable in its errors, not uncertain about them. It is confidently
wrong.**

That is why every uncertainty-shaped mechanism underperformed. You cannot measure
uncertainty that is not there. The errors are systematic: the wrong value selected
consistently, for a consistent reason, on consistent document layouts. 50 of
`tv_address`'s 63 remaining failures are one category, wrong-company selection,
and the prompt arm written to fix it moved that count from 47 to 50 (finding 44).

**Systematic errors need a corrective instrument, not an estimator.** The
mechanism that would fix them is span localisation, telling the model *where* to
read rather than hoping it picks right and then asking it how sure it is.

There is also a suspected self-inflicted cause. Constrained decoding with a JSON
grammar, a 120-character bound and one obvious on-page candidate leaves very few
valid next tokens at each step. Temperature can only redistribute probability
across choices that exist, and the grammar removed them. **Structured output
bought guaranteed-parseable answers and plausibly cost the ability to measure
uncertainty by sampling.** This is a real tradeoff and it is not in any of the
"always use strict schema mode" advice I read.

## Consequences

**Accepted.** Grounding and per-field routing are effectively free and are
adopted. Prompted abstention stays.

**Accepted cost.** There is no cheap per-prediction confidence on this stack. Any
deployment must size its human review queue from per-field base rates, not from a
calibrated score.

**Known gap, disclosed.** The risk-coverage curve was fitted on the same 141 test
documents it was evaluated on. The split's 100-document valid set has never been
run. **The curve must not be reported as a result** until it is refitted there.
This ADR records the decision and the mechanism; the per-field lists in point 2
are illustrative, not validated.

**Follow-up experiments, in priority order.**

1. Refit on the unused valid set. Converts the illustrative curve into a real one.
2. Sample without the JSON schema and compare answer diversity. Tests whether
   constrained decoding caused the collapse. If it did, the cost of structured
   output is much higher than advertised and the tradeoff should be made
   deliberately, for example schema-free sampling for the confidence pass and
   constrained decoding for the final answer.
3. Verbalized confidence, one extra schema field. Cheap, expected to be poorly
   calibrated, worth one run to confirm on this data rather than citing
   someone else's.
4. Span localisation for `tv_address`. The only approach that addresses the
   dominant failure mode rather than measuring it.
