## 2026-09-23, first run: qwen3:14b, 6 unrepeated fields, 3 docs

Informal count: 14/18 fields matched under Google's matchers.

1. contract_num, doc 1: predicted "950658-1", gold "950658". The document
   contains BOTH "Invoice # 950658-1" and "Order # 950658". Model took the
   invoice number. Under NumericalStringMatch these are 9506581 vs 950658,
   so no match. Neither candidate is labelled "contract" on the page.
   Hypothesis: contract_num means Order #. Needs checking across more docs
   before touching the prompt.

2. Field-role confusion, doc 2 (WXXA): model put "POL/FWD.US PAC" in
   `product` and left `advertiser` empty. Gold has it the other way round,
   with product = "issue". So "product" on political forms appears to mean
   ad category, not a product name. Another labelling convention the model
   cannot infer from the page.

3. Template variance dominates. Docs 1 and 3 scored 5/6 and 6/6; doc 2
   scored 3/6. Not a uniform ~78% model. Closer to ~95% on layouts it
   handles and ~50% on ones it doesn't. This is what VRDU's
   single/mixed/unseen-template splits exist to measure.

Not changing anything yet. n=3.
## 2026-09-23, infrastructure findings (not model behaviour)

Three problems found while debugging a hung run. None are about the model, but
all three would have silently corrupted results.

4. Ollama loads with num_ctx 4096 by default, regardless of what the model
   supports (qwen3:14b supports 40960). At 4096, 69 of 641 documents (10.8%)
   would be silently truncated. No error, no warning, just missing text and
   unexplained failures on the longest documents. Fixed with a Modelfile
   setting num_ctx 32768, committed to the repo. This is the exact shape of
   failure worth watching for: a green run that is quietly wrong.

5. A stale ollama process from an earlier malformed command held port 11434
   while brew services repeatedly failed to bind. Symptom was requests hanging
   indefinitely rather than erroring. Machine was also thrashing: free RAM was
   about 65 MB with swap nearly exhausted. Killing the orphan recovered ~12.9 GB.

6. qwen3 has thinking mode on by default. A probe with max_tokens 5 returned an
   empty string because all five tokens went to hidden reasoning. For extraction
   this is pure overhead. Set think=False. Worth an ablation arm later: does
   reasoning help on a copying task? Prediction: no, and that is worth measuring.

7. NON-DETERMINISM IS LARGE, and this is the most important finding so far.
   Two runs, same documents, same prompt, nothing changed but sampling:
     doc 1 contract_num: '950658-1' then '0129'   (gold '950658')
     doc 2 advertiser:   None       then correct
     doc 2 product:      'POL/FWD.US PAC' then 'FOX'  (gold 'issue')
   qwen3 defaults to temperature 0.6, so every run is a sample rather than
   an answer. Consequences: an informal 8/12 could be 6/12 or 10/12 on a
   re-run; two prompts cannot be compared on one run each; every number
   needs an n and ideally an interval. Set temperature 0, which reduces but
   does not eliminate this (GPU float arithmetic is not associative).

8. contract_num is genuinely ambiguous on the page. Document 1 carries
   "Invoice # 950658-1", "Order # 950658" and "Estimate Number 0129". The
   model has picked the invoice number and the estimate number across two
   runs. Gold wants the order number. This is a prompt problem, not a
   sampling problem.

9. flight_from returned a range: '03/27/20 - 03/31/20' where gold wants
   '03/27/20'. DateMatch cannot parse a range, so it scores as a miss. The
   document shows a flight window and the model returned the whole thing.

10. Thinking mode cannot be disabled via the OpenAI-compatible endpoint.
    Neither think=false nor an in-prompt /no_think directive works; it is
    baked into the chat template. Roughly 3k output tokens per document, so
    about 10x wall-clock. Free locally, but it makes full sweeps slow.
    Open item.

## 2026-09-23, schema expanded from 6 to 9 unrepeated fields

11. TEMPERATURE 0 GIVES STABLE ANSWERS. Two consecutive runs produced
    byte-identical field predictions. Output token counts differed (3607 vs
    4456), so the hidden reasoning varied while the final structured answer
    converged. Consequence: at temperature 0 a difference between runs now
    carries information. At 0.6 it did not.

12. SCHEMA BREADTH DEGRADES PER-FIELD ACCURACY, measured on my own data.
    Expanding the same call from 6 fields to 9 caused four fields on
    document 1 to return None, including flight_from which was previously
    extracted correctly ('12/30/19'). Nothing else changed. This matches
    published results where accuracy collapses as schema size grows.
    Experiment this motivates: does splitting into two calls of 4 and 5
    fields beat one call of 9? Week 7 ablation arm.

13. Correct absence detection works. agency returned None against gold None
    on both documents. The prompt instruction to return null rather than
    infer is being followed at least some of the time.

14. tv_address on document 2 returned 'WXXA', the station call sign, where
    gold is a PO Box in Atlanta. Same shape as the product confusion in
    finding 2: the model finds a plausible nearby value and assigns it to
    the wrong field. Now two instances, so worth counting as a category
    rather than treating as a one-off.

