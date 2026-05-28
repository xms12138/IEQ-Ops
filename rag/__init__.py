"""RAG knowledge base: deterministic ingestion + retrieval over building standards.

No LLM lives in the retrieval path (Hard Constraint #9). `ingest.py` may call a
cloud LLM to write Anthropic-style contextual prefixes, but `retrieve.py` and the
mcp-rag-server that wraps it are pure retrieval primitives.
"""
