# Confidence, and why it didn't work

[Back to the README](../README.md)

A model that is 68% correct per prediction is not useful on its own. It becomes
useful if it can tell you which 20% to send to a human, so I spent a step trying
to build per-prediction confidence. Three mechanisms, measured rather than
assumed:

```
signal                     separation              reach
grounding in source text   69.8% vs 0.0% correct   5 of 1230 predictions
field identity             97.1% vs 44.0%          a prior, not confidence
self-consistency (3x)      75.1% vs 33.3%          27 of 360 predictions
```

Self-consistency is the one that works. Unanimous answers across three samples
are 75.1% correct and split answers 33.3%, and the Wilson 95% intervals don't
overlap ([70.2, 79.4] against [18.6, 52.2]), so a 42-point gap holds up even at
n=27. Per unit of coverage given away it is nearly twice as efficient as the
trivial alternative of dropping the worst fields outright: 0.43 accuracy points
per percent, against 0.25.

It also barely fires. 92.5% of predictions are unanimous at temperature 0.7, so
you pay 3x inference to flag 7.5% of your answers.

Three separate measurements turned out to be saying the same thing. Temperature 0
gives byte-identical predictions across runs. When the model returns null it is
right 100% of the time, zero false abstentions across 187 present-field cases in
two arms. And at temperature 0.7 it will not disagree with itself.

The model is stable in its errors rather than uncertain about them. It is
confidently wrong, which is why a prompt asking it to abstain reached a quarter
of the cases it should have, why grounding separates almost nothing, and why no
amount of sampling will surface most of the errors. Systematic errors need a
corrective instrument, not an estimator.

There is a suspect for the cause, and it is self-inflicted. Constrained decoding
with a JSON grammar, a 120-character bound and one obvious candidate on the page
leaves very few valid next tokens at each step, and temperature can only spread
probability across choices that still exist. Structured output bought guaranteed
parseable answers and plausibly cost the ability to measure uncertainty by
sampling. That tradeoff appears in none of the "always use strict schema mode"
advice I read. It is untested here; testing it means sampling without the schema
and comparing diversity, which is the experiment I would run after the valid split.

[ADR 0002](adr/0002-confidence-and-abstention.md) has the full comparison
and the routing decision that came out of it.
