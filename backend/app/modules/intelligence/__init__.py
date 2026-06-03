"""Intelligence layer: AI summaries, risk detection, recommendations, reports, digests.

Design principle: every number is computed deterministically in Python (testable,
explainable, never hallucinated). AI is used only to wrap those facts in a readable
narrative, and degrades gracefully to a deterministic narrative when no key is present.
"""