## 2026-09-23, step 3 harness: infrastructure debugging

15. THINKING MODE WAS THE FIRST BOTTLENECK. Ollama's OpenAI-compatible /v1
    endpoint silently ignores think=false, so qwen3 generated roughly 3000
    tokens of hidden reasoning per document. Measured from ollama's own log:
    prompt eval 301 to 600 tok/s (fine), generation 21 tok/s (the bottleneck).
    About 2.4 minutes per document, 5.6 hours for a 141-document split. The
    native /api/chat endpoint does honour think=false, and structured output
    still works there via `format` with a JSON schema. Switched to it.

16. UNBOUNDED STRINGS UNDER GRAMMAR CONSTRAINT CAN RUN AWAY. With thinking
    disabled, generation still climbed past 1787 tokens and kept going for a
    1281-token document. A schema saying {"type":["string","null"]} places no
    length bound, so echoing the entire source document into one field is
    perfectly valid output. Constrained decoding guarantees the output is
    VALID, not that it is SENSIBLE, and an unconstrained model would simply
    have stopped talking. This is a failure mode that strict schema modes
    introduce rather than prevent.

17. GENERATION TIME IS HIGHLY VARIABLE AND I CANNOT FULLY EXPLAIN IT. The same
    document, same schema, same prompt ranged from 14s to over 300s across
    runs. Schema form (anyOf vs type-array) did not explain it. Documented as
    open rather than claimed as solved. Mitigation: 240s timeout, one retry,
    then record the document as failed and continue. Failures are counted and
    printed loudly, because a silently skipped document makes the score a lie.

18. PROCESS FAILURE, MINE. I changed more than one variable between diagnostic
    runs repeatedly: the schema-form test also swapped the system prompt, the
    isolation test dropped it entirely. Each run answered a question I had not
    meant to ask, and four rounds did the work of two. This is exactly the
    discipline week 7's ablation requires (one factor, hypothesis written
    first) and I demonstrated why by not following it.

19. THE RUNAWAY HAS A CONFIRMED CAUSE AND A ONE-LINE FIX. Finding 16 was
    right about the mechanism and I failed to validate it for several rounds.
    Decisive test, one variable, document 05998648 (3957 chars):
      maxLength=120  ->  6.8s, 169 tokens, correct values
      unbounded      ->  TIMEOUT after 120s
    It is document-specific: on 030f7df7 the unbounded schema completed in
    14s. So some documents offer the model a tempting thing to echo and
    others do not, which is why this looked intermittent and unexplainable
    for so long.
    Adding maxLength turns the split from an estimated 18 hours into roughly
    16 minutes. It is also not a workaround: it encodes a true fact about the
    domain. An advertiser name is short, a flight date is eight characters.
    The schema was previously asserting that any of these could be a
    paragraph, which was never true.

## 2026-09-24, FIRST EXTERNALLY SCORED BASELINE

Conditions: qwen3-14b-32k local, prompt v1, temperature 0, think=false,
maxLength 120, 9 unrepeated fields only, split
DeepForm-kno_template-train_200-test_141-valid_100-SD_0 (141 test documents),
0 failures, 32 minutes wall clock. Scored by Google's evaluate.py against
Google's annotations.

  unrepeated F1  0.665   (P 0.622  R 0.714)   <- the honest headline
  macro F1       0.591
  micro F1       0.359   (R 0.252)

20. REPORT THE UNREPEATED AGGREGATE, NOT MICRO OR MACRO. evaluate.py scores
    all 14 fields; I extract 9. The 5 line-item fields score 0. Micro is
    instance-weighted and line-item instances dominate the corpus, so micro
    collapses to 0.359. Macro averages 9 real scores with 5 zeros and lands
    at 0.591. Neither describes what was built. unrepeated_f1 = 0.665 does.
    This is finding 12's micro/macro divergence showing up for real, and it
    is why a number without its denominator is meaningless.

21. NOT COMPARABLE TO THE PUBLISHED 30.05 BASELINE, and I should not claim
    otherwise. Those figures are MIXED template with all 14 fields. This is
    SINGLE template with 9. Different regime, different field set. The
    comparison to make later is against my own ablation arms, or against a
    published number only after matching the split and field set exactly.

22. FAILURE IS CONCENTRATED IN THREE FIELDS, not spread evenly.
      gross_amount 0.968 and advertiser 0.868 are near solved.
      tv_address 0.256 is the worst by a wide margin.
      agency 0.512 splits oddly: recall 0.768, precision 0.384.
    agency and tv_address need DIFFERENT fixes. agency finds the right value
    when one exists but invents one when it does not, so it is a
    hallucination/abstention problem. tv_address is weak at both ends and
    looks like genuine field confusion, consistent with finding 14 where it
    returned the station call sign instead of a mailing address.
    Weeks 4 to 6 should open-code these two first. Fixing tv_address alone
    is worth roughly 5 points of unrepeated F1.
