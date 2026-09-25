# Ablation results

One factor changed per arm. Hypothesis recorded before each run.
Arms that made things worse are kept, because those are the informative ones.

| arm | unrep F1 | precision | recall | n | note |
|---|---|---|---|---|---|
| v1_baseline | 0.6649 | 0.6223 | 0.7139 | 141 docs | original prompt |
| v2_abstain | 0.6784 | 0.6479 | 0.7120 | 141 docs | +0.0135. Predicted +0.02 to 0.03. See FINDINGS 36 to 39 |
