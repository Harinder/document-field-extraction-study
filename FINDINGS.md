## first run: qwen3:14b, 6 unrepeated fields, 3 docs

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
## infrastructure findings (not model behaviour)

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

## schema expanded from 6 to 9 unrepeated fields

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

## step 3 harness: infrastructure debugging

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

## FIRST EXTERNALLY SCORED BASELINE

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
    [Later note: finding 12 is about schema breadth, not micro/macro, so this
    cross-reference points at the wrong finding.]

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

## step 4: grounding

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
    [Later note: wrong, for the reason finding 26 gives. The check only looked
    for contiguous text. Google's character spans put each of these 23
    tv_address values in two or three separate places in the OCR, so all of
    them are on the page and the ceiling is not 0.90.]

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

## step 5 open coding: a measurement bug found by reading

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

## step 5: tv_address failure taxonomy

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

## step 5: agency taxonomy, and why per-field analysis matters

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

## step 6 arm 1: v2_abstain

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

## step 6 arm 2: v3_complete

One paragraph added to BASELINE v1 (not to v2), asking for complete multi-line
values. 141 documents, 0 failures, 1913s.

  overall unrepeated F1  0.6649 -> 0.6810  (+0.0161)   predicted ~0.69
  tv_address        F1   0.256  -> 0.398   (+0.142)    predicted 0.33 to 0.40

41. PREDICTION LANDED THIS TIME, at the top of the stated range. The ceiling
    from perfect completeness was 0.465; the arm reached 0.398, which is 68%
    of the available gain. Arm 1 reached 25% of its target. The difference is
    worth noting: completeness is a formatting instruction the model can
    simply comply with, while abstention requires it to judge that something
    is absent. Instructions that ask for a different OUTPUT SHAPE land much
    better than instructions that ask for a different DECISION.

42. THE FIX CHANGED HOW IT ANSWERS, NOT WHAT IT PICKS. By failure mode:
      CORRECT          33 -> 49   (+16)
      incomplete       27 ->  3   (-24)   target, nearly eliminated
      not an address   11 ->  1   (-10)   not targeted
      spurious         22 -> 10   (-12)   not targeted
      wrong value      47 -> 65   (+18)   WORSE
    The +18 are not new failures. They are the same documents moving between
    categories: a case that used to return 'WSAZ' now returns a complete,
    well-formed address belonging to the wrong company. Form fixed, selection
    untouched. tv_address failures are now 71% wrong value (65 of 92), which
    is the disambiguation problem and the target for arm 3.

43. COLLATERAL DAMAGE IS REAL AND THE HEADLINE HIDES IT. Six of nine fields
    got slightly worse:
      tv_address +0.142   property +0.030   agency +0.008
      product -0.005   advertiser -0.007   gross_amount -0.008
      flight_to -0.010   contract_num -0.013   flight_from -0.013
    A rule about returning fuller values makes every field more verbose,
    which helps one multi-line field and mildly hurts eight single-value
    ones. Net +0.0161 overall. Reporting only the overall delta would hide
    both the +0.142 and the eight small regressions, and reporting only the
    target field would hide the cost entirely. Per-field tables are not
    decoration.

## step 6 arm 3: v4_whose

One paragraph added to BASELINE v1 naming which organisation each field refers
to. Rule derived from the data, not guessed: gold tv_address sits near the
station call sign or after "REMIT TO" ('remit' appeared 23 times in preceding
context). 141 documents, 0 failures, 4270s.

  overall unrepeated F1  0.6649 -> 0.7212  (+0.0563)   BEST ARM
  tv_address        F1   0.256  -> 0.534   (+0.278)    predicted 0.35-0.42, EXCEEDED
                                                        86% of the 0.620 ceiling

  per field: tv_address +0.278, property +0.081, agency +0.069,
             contract_num +0.063, advertiser +0.029, product +0.007,
             gross_amount 0, flight_to -0.005, flight_from -0.016
  Seven of nine improved or held. Arm 2 regressed six.

44. THE BEST ARM FAILED AT ITS STATED PURPOSE. By failure mode:
      CORRECT          33 -> 66  (+33)
      wrong value      47 -> 50  ( +3)   the target, UNCHANGED
      incomplete       27 ->  1  (-26)
      not an address   11 ->  0  (-11)
      spurious         22 -> 12  (-10)
    I wrote this prompt to fix wrong-company selection. It did not fix it.
    It fixed the FORM problems again, more thoroughly than arm 2 did and
    without arm 2's collateral damage, probably because describing what a
    remittance address is teaches the shape implicitly while "it is NOT the
    agency's address" discourages grabbing a nearby wrong value.

45. WRONG-VALUE SELECTION IS UNSOLVED AND IS NOW THE WHOLE PROBLEM. 50 of
    tv_address's 63 remaining failures. Three prompt arms have moved it by
    +3, -0 and +3. Prompting has not touched it. If it is to be fixed it
    needs a different mechanism: retrieval of the right text span, a
    two-stage approach that first locates the station block, or per-field
    few-shot examples. That is a step 7 or step 8 question, not another
    prompt reword.

