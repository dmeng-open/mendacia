# Open questions for the operator

## P3-4: the 300 ms search p95 budget cannot hold with a live query embedding

The plan's P3-4 perf rule fails when search p95 exceeds 300 ms. With `LLM_MODE=live`, the retrieval
eval measured p95 305 ms overall (gallery 308 ms, lighthouse 259 ms, manor 275 ms). The same
searches without the query embedding have p95 6.1 ms. The embedding call to
`openai/text-embedding-3-small` is the limiter: a raw keep-alive HTTP probe from the cloud container
to the OpenAI embeddings endpoint measured median 213 ms and p95 324 ms over 15 calls, so no search
code can bring the total under 300 ms on this network.

Default taken: the code ships as is. The report prints p95 with and without the embed, so both
numbers stay visible. Options for the operator:

1. Judge the 300 ms budget on search time excluding the query embedding (6.1 ms), and set a separate
   budget for the embedding round trip.
2. Raise the budget to cover the provider round trip (for example 500 ms).
3. Cache query embeddings by model and normalized query text (ADR 009 allows this key). Repeat
   queries then skip the round trip, but a first query still pays it.
