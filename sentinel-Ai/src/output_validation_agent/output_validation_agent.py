from __future__ import annotations

import logging

from src.output_validation_agent.models import (
    ValidationContext,
    ValidationDecision,
    ValidationResult,
)
from src.output_validation_agent.sanitizer.response_sanitizer import (
    ResponseSanitizer,
)
from src.output_validation_agent.policies.output_policy_engine import (
    OutputPolicyEngine,
)
from src.output_validation_agent.risk.output_risk_engine import (
    OutputRiskEngine,
)
from src.output_validation_agent.validators.base import (
    BaseValidator,
)
from src.output_validation_agent.exceptions import (
    ValidatorExecutionError,
    InvalidValidationContextError,
    InvalidValidationResultError,
)
logger = logging.getLogger(__name__)


class OutputValidationAgent:
    """
    Orchestrates output validation for every LLM response.

    Responsibilities
    ----------------
    - Execute every validator.
    - Collect ValidationResults.
    - Evaluate policy.
    - Compute overall risk.
    - Sanitize the response when required.
    - Produce the final ValidationDecision.

    This class contains no validation logic.
    """
    def __init__(
        self,
        validators: list[BaseValidator],
        policy_engine: OutputPolicyEngine,
        risk_engine: OutputRiskEngine,
        sanitizer: ResponseSanitizer,
    ) -> None:

        if not validators:
            raise ValueError(
                "At least one validator must be provided."
            )

        if policy_engine is None:
            raise ValueError(
                "policy_engine cannot be None."
            )

        if risk_engine is None:
            raise ValueError(
                "risk_engine cannot be None."
            )

        if sanitizer is None:
            raise ValueError(
                "sanitizer cannot be None."
            )

        self._validators = validators
        self._policy_engine = policy_engine
        self._risk_engine = risk_engine
        self._sanitizer = sanitizer

    def validate(
        self,
        context: ValidationContext,
    ) -> ValidationDecision:
        """
        Validate an LLM response and produce the final decision.
        """
        if not isinstance(
            context,
            ValidationContext,
        ):
            raise InvalidValidationContextError(
                "Expected ValidationContext."
            )

        logger.info("Starting output validation.")

        validation_results = self._run_validators(context)

        policy = self._policy_engine.evaluate(
            validation_results
        )

        risk = self._risk_engine.assess(
            validation_results
        )

        original_response = context.llm_response

        final_response = original_response

        if policy.should_sanitize:
            final_response = (
                self._sanitizer.sanitize(
                    final_response,
                    validation_results,
                )
            )

        decision = ValidationDecision(
            approved=policy.allowed,
            original_response=original_response,
            final_response=final_response,
            validation_results=validation_results,
            policy_evaluation=policy,
            risk_assessment=risk,
            request_id=context.metadata.get(
                "request_id",
                "",
            ),
        )

        logger.info(
            "Output validation completed. "
            "Approved=%s Risk=%s",
            decision.approved,
            decision.risk_assessment.risk_level.value,
        )

        return decision

    def _run_validators(
        self,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        """
        Execute every validator.
        """
        results: list[ValidationResult] = []

        for validator in self._validators:
            logger.debug(
                "Executing validator '%s'.",
                validator.name,
            )

            try:
                result = validator.validate(context)
            except Exception as exc:
                logger.exception(
                    "Validator '%s' failed during execution.",
                    validator.name,
                )
                raise ValidatorExecutionError(
                    f"Validator '{validator.name}' failed during execution: {exc}"
                ) from exc

            if not isinstance(
                result,
                ValidationResult,
            ):
                raise InvalidValidationResultError(
                    f"Validator '{validator.name}' "
                    f"returned an invalid ValidationResult."
                )

            results.append(result)

        return results
