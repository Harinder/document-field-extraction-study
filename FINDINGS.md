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

## 2026-09-24, step 4: grounding

Run on cached predictions, no new inference. A value the model emits should
appear in the source OCR text; if not, it was invented.

23. GROUNDING IS A PERFECT NEGATIVE FILTER ON THIS CORPUS.
      grounded    1212 predictions, 63.6% correct
      ungrounded    27 predictions,  0.0% correct
    All 27 ungrounded predictions were wrong. Discarding them removes 27
    false positives and zero correct answers: precision 0.622 -> 0.636,
    recall unchanged, unrepeated F1 0.665 -> ~0.673. Small but free, and
    it is a rule rather than a tuned threshold.

24. RECALL CEILING IS 99.0%. 2217 of 2240 gold values are literally present
    in the OCR text, so almost nothing is structurally unreachable. The
    exception is tv_address at 90.0%: 23 of its 231 gold values do not
    appear in the text at all. About 10% of that field is impossible for
    any system reading this OCR, and its 0.256 F1 must be reported against
    a 0.90 ceiling, not 1.00.

25. CORRECTION TO FINDING 22: THE MODEL IS NOT HALLUCINATING. I read
    agency's precision of 0.384 as fabrication. Grounding disproves it:
    all 138 agency predictions and 134 of 140 tv_address predictions are
    real text copied from the document. The model is not inventing values,
    it is SELECTING THE WRONG ONES.
    This changes the fix. Fabrication would need abstention and confidence
    thresholds. Wrong-value selection needs disambiguation: telling the
    model which of several plausible on-page strings is the one being asked
    for. It is the same root cause as contract_num choosing between
    Invoice #, Order # and Estimate Number (finding 8), and as tv_address
    returning the station call sign (finding 14).
    Wrong-value selection is now the dominant failure mode of the whole
    system, and weeks 4 to 6 should open-code for it specifically rather
    than looking for hallucination.

## 2026-09-24, step 5 open coding: a measurement bug found by reading

26. MY GROUNDING CHECK HAD A FALSE-POSITIVE PROBLEM AND FINDING 23 WAS PARTLY
    WRONG. Found by reading document 300535fe by hand rather than by any
    metric. The model predicted tv_address '16 Cypress Ave Wheeling, WV 26003'
    and my check said NOT FOUND IN DOCUMENT, i.e. invented. Reading the OCR
    showed both halves are present but torn apart:
        ... Billing Calendar: / Broadcast / 16 Cypress Ave / EOM/EOC /
        Billing Cycle: / Agency Commission: / Wheeling, WV 26003 / 15% ...
    The model correctly reassembled a real address from fragments separated
    by unrelated labels. My check looked for a contiguous substring, so it
    scored competent behaviour as fabrication.
    Corrected counts across all 1239 predictions:
        flagged ungrounded by the old check:            55
        actually reassembled from scattered fragments:  49
        genuinely absent from the document:              6
    So fabrication is 6 cases, about 0.5% of predictions. It is essentially
    not a failure mode of this model. Finding 25 stands and is strengthened:
    the problem is wrong-value SELECTION, not invention.

27. THE OCR TEARS MULTI-LINE VALUES APART, and this is a first-class property
    of the substrate rather than an edge case. Addresses in particular get
    split, with form labels interleaved between the street line and the city
    line. Any grounding, span-matching or verification logic has to handle
    non-contiguous values or it will systematically misclassify correct
    output. This also explains part of why tv_address is the worst field: it
    is the only one whose gold value is routinely multi-line.

28. METHOD NOTE. Three summaries pointed the wrong way here. The F1 score said
    "tv_address is bad". Grounding said "27 inventions". Both were true-ish and
    both were misleading. Reading ONE document showed the OCR tears addresses
    apart and that my own detector could not handle reassembly. No aggregate
    could have surfaced either. This is the argument for the protected block
    stated as concretely as I can state it.

