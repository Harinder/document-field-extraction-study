# What I got wrong

[Back to the README](../README.md)

**I read a precision of 0.384 as hallucination.** It wasn't. A grounding check
showed all 138 `agency` predictions were real text copied off the page, and
genuine fabrication came to 6 cases in 1239 predictions. The model was selecting
wrong values, not inventing them. Those two diagnoses call for completely
different fixes, thresholds and abstention for one, disambiguation and retrieval
for the other, so I would have built the wrong thing.

**My grounding check was itself wrong, and only reading a document by hand found
it.** On document `300535fe` the model predicted `16 Cypress Ave Wheeling, WV
26003` and my check called it invented. The OCR reads:

```
... Billing Calendar: / Broadcast / 16 Cypress Ave / EOM/EOC /
    Billing Cycle: / Agency Commission: / Wheeling, WV 26003 / 15% ...
```

Both halves are there, torn apart, with unrelated form labels sitting between the
street line and the city line. The model had correctly reassembled a real address
from fragments and my contiguous-substring check scored that as fabrication. Of
55 flagged predictions, 49 were reassembly and 6 were real. No aggregate would
have surfaced this. The F1 said "tv_address is bad" and the grounding check said
"27 inventions", and both were true enough to be misleading.

**All three prompt revisions improved the score through a mechanism other than
the one I designed them for.** Every time. Arm 1 aimed at abstention and
accidentally improved completeness. Arm 2 aimed at completeness, hit it, and
converted its fixed cases into a new failure category. Arm 3 aimed at
disambiguation, didn't achieve it at all, and delivered the biggest formatting fix
of the three. An F1 delta tells you whether something changed and never why. All
three would have gone down as confirmed hypotheses if I had stopped at the score,
and only the per-failure-mode breakdown caught it.

**"One factor at a time" is harder than it sounds with prompts.** I changed one
file and assumed that was one variable. Rewording the null rule also changed
copying behaviour, so two effects moved at once and partly cancelled each other:
six cases gained, three lost, on the same field. A prompt is a single artifact but
not a single variable.

**I predicted the wrong ordering of what prompting buys.** After arm 2 I
concluded that instructions about output shape land well and instructions about
decisions don't. Arm 3 was neither and beat both. The revised ordering, on this
task:

```
semantic clarity  (what the field MEANS)    largest, and broadly positive
output shape      (how to format it)        moderate, narrow, with real costs
decisions         (when to abstain)         smallest
```

`contract_num` gained +0.063 without appearing in the prompt at all, which is the
best evidence for the semantic reading. Clarifying the document's cast of
organisations helped a field nobody mentioned.
