"""Three-tier memory system (episodic / semantic / procedural).

- episodic.py  (Qdrant `ieq_incidents`) — incident trajectories, written by the
  verifier on close, recalled inline by the planner (and listed by the reflector).
- semantic.py  (Qdrant `ieq_semantic_facts`) — building-specific facts, minted
  weekly by the reflector, recallable by similarity.
- procedural.py (Postgres `sops`) — SOP templates with trigger conditions, drafted
  weekly by the reflector and queued PENDING until a human signs off (#8 gating).

The weekly ReflectionGraph (core/reflection.py) consolidates episodic → semantic +
procedural; the planner reads episodic at planning time. Cross-tier flow goes
through these module functions, never agent-to-store directly.

Hard Constraint #3: every memory write goes through a function in this package
with audit logging — agent nodes never touch Qdrant/Postgres for memory directly.
The verifier calls `episodic.save_trajectory()`; the reflection consolidate node
calls `semantic.save_facts()` / `procedural.queue_sop()`; none upsert inline.
"""