## 2026-09-24, step 5: tv_address failure taxonomy

Hand-labelled 10 randomly sampled failures (seed 0, not cherry-picked), then
auto-classified all 107 using the categories that came out of those 10.

  category          10-case sample    all 107
  wrong company            40%         43.9%  (47)
  incomplete               30%         25.2%  (27)
  spurious                 20%         20.6%  (22)
  not an address           10%         10.3%  (11)
  missed entirely           0%          0.0%  (0)

29. TEN HAND-LABELLED CASES PREDICTED 107 TO WITHIN A FEW POINTS ON EVERY
    CATEGORY. This is the argument for open coding in one line. A small
    honest sample, labelled by someone actually looking at the data, gives
    the shape of the whole distribution. Labelling everything was never
    necessary; labelling nothing would have left the 0.256 F1 undiagnosed.

30. THE CATEGORIES CAME FROM THE DATA, NOT FROM ME. I had predicted
    "hallucination" from the precision number (finding 22) and was wrong
    twice: first about fabrication, then about it being one failure mode.
    It is four, with different causes and different fixes. Distribution:

    incomplete (25%): finds the right address, returns only the street line.
      Gold is multi-line; AddressMatch allows edit distance 3, so a missing
      city/state/zip fails by a wide margin. Fix: one prompt sentence asking
      for the complete multi-line address. Cheapest available win.

    spurious (21%): document has no address; model answers anyway. The prompt
      already says "return null. Do not infer." It is ignored about a fifth
      of the time. Needs a stronger instruction or an explicit abstention
      rule, and is worth measuring separately since it is a precision-only
      loss.

    wrong company (44%): the page carries several addresses (station, agency,
      rep firm, billing) and the model picks the wrong one. Same root cause
      as contract_num choosing between Invoice #, Order # and Estimate Number
      (finding 8). The prompt never says WHOSE address is wanted.

    not an address (10%): returns call signs like 'WZTV NASHVILLE'. Likely
      improves with the same disambiguation fix.

31. DO NOT FIX YET. Three of the four have obvious one-line prompt fixes and
    the temptation is to apply all three at once. Apply them one at a time,
    with the expected effect written down first, or the ablation in step 6
    cannot attribute anything. Predicted effects, recorded now so they can be
    checked later: multi-line instruction should recover most of the 25%;
    an explicit "whose address" instruction should recover part of the 44%;
    a stronger null rule should recover part of the 21%.

## 2026-09-24, step 5: agency taxonomy, and why per-field analysis matters

Hand-labelled 10 random agency failures with no categories supplied, having
done the exercise once on tv_address. The categories that emerged were
different, which is itself the finding.

  failure mode              agency        tv_address
  spurious (gold is None)   81.2% (69)    20.6% (22)
  wrong value               15.3% (13)    54.2% (58)
  incomplete (truncated)     3.5% (3)     25.2% (27)

  10-case agency sample said 70% spurious; true figure 81.2%. Within
  sampling error at n=10 and the ranking was correct.

32. AGENCY IS ALMOST ENTIRELY ONE PROBLEM: IT ANSWERS WHEN IT SHOULD NOT.
    69 of its 85 failures are documents with no agency at all. This is the
    precision 0.384 / recall 0.768 signature read correctly: when an agency
    exists the model usually finds it, and when none exists it invents a
    plausible-looking media company from elsewhere on the page.

33. THE SAME FIX IS WORTH TEN TIMES MORE ON ONE FIELD THAN THE OTHER.
    Projected effect of perfect abstention (every spurious prediction
    becomes null; costs zero correct answers):
      agency       F1 0.512 -> 0.768   (+0.256)
      tv_address   F1 0.256 -> 0.280   (+0.024)
    This is the argument for per-field failure analysis in one number. The
    overall score gives no way to see that abstention is the dominant lever
    on one field and nearly irrelevant on another.

