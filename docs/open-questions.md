# Still open

[Back to the README](../README.md)

Recorded rather than quietly dropped.

Wrong-value selection is unsolved and is now essentially the whole problem, 50 of
`tv_address`'s 63 remaining failures. The arm written to fix it, `v4_whose`,
moved that count from 47 to 50, and `v3_complete` pushed it to 65 as cases it
fixed in form turned into well-formed wrong picks. Prompting has not reduced it.
It needs a different mechanism: span
retrieval, a two-stage approach that locates the station block first, or per-field
few-shot examples.

The valid split has never been run, so both the arm selection and the
risk-coverage curve are fitted on the data they were scored on. First thing I
would fix.

Whether constrained decoding caused the sampling collapse, as described in
[the confidence write-up](confidence.md).

One unexplained timing anomaly. The `v2_abstain` run took 4.9 hours against a 23-minute
projection measured from its own first 20 documents. The rate degraded from about
13s to about 150s per document partway through and stayed there, on the same
machine and settings as a baseline run that did 141 documents in 1905s. Not
investigated.

Whether schema breadth hurts. Expanding one call from 6 fields to 9 made four
fields start returning null, including one that had been correct. Splitting into
two calls of 4 and 5 is an untested arm.

Line items: 5 fields, variable per-row field sets, a median of about 12 rows per
document. The row-matching key is a judgement call worth several points of score.
