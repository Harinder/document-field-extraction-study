# How the failure taxonomy was built

[Back to the README](../README.md)

Ten `tv_address` failures, sampled at seed 0 and not cherry-picked, hand-labelled
against a short list of candidate categories, with `???` for anything that did not
fit. The filled-in sheets are in [`annotations/`](../annotations/); every case marked
`???` there has no gold value, so it counts as spurious. The categories were then
applied to all 107.

| category | 10-case sample | all 107 |
|---|---|---|
| wrong company | 40% | 43.9% |
| incomplete | 30% | 25.2% |
| spurious (no address on the page) | 20% | 20.6% |
| not an address (returned a call sign) | 10% | 10.3% |
| missed entirely | 0% | 0.0% |

The code that sorted all 107 into these categories is not in the repo, so unlike
the F1 figures these counts cannot be regenerated from the cache.

Ten cases predicted 107 to within a few points on every category. Labelling
everything was never necessary and labelling nothing would have left a 0.256 F1
undiagnosed. Repeating the exercise on `agency` gave a very different split: 81% of its
failures are documents with no agency at all, against 21% for `tv_address`. That
is its own finding: the two worst fields fail for unrelated reasons and I would
have missed that by pooling them.