46. THREE ARMS, THREE TIMES THE MECHANISM DIFFERED FROM THE DESIGN INTENT.
      arm 1 aimed at abstention: got 25% of it, and accidentally improved
             completeness on tv_address.
      arm 2 aimed at completeness: hit it, and accidentally improved
             not-an-address and spurious, while converting fixed cases into
             wrong-value ones.
      arm 3 aimed at disambiguation: did not achieve it at all, and instead
             delivered the largest form-fix of the three.
    An F1 delta tells you IF something changed, never WHY. Every one of these
    three arms would have been written up as a confirmed hypothesis if I had
    stopped at the score. The per-failure-mode breakdown is the only thing
    that caught it, all three times.

47. REFINEMENT OF FINDING 41. I had concluded shape instructions land and
    decision instructions do not. Arm 3 is neither: it is semantic, telling
    the model what the field MEANS. It beat both, and it helped seven fields
    instead of hurting six. Revised ordering of what prompting buys, on this
    task:
      semantic clarity (what the field means)   largest, broadly positive
      output shape (how to format)              moderate, narrow, with costs
      decisions (when to abstain)               smallest
    contract_num gained +0.063 without being mentioned in the prompt at all,
    which supports the semantic reading: clarifying the document's cast of
    organisations helps fields that were never named.

## step 7: confidence from free features (weak result)

Built on the v4_whose predictions, no new inference. 1230 non-null predictions,
67.7% correct overall.

48. GROUNDING QUALITY PREDICTS CORRECTNESS MONOTONICALLY, BUT REACHES ALMOST
    NOTHING.
      exact match in text   1160 preds  69.8% correct
      whitespace difference   37 preds  40.5% correct
      reassembled fragments   28 preds  28.6% correct
      absent entirely          5 preds   0.0% correct
    The ordering is clean and real. But 94% of predictions are exact matches,
    so this feature separates only 70 of 1230. Useful as a hard filter on the
    5 absent cases, useless as a ranking signal.

49. THE STRONGEST AVAILABLE SIGNAL IS JUST WHICH FIELD IT IS, which means it
    is a prior rather than confidence.
      gross_amount 97.1%   advertiser 89.4%   product 72.1%
      contract_num 68.4%   flight_to 65.9%    flight_from 63.0%
      property 56.1%       tv_address 51.2%   agency 44.0%
    A 53-point spread. But a per-field rate cannot tell me WHICH agency
    predictions are good, only that agency is bad on average. That is not
    per-prediction confidence and should not be reported as if it were.

50. MY RISK-COVERAGE CURVE IS BARELY BETTER THAN A TRIVIAL BASELINE, and this
    is the honest headline of step 7 so far.
      coverage  accuracy      vs dropping worst fields outright
        100%      67.7%       all 9 fields            67.7%
         90%      72.1%       drop agency             70.6%
         80%      73.6%       drop agency+tv_address  73.2%
         70%      75.6%       drop 3 fields           76.1%
         50%      80.0%       drop 4 fields           78.7%
    At 70% coverage the trivial rule BEATS my score. The curve is dominated by
    field identity, so it is field-dropping with extra steps. Reporting the
    curve without this comparison would have made a prior look like a model.

51. THE CURVE ABOVE IS LEAKY AND MUST NOT BE REPORTED AS A RESULT. The
    per-field rates used to rank were computed on the same 141 documents being
    scored. The split's valid set (100 documents) has never been used and is
    the correct place to fit. Doing it properly requires a run on valid, which
    is the next step, not this one.

52. WHAT THIS IMPLIES FOR REAL CONFIDENCE. A useful signal must vary WITHIN a
    field. Free features do not: grounding is flat across 94% of cases and
    field identity is constant by definition. The signals that would vary are
    all paid:
      self-consistency  sample N times, measure agreement. Costs Nx inference.
      verbalized        ask the model for a score. One extra field, cheap, but
                        known to be poorly calibrated.
      logprobs          not exposed on ollama's native /api/chat path.
    Finding 37 says the signal exists (the model never abstains wrongly), so
    the question is which mechanism surfaces it. Self-consistency is the one
    worth testing next: on a 40-document subset at 3 samples it is about 25
    minutes and directly tests whether disagreement predicts error.

## step 7: self-consistency (real signal, narrow reach)

40 documents x 3 samples at temperature 0.7 with the v4_whose prompt, different
seeds. 360 field predictions, 1067s.

  3 of 3 agree   333 preds  75.1% correct   Wilson 95% CI [70.2, 79.4]
  2 of 3 agree    24 preds  33.3% correct
  1 of 3 agree     3 preds  33.3% correct
  disagreement combined  27 preds  33.3%    Wilson 95% CI [18.6, 52.2]
  overall        360 preds  71.9% correct

