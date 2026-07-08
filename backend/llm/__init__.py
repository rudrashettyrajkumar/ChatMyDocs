"""BYOK (bring-your-own-key) multi-provider LLM layer.

Everything the BYOK feature knows about providers lives under this package:

- `catalog`   — the static provider/model catalog served to the frontend
- `runconfig` — per-request provider selection parsed from `X-LLM-*` headers
- `factory`   — LangChain chat-model construction (lazy provider imports)
- `gateway`   — the single chokepoint every agent calls (`complete`/`stream`)
- `embedder`  — 768-dim BYOK embeddings (OpenAI-compatible gateways)
- `reranker`  — optional open-source cross-encoder rerank (FlashRank)
"""