34. THE TWO WORST FIELDS NEED DIFFERENT FIXES, not one shared one.
      agency     -> abstention. Stop answering when the field is absent.
      tv_address -> disambiguation (whose address?) plus completeness
                    (return the full multi-line value).
    Had I applied one "improve the prompt" change I would have moved one
    field and learned nothing about the other.

35. THESE ARE PREDICTIONS, NOT RESULTS. The +0.256 and +0.024 above are
    what perfect abstention WOULD yield. Recorded before any prompt change
    so step 6 can compare predicted against actual. If the actual gain is
    far below the projection, that gap is itself the finding: it would mean
    the model cannot tell an absent field from a present one, which is a
    harder problem than instruction-following.

## 2026-09-25, step 6 arm 1: v2_abstain

Changed exactly one file: the null instruction became an explicit paragraph.
Everything else identical. 141 documents, 0 failures.

  overall unrepeated F1  0.6649 -> 0.6784  (+0.0135)   predicted +0.02 to 0.03
    precision            0.6223 -> 0.6479  (+0.0256)
    recall               0.7139 -> 0.7120  (-0.0019)

  agency      F1 0.512 -> 0.552  (+0.040)   PREDICTED +0.256. Got 16% of it.
  tv_address  F1 0.256 -> 0.279  (+0.023)   predicted +0.024. Right number,
                                            WRONG REASON, see finding 38.

36. THE PREDICTION MISSED BY 6x AND THE MECHANISM EXPLAINS WHY. On the 72
    documents with no agency:
      baseline returned null   3/72  ( 4.2%)
      v2_abstain returned null 18/72 (25.0%)
    The instruction worked, six times more abstention, but reached only a
    quarter of the cases. The projected +0.256 assumed 100% abstention. A
    prompt got 25% of the way there. Recording the projection first is what
    makes this measurable rather than a vague "it helped a bit".

37. THE MODEL NEVER ABSTAINS WRONGLY. On the 69 documents where an agency IS
    present, both arms returned null 0 times. Same for tv_address: 0 false
    abstentions out of 118 present cases in both arms. So when it decides to
    return null it is right 100% of the time. It is not confused about
    absence, it is BIASED TOWARD ANSWERING. That is a different problem from
    "cannot tell", and it is the one step 7 should attack: a confidence
    threshold can exploit a signal the model already has, where a prompt is
    just asking more loudly.

38. RIGHT ANSWER, WRONG REASON, and I nearly recorded it as a success. The
    tv_address prediction (+0.024 from abstention) matched the measurement
    (+0.023) almost exactly. But tv_address abstention did not change at all
    (1/23 in both arms). Every one of the 6 gained cases is an INCOMPLETENESS
    fix:
      'PO Box 1001'          -> 'PO Box 1001 Quincy, IL 62306-1001'
      '2302 Lapeer Road'     -> '2302 Lapeer Road, Flint, MI 48503'
    An instruction written to make the model answer LESS made it answer more
    COMPLETELY. Had I checked only the F1 delta against the prediction I would
    have concluded my model of the system was correct when it was not.

39. "ONE FACTOR AT A TIME" IS HARDER THAN IT SOUNDS WITH PROMPTS. I changed
    one file and believed that was one factor. It was not: rewording the null
    rule also changed copying behaviour, so two effects moved at once and
    they partly cancelled (6 gained, 3 lost on tv_address). A prompt is a
    single artifact but not a single variable. Future arms need either a
    minimal diff (one sentence, nothing else touched) or per-failure-mode
    measurement rather than per-field F1, which is what caught this.

40. TIMING ANOMALY, UNEXPLAINED. The arm took 17472s (4.9 hours) against a
    projection of 23 minutes measured from its own first 20 documents
    (254s). Rate degraded from ~13s/doc to ~150s/doc partway through and
    stayed there. Same machine, same model, same settings as the baseline
    run which completed 141 documents in 1905s. Not investigated. Logged so
    it is not silently forgotten.