53. SELF-CONSISTENCY IS THE FIRST CONFIDENCE SIGNAL THAT BEATS THE TRIVIAL
    BASELINE. A 42-point accuracy gap between unanimous and split answers,
    and the Wilson intervals do not overlap, so the separation holds even
    at n=27. Efficiency comparison:
      self-consistency  drop 7.5% of answers, gain 3.2 points   0.43 pts/%
      field prior       drop 50%  of answers, gain 12.3 points  0.25 pts/%
    Nearly twice the accuracy gain per unit of coverage sacrificed. It is
    also the only signal so far that varies WITHIN a field, which is what
    findings 48 to 52 said was required.

54. BUT 92.5% OF PREDICTIONS ARE UNANIMOUS AT TEMPERATURE 0.7. Disagreement
    flags only 27 of 360. Same shape as grounding: clean signal, almost no
    reach. To use it you pay 3x inference to identify 7.5% of your answers
    as suspect. Whether that trades well depends entirely on whether there
    is a human review queue on the other side.

55. THE MODEL IS STABLE IN ITS ERRORS, NOT UNCERTAIN ABOUT THEM, and three
    separate findings now say the same thing:
      finding 11  temperature 0 gave byte-identical answers across runs
      finding 37  it never abstains wrongly; when it says null it is right
      finding 54  it will not disagree with itself even at temperature 0.7
    It is confidently wrong. That is why arm 1's abstention prompt reached
    only 25%, and why no sampling method will surface most of the errors.
    Systematic errors need a different instrument than uncertainty estimates.

56. CONSTRAINED DECODING PROBABLY CAUSES THE COLLAPSE, and this is a real
    tradeoff nobody mentions when recommending strict schema modes. With a
    JSON schema, maxLength 120, and a document containing one obvious
    candidate, the set of valid next tokens at each step is small.
    Temperature can only spread probability across choices that exist, and
    the grammar has removed most of them. Structured output bought
    guaranteed-parseable answers and cost the ability to measure uncertainty
    by sampling. Not tested directly; testing it would mean sampling without
    the schema and comparing diversity, which is a clean follow-up
    experiment and is not run here.

## step 8: writing it up

57. WRITING THE README FOUND A VERIFICATION GAP I DID NOT KNOW I HAD. The
    per-field baseline numbers existed only inside a log line from an earlier
    run, and the baseline run's own log did not print them at all. I
    had been deriving them by subtracting the deltas quoted in findings 43 and
    the arm 3 block. That works until one of those deltas is a typo, and then
    every derived number is wrong with no way to notice.
    Fixed by writing score_arm.py, which re-scores any arm from its cached
    responses with zero inference. Re-scored v1 and all nine fields matched the
    derived values exactly (advertiser 0.868, agency 0.512, contract_num 0.616,
    flight_from 0.698, flight_to 0.722, gross_amount 0.968, product 0.741,
    tv_address 0.256, property 0.531).
    The derivation happened to be right. The point is that I could not have
    known that before checking, and a published table nobody can regenerate is
    a claim rather than a measurement. Caching every raw response per arm, a
    decision made for speed in step 6, is what made the check cost 4 seconds
    instead of 5 hours.

58. THE ENDPOINT CHOICE FORECLOSED THE CONFIDENCE APPROACH, and I only saw the
    causal chain while writing ADR 0002. Thinking mode could not be disabled on
    ollama's /v1 path (finding 15), so I moved to native /api/chat. Native
    /api/chat does not expose token logprobs. Logprobs are the cheapest and
    best-calibrated confidence signal in the literature. So a decision taken
    purely to cut 10x wall clock in step 3 removed the best available option in
    step 7, several steps later, and nothing flagged it at the time.
    This is the shape of infrastructure decision worth writing down: it was
    correct on its own terms, it had no visible cost when made, and its real
    cost was paid by a part of the system that did not exist yet.

59. THE HONEST HEADLINE IS NOT THE F1. Ranked by what survived scrutiny:
      the model is confidently wrong, not uncertain (findings 11, 37, 54, 55)
      wrong-value selection is the whole remaining problem (findings 25, 45)
      an F1 delta never tells you WHY, three arms for three (finding 46)
      constrained decoding may have caused the collapse it also prevents
        (findings 16, 19, 56)
    0.6649 -> 0.7212 is the fourth most interesting thing here, and it is the
    only one a leaderboard would record.

60. WHAT I WOULD DO DIFFERENTLY, in order of how much time it cost me.
    Run the valid split on day one so there is always a clean surface to
    report on. I have a leaky risk-coverage curve and a selected-on-test best
    arm purely because I never held anything back, and both are now caveats
    in the README instead of results.
    Print per-field scores from every run, including the very first. Cost me
    findings I had to reconstruct later.
    Measure per-failure-mode, not per-field, from the first ablation onward.
    The score moved for the wrong reason three times out of three, and the
    per-field table caught none of them.
    Read one document by hand before trusting any detector I wrote. My
    grounding check was wrong for several rounds and only reading document
    300535fe exposed it.
