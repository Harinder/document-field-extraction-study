# Four infrastructure problems worth knowing about

[Back to the README](../README.md)

None of these are model behaviour. All four produce a run that finishes cleanly
and reports the wrong thing, which is the failure mode worth rehearsing.

Ollama loads models at `num_ctx 4096` regardless of what the model supports.
`qwen3:14b` supports 40960. At 4096, 69 of 641 documents get silently truncated,
10.8% of the corpus, with no error and no warning, just missing text and
inexplicable failures on the longest documents. Fixed in the `Modelfile`, which
is committed for exactly that reason.

Non-determinism is large, and qwen3 defaults to temperature 0.6. Two identical
runs disagreed on `contract_num` (`950658-1` then `0129`), on `advertiser` (null
then correct) and on `product`. Every run was a sample rather than an answer, so
an informal 8-of-12 could have been 6 or 10, and two prompts can't be compared on
one run each.

Thinking mode can't be disabled through Ollama's OpenAI-compatible `/v1`
endpoint. Neither `think=false` nor an in-prompt directive works, because it is
baked into the chat template. That is around 3000 hidden reasoning tokens per
document and roughly 10x wall clock on what is fundamentally a copying task. The
native `/api/chat` endpoint honours it and structured output still works there.

Unbounded strings under grammar constraint run away. A schema saying
`{"type": ["string", "null"]}` sets no length bound, so echoing the entire source
document into one field is perfectly valid output. The decisive one-variable test,
on document `05998648`:

```
maxLength 120   ->  6.8s, 169 tokens, correct values
unbounded       ->  TIMEOUT at 120s
```

Constrained decoding guarantees the output is valid, not that it is sensible, and
an unconstrained model would simply have stopped talking. This is a failure mode
strict schema modes introduce rather than prevent. Adding `maxLength` turned the
split from an estimated 18 hours into 16 minutes, and it isn't a workaround
either: an advertiser name is short and a flight date is eight characters. The
schema had been asserting that any of them could be a paragraph.
