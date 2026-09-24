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
