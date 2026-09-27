# ADR 0001. What "correct" means

**Status:** accepted

**Source:** `data/vrdu/main/meta.json` and `vendor/vrdu/match_utils.py`, read directly.

## Context

The headline number is produced by Google's evaluator, so "correct" here means
whatever their match functions accept, which is not the same as string equality.
Before designing the extraction pipeline I read that code.

## The schema

14 fields, split by appearance pattern:

**Unrepeated (one value per document, 9):**
`advertiser`, `agency`, `contract_num`, `flight_from`, `flight_to`,
`gross_amount`, `product`, `tv_address`, `property`

**Line item (repeated per table row, 5):**
`channel`, `program_desc`, `program_start_date`, `program_end_date`, `sub_amount`

## What each matcher accepts

Every matcher runs `remove_redundant_whitespace` first, strips leading/trailing
whitespace and collapses runs of whitespace to a single space.
`' abc\ndef   ghi\t'` becomes `'abc def ghi'`.

| Matcher | Fields | Rule |
|---|---|---|
| `GeneralStringMatch` | advertiser, agency, product, property, channel, program_desc | Strip all non-alphanumerics, then exact compare. **Case sensitive.** |
| `NumericalStringMatch` | contract_num | Strip all non-digits, then exact compare |
| `DateMatch` | flight_from, flight_to, program_start_date, program_end_date | Same year/month/day, **or** same year with month and day swapped (handles MM/DD vs DD/MM) |
| `PriceMatch` | gross_amount, sub_amount | Parse to number, match if absolute difference < 0.01 |
| `AddressMatch` | tv_address | Levenshtein edit distance ≤ 3 |

## Multiple occurrences

Gold stores **every** occurrence of a value, not one canonical position. On the
first document, `property` = `"KMSP\n"` appears four times (twice per page, across
two pages). `match()` loops over all labelled entities and returns True on the
first hit, so **matching any single occurrence scores correct.** There is no need
to reproduce the duplication or pick a particular occurrence.

## Consequences

**Formatting does not need normalising.** Currency symbols, thousands separators,
date format, trailing punctuation and newlines are all absorbed by the matchers.
Effort spent reproducing gold's exact string form is wasted.

**Case does need preserving.** `match_by_alpha_numeric_text` never lowercases, so
`"kmsp"` fails against `"KMSP"`. This is the one strictness in an otherwise
lenient set.

**The metric is more forgiving than "actually right", and the number is therefore
slightly optimistic.** Specifically:

- `PriceMatch` tolerance is 0.01, the docstring's own example is `"$3.14" == "3.1415926"`.
- `AddressMatch` passes anything within 3 edits of the gold address.
- `NumericalStringMatch` strips everything non-numeric from `contract_num`, so a
  different identifier whose digits coincide would score as a match.

The README lists this under [What this number does not cover](../../README.md#what-this-number-does-not-cover), and [the full results](../results.md#what-this-number-does-not-cover) cover all three matchers.

## My own judgement calls, revisited after the runs

I wrote these down before the first runs. The answers underneath came later.

- [x] `tv_address` is the **remit** address, not the station's physical address.
      Confirm against several documents and note how often that distinction bites.

  Not only the remit address. Gold is the station's address, or the address
  payment is remitted to on its behalf, usually near the call sign or after
  "REMIT TO" (FINDINGS.md, step 6 arm 3, and `prompts/v4_whose.txt`). I did not
  count how often the station-versus-remit choice alone causes a miss.

- [x] `gross_amount`, on document 1 the candidates are $5,625.00 (Gross Total),
      $843.75 (Agency Commission), $4,781.25 (Net Amount Due). Record which one
      gold selects and whether the field name alone is enough to disambiguate.

  Gold is $5,625.00, the Gross Total (`traces/run-2154.txt`). The field name was
  enough: the first prompt says nothing about gross versus net, and
  `gross_amount` still scored F1 0.968 (finding 22).

- [ ] `agency` vs `advertiser`, how often are these confusable on real documents?

  Still open, I did not count it. The `agency` failure taxonomy has no category
  for it, and 81% of `agency` failures turned out to be documents with no agency
  at all (finding 32).

- [x] Absent fields: gold simply omits a field that is not present. Decide how the
      schema represents that (null vs missing) and note that there is no gold
      label for the distinction, so it is an internal convention only.

  Decided: every field is required and typed string or null, so the model
  returns null, and nulls are left out of the predictions file the same way gold
  leaves the field out (`SCHEMA` and the results loop in `baseline.py`).

- [ ] Line items: what is the row-matching key, given 5 fields per row, partial
      rows, and a median of ~12 rows per document? This is a judgement call worth
      several points of score.

  Still open. Line items were scoped out (addendum below) and are listed in
  [Still open](../open-questions.md).

---

## Addendum, the annotation format is not uniform

Discovered by crashing on it. `annotations` is a list of `[key, values]` pairs,
but `key` has two different types:

- **Unrepeated field:** `key` is a **string** (the field name). `values` is a list
  of occurrences, each `[text, [page,x0,y0,x1,y1], [[char_start,char_end]]]`.
- **Line-item row:** `key` is a **list of field names** present in that row, e.g.
  `['channel','program_desc','program_start_date','program_end_date']`. `values`
  holds occurrence groups whose members align **positionally** to that tuple.

So each line-item entry is one table row, and rows carry **variable field sets**.
Document 1 has 8 rows in 2 variants: 7 with four fields, 1 with only
`['channel','program_desc']`. `sub_amount` does not appear at all in this
document despite being in the schema.

**Decision:** scope the first pass to the 9 unrepeated fields. `benchmark_utils.py`
emits an unrepeated-only aggregate, so a real externally-scored number is
reachable without solving row alignment first. Line items come later, and the
row-matching key is a judgement call worth several points.
