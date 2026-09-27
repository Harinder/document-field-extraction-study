# Vendored: VRDU evaluator

These four files are Google Research's evaluator for the VRDU benchmark, copied
without changes from
[google-research/google-research/vrdu](https://github.com/google-research/google-research/tree/master/vrdu).

| file | what it does |
|---|---|
| `evaluate.py` | command-line entry point |
| `evaluate_utils.py` | loads predictions and splits |
| `benchmark_utils.py` | loads the dataset, computes precision, recall and F1 |
| `match_utils.py` | the match rules, one per field type |

They are licensed under Apache 2.0, see [`LICENSE`](LICENSE) in this folder. The
MIT licence at the repo root does not apply to them.

To confirm they are unmodified, compare each file's git blob hash with upstream:

```bash
git hash-object vendor/vrdu/*.py
```
