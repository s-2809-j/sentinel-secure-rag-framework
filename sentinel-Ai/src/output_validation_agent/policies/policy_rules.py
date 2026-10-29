from __future__ import annotations

from src.output_validation_agent.models import OutputCategory


ALLOW = "allow"
SANITIZE = "sanitize"
BLOCK = "block"


POLICY_RULES: dict[OutputCategory, str] = {
    #
    # Safe responses.
    #
    OutputCategory.SAFE: ALLOW,

    #
    # Hallucination and unsupported claims.
    #
    OutputCategory.HALLUCINATION: SANITIZE,
    OutputCategory.UNSUPPORTED_CLAIM: SANITIZE,

    #
    # Response must never be returned.
    #
    OutputCategory.PROMPT_LEAKAGE: BLOCK,
    OutputCategory.PII: BLOCK,
    OutputCategory.POLICY_VIOLATION: BLOCK,
}
