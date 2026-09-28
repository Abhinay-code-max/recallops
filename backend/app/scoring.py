"""Fix ranking formula.

Scaffold only — implemented in Prompt 3 (docs/PROMPTS.md).

Per docs/SPEC.md section 5:
score = similarity * (worked + 0.5*partial + 1) / (attempts + 2) - 0.3 * recent_failures
"""
