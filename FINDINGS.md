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