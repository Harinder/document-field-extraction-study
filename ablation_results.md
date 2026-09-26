# Ablation results

One factor changed per arm. Hypothesis recorded before each run.
Arms that made things worse are kept, because those are the informative ones.

| arm | unrep F1 | precision | recall | n | note |
|---|---|---|---|---|---|
| v1_baseline | 0.6649 | 0.6223 | 0.7139 | 141 docs | original prompt |
| v2_abstain | 0.6784 | 0.6479 | 0.7120 | 141 docs | +0.0135. Predicted +0.02 to 0.03. See FINDINGS 36 to 39 |
| v3_complete | 0.6810 | 0.6472 | 0.7185 | 141 docs | +0.0161. tv_address +0.142, but 6 of 9 fields slightly worse. FINDINGS 41 to 43 |
| **v4_whose** | **0.7212** | 0.6772 | 0.7713 | 141 docs | **+0.0563, best arm.** tv_address +0.278, 7 of 9 fields improved. But NOT via the intended mechanism. FINDINGS 44 to 47 |
