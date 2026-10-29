from __future__ import annotations

import logging

from .base import BaseValidator
from .tier2_judge import Tier2Judge
from .result_aggregator import ResultAggregator

from .support.models import (
    HallucinationConfig,
    HeuristicResult,
    SentenceDecision,
    SentenceEvidence,
    Tier2Decision,

)
from .support.models import (
    HallucinationAggregationResult,
)
from src.knowledge_base.models import RetrievedChunk

from src.output_validation_agent.models import (
    OutputCategory,
    ValidationContext,
    ValidationResult,
)


from ..exceptions import (
    ValidatorExecutionError,
)
from src.output_validation_agent.validators.support.scoring import (
    EscalationDecision,
    EscalationPolicy,
)
logger = logging.getLogger(__name__)


class HallucinationValidator(BaseValidator):
    """
    Production implementation of the Output Validation Agent.

    Responsibilities
    ----------------
    - Split the LLM response into sentences.
    - Execute Tier-1 validation.
    - Invoke Tier-2 only when necessary.
    - Aggregate sentence decisions.
    - Execute policy evaluation.
    - Execute risk assessment.
    - Return the final ValidationResult.

    This class is purely an orchestrator.
    """

    def __init__(
        self,
        splitter,
        semantic_scorer,
        lexical_scorer=None,
        keyword_scorer=None,
        entity_scorer=None,
        numeric_scorer=None,
        citation_scorer=None,
        support_score_aggregator=None,
        escalation_policy=None,
        tier2_judge: Tier2Judge | None = None,
        result_aggregator: ResultAggregator | None = None,
        config: HallucinationConfig | None = None,
    ) -> None:

        super().__init__()

        self._splitter = splitter

        self._semantic_scorer = semantic_scorer

        # Backwards compatible support for the older 'lexical_scorer'
        # used in unit tests. If a lexical_scorer is provided we will
        # use it directly; otherwise fall back to the individual
        # lexical scorers (keyword/entity/numeric/citation).
        self._lexical_scorer = lexical_scorer

        self._keyword_scorer = keyword_scorer
        self._entity_scorer = entity_scorer
        self._numeric_scorer = numeric_scorer
        self._citation_scorer = citation_scorer

        # SupportScoreAggregator compatibility: accept objects that
        # expose either `aggregate(results, config)` (new API) or
        # `compute(heuristic_results)` (legacy test fakes). Wrap legacy
        # objects so the rest of the code can always call `aggregate`.
        if support_score_aggregator is None:
            self._support_score_aggregator = None
        elif hasattr(support_score_aggregator, "aggregate"):
            self._support_score_aggregator = support_score_aggregator
        elif hasattr(support_score_aggregator, "compute"):
            class _Wrapper:
                def __init__(self, inner):
                    self._inner = inner

                def aggregate(self, results, cfg):
                    # Legacy `compute` returns a single support score.
                    return (self._inner.compute(results), False)

            self._support_score_aggregator = _Wrapper(
                support_score_aggregator
            )
        else:
            self._support_score_aggregator = support_score_aggregator

        if escalation_policy is None:
            self._escalation_policy = EscalationPolicy()
        else:
            self._escalation_policy = escalation_policy

        self._tier2_judge = tier2_judge

        self._result_aggregator = result_aggregator

        self._config = config

    ####################################################################
    # Public API
    ####################################################################

    CONTROLLED_NO_EVIDENCE_PHRASES = (
        "not available in the knowledge base",
        "couldn't find any relevant information",
        "could not find any relevant information",
        "lacks sufficient evidence",
        "no relevant information",
    )

    @classmethod
    def is_controlled_no_evidence_response(cls, response: str) -> bool:
        if not response:
            return False
        normalized = response.strip().lower()
        return any(phrase in normalized for phrase in cls.CONTROLLED_NO_EVIDENCE_PHRASES)

    def _validate(
    self,
    context: ValidationContext,
) -> ValidationResult:
        """
        Validate an LLM response against retrieved evidence.
        """

        logger.info(
            "Starting Hallucination Validator."
        )

        # No-context validation path: if no chunks survive, verify whether response is a controlled refusal
        if not context.retrieved_chunks and self.is_controlled_no_evidence_response(context.llm_response):
            logger.info(
                "Controlled no-evidence response detected — approving via no-context validation path."
            )
            return ValidationResult(
                validator_name=self.name,
                passed=True,
                category=OutputCategory.SAFE,
                score=0.0,
                reason="Controlled no-evidence response approved without retrieved context.",
                details={"no_context": True, "refusal_detected": True},
            )

        self._validate_inputs(context)

        sentences = self._splitter.split(
            context.llm_response
        )

        sentence_decisions: list[
            SentenceDecision
        ] = []

        for sentence in sentences:

            decision = self._process_sentence(
                sentence=sentence,
                evidence_chunks=context.retrieved_chunks,
                conversation_context=context.metadata.get(
                    "conversation_context"
                ),
            )

            sentence_decisions.append(decision)

        aggregation_result = (
            self._result_aggregator.aggregate(
                sentence_decisions
            )
        )

        return self._build_validation_result(
            aggregation_result
        )
        ####################################################################
    # Sentence Processing
    ####################################################################

    def _process_sentence(
    self,
    sentence: str,
    evidence_chunks: list[RetrievedChunk],
    conversation_context: str | None,
) -> SentenceDecision:
        """
        Process a single sentence through the complete
        validation pipeline.
        """

        logger.debug(
            "Processing sentence: %s",
            sentence,
        )

        evidence = self._build_sentence_evidence(
            sentence=sentence,
            evidence_chunks=evidence_chunks,
        )

        support_score, hard_rule = (
        self._support_score_aggregator.aggregate(
        evidence.heuristic_results,
        self._config,
    )
)

        decision = self._escalation_policy.decide(
            support_score=support_score,
            hard_rule_triggered=hard_rule,
            config=self._config,
        )

        logger.debug(
    "Tier-1 decision: %s",
    decision.value,
        )

        if decision == EscalationDecision.ACCEPT:

            return self._create_supported_decision(
                sentence,
                support_score,
                evidence,
            )

        if decision == EscalationDecision.REJECT:

            return self._create_unsupported_decision(
                sentence,
                support_score,
                evidence,
            )
        
        if not self._config.enable_tier2:

            return self._create_unsupported_decision(
                sentence,
                support_score,
                evidence,
            )
        evidence_text = [
                chunk.content
                for chunk in evidence_chunks
            ]
        tier2 = self._tier2_judge.evaluate(
            sentence=sentence,
            evidence_chunks=evidence_text,
            conversation_context=conversation_context,
        )

        return self._create_tier2_decision(
            sentence=sentence,
            support_score=support_score,
            evidence=evidence,
            tier2=tier2,
        )

    ####################################################################
    # Tier-1 Evidence
    ####################################################################

    def _build_sentence_evidence(
    self,
    sentence: str,
    evidence_chunks: list[RetrievedChunk],
) -> SentenceEvidence:
        """
        Execute all Tier-1 heuristic scorers.
        """

        heuristic_results: list[HeuristicResult] = []

        # Convert retrieved chunk objects to plain text before
        # passing them into heuristic scorers which expect
        # list[str].
        evidence_texts = [
            chunk.content
            for chunk in evidence_chunks
        ]

        def _normalize(res):
            # Scorer implementations historically returned either
            # a single HeuristicResult or a list of them. Normalize
            # to a list for consistent aggregation below.
            if res is None:
                return []
            if isinstance(res, list):
                return res
            return [res]

        # Semantic scorer (single result)
        heuristic_results.extend(
            _normalize(
                self._semantic_scorer.score(
                    sentence,
                    evidence_texts,
                )
            )
        )

        # Lexical scorers: support legacy 'lexical_scorer' or the
        # newer granular scorers (keyword/entity/numeric/citation).
        if self._lexical_scorer is not None:
            heuristic_results.extend(
                _normalize(
                    self._lexical_scorer.score(
                        sentence,
                        evidence_texts,
                    )
                )
            )
        else:
            if self._keyword_scorer is not None:
                heuristic_results.extend(
                    _normalize(
                        self._keyword_scorer.score(
                            sentence,
                            evidence_texts,
                        )
                    )
                )

            if self._entity_scorer is not None:
                heuristic_results.extend(
                    _normalize(
                        self._entity_scorer.score(
                            sentence,
                            evidence_texts,
                        )
                    )
                )

            if self._numeric_scorer is not None:
                heuristic_results.extend(
                    _normalize(
                        self._numeric_scorer.score(
                            sentence,
                            evidence_texts,
                        )
                    )
                )

            if self._citation_scorer is not None:
                heuristic_results.extend(
                    _normalize(
                        self._citation_scorer.score(
                            sentence,
                            evidence_texts,
                        )
                    )
                )

        return SentenceEvidence(
            sentence=sentence,
            heuristic_results=heuristic_results,
        )

    ####################################################################
    # Input Validation
    ####################################################################

    @staticmethod
    def _validate_inputs(
        context: ValidationContext,
    ) -> None:
        """
        Validate validator inputs.
        """

        if not isinstance(
            context,
            ValidationContext,
        ):
            raise ValidatorExecutionError(
                "Expected ValidationContext."
            )

        if not context.llm_response.strip():
            raise ValidatorExecutionError(
                "LLM response cannot be empty."
            )

        if not context.retrieved_chunks:
            raise ValidatorExecutionError(
                "Retrieved chunks cannot be empty."
            )
        ####################################################################
    # Decision Factory Methods
    ####################################################################

    @staticmethod
    def _create_supported_decision(
        sentence: str,
        support_score: float,
        evidence: SentenceEvidence,
    ) -> SentenceDecision:
        """
        Create a supported sentence decision using Tier-1 results.
        """

        return SentenceDecision(
            sentence=sentence,
            support_score=support_score,
            supported=True,
            used_tier2=False,
            tier2_decision=None,
            evidence=evidence,
        )

    @staticmethod
    def _create_unsupported_decision(
        sentence: str,
        support_score: float,
        evidence: SentenceEvidence,
    ) -> SentenceDecision:
        """
        Create an unsupported sentence decision using Tier-1 results.
        """

        return SentenceDecision(
            sentence=sentence,
            support_score=support_score,
            supported=False,
            used_tier2=False,
            tier2_decision=None,
            evidence=evidence,
        )

    @staticmethod
    def _create_tier2_decision(
        sentence: str,
        support_score: float,
        evidence: SentenceEvidence,
        tier2: Tier2Decision,
    ) -> SentenceDecision:
        """
        Create a sentence decision using the Tier-2 Judge output.
        """

        return SentenceDecision(
            sentence=sentence,
            support_score=support_score,
            supported=tier2.supported,
            used_tier2=True,
            tier2_decision=tier2,
            evidence=evidence,
        )
    def _build_validation_result(
    self,
    aggregation_result: HallucinationAggregationResult,
    ) -> ValidationResult:
        """
        Convert the hallucination aggregation result into the
        generic ValidationResult contract.
        """

        passed = not aggregation_result.hallucination_detected

        return ValidationResult(
            validator_name="HallucinationValidator",
            passed=passed,
            category=(
                OutputCategory.SAFE
                if passed
                else OutputCategory.HALLUCINATION
            ),
            score=1.0 - aggregation_result.average_support_score,
            reason=(
                "No hallucinations detected."
                if passed
                else "Unsupported claims detected."
            ),
            details={
                "average_support_score": aggregation_result.average_support_score,
                "confidence": aggregation_result.confidence,
                "supported_sentence_count": aggregation_result.supported_sentence_count,
                "unsupported_sentence_count": aggregation_result.unsupported_sentence_count,
                "tier2_usage_count": aggregation_result.tier2_usage_count,
                "sentence_decisions": aggregation_result.sentence_decisions,
                "metadata": aggregation_result.metadata,
            },
        )