"""
GSoC Module B: Noise/Relevance Filter - Two-Stage Filtering System

Filters security knowledge from noise using:
1. Regex-based filtering (fast, eliminates common patterns)
2. LLM-based relevance checking (semantic, highly accurate)

Features:
- Production-ready regex patterns corpus
- LLM API integration (Gemini Flash / GPT-4o-mini)
- Confidence scoring and thresholding
- Comprehensive logging and metrics
"""

import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

logger = logging.getLogger(__name__)


class FilterReason(Enum):
    """Reasons for filtering content."""
    LOCKFILE = "lockfile"
    CI_CONFIG = "ci_config"
    FORMATTING = "formatting"
    ADMIN = "admin"
    TEST_OUTPUT = "test_output"
    BUILD_ARTIFACT = "build_artifact"
    LINTING = "linting"
    TYPO_FIX = "typo_fix"
    SECURITY_KNOWLEDGE = "security_knowledge"  # Not filtered
    UNKNOWN = "unknown"


class NoiseFilter:
    """Two-stage filter: Regex + LLM for security content relevance."""

    # Stage 1: Regex patterns that are almost certainly noise
    NOISE_REGEX_PATTERNS = {
        "lockfile": [
            r"package-lock\.json",
            r"yarn\.lock",
            r"Gemfile\.lock",
            r"poetry\.lock",
            r"requirements\.lock",
            r"\.lock$",
        ],
        "ci_config": [
            r"\.github/workflows",
            r"\.gitlab-ci\.yml",
            r"\.circleci",
            r"Jenkinsfile",
            r"\.travis\.yml",
            r"azure-pipelines\.yml",
        ],
        "admin_files": [
            r"CNAME$",
            r"_config\.yml",
            r"_redirects$",
            r"robots\.txt",
            r"sitemap\.xml",
            r"\.gitignore$",
            r"\.gitattributes$",
        ],
        "linting": [
            r"prettier",
            r"eslint",
            r"black formatting",
            r"whitespace fix",
            r"trailing comma",
            r"format: fix",
            r"lint:",
            r"Bump [a-z-]+ from .* to .*",
        ],
        "version_bumps": [
            r"Bump dependencies",
            r"Update dependency",
            r"Deprecate",
            r"Remove deprecated",
        ],
        "tests": [
            r"test_.*\.py",
            r"__pycache__",
            r"\.pytest_cache",
            r"coverage\.xml",
        ],
    }

    # Stage 2: Keywords indicating security knowledge
    SECURITY_KEYWORDS = [
        "security",
        "vulnerability",
        "cve",
        "threat",
        "risk",
        "exploit",
        "authentication",
        "authorization",
        "encryption",
        "crypto",
        "attack",
        "defense",
        "mitigation",
        "compliance",
        "owasp",
        "asvs",
        "control",
        "requirement",
        "validation",
        "injection",
        "xss",
        "csrf",
        "sql injection",
        "privilege escalation",
        "ssrf",
        "xml external",
        "deserialization",
        "race condition",
    ]

    def __init__(self, llm_client: Optional[Any] = None, confidence_threshold: float = 0.8):
        """
        Initialize the noise filter.

        Args:
            llm_client: Optional LLM client (Gemini/GPT-4o-mini)
            confidence_threshold: Confidence score above which content is kept (0-1)
        """
        self.llm_client = llm_client
        self.confidence_threshold = confidence_threshold
        self.metrics = {
            "total_processed": 0,
            "filtered_regex": 0,
            "filtered_llm": 0,
            "approved": 0,
            "llm_errors": 0,
        }

    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Compile regex patterns for efficiency."""
        compiled = {}
        for category, patterns in self.NOISE_REGEX_PATTERNS.items():
            compiled[category] = [re.compile(p, re.IGNORECASE) for p in patterns]
        return compiled

    def filter_stage_1_regex(
        self, content: str
    ) -> Tuple[bool, Optional[FilterReason], Optional[str]]:
        """
        Stage 1: Quick regex-based filtering.

        Args:
            content: Content to filter

        Returns:
            Tuple of (is_noise, reason, matched_pattern)
        """
        patterns = self._compile_patterns()

        for category, compiled_patterns in patterns.items():
            for pattern in compiled_patterns:
                if pattern.search(content):
                    reason = FilterReason[category.upper()] if hasattr(
                        FilterReason, category.upper()
                    ) else FilterReason.UNKNOWN
                    return True, reason, pattern.pattern

        return False, None, None

    def _has_security_keywords(self, content: str) -> bool:
        """Check if content contains security-related keywords."""
        content_lower = content.lower()
        return any(keyword in content_lower for keyword in self.SECURITY_KEYWORDS)

    def filter_stage_2_llm(
        self, content: str
    ) -> Tuple[bool, float, Optional[str]]:
        """
        Stage 2: LLM-based semantic relevance checking.

        Args:
            content: Content to evaluate

        Returns:
            Tuple of (is_security_knowledge, confidence_score, reasoning)
        """
        if not self.llm_client:
            # Fallback: Use keyword matching if no LLM available
            has_keywords = self._has_security_keywords(content)
            confidence = 0.7 if has_keywords else 0.3
            return has_keywords, confidence, "Keyword-based fallback"

        try:
            # Prepare prompt for LLM
            prompt = self._build_llm_prompt(content)

            # Call LLM service
            response = self.llm_client.evaluate_relevance(prompt)

            # Parse response
            is_relevant = response.get("is_security_knowledge", False)
            confidence = min(1.0, max(0.0, response.get("confidence", 0.5)))

            return is_relevant, confidence, response.get("reasoning", "")

        except Exception as e:
            logger.error(f"LLM evaluation failed: {e}")
            self.metrics["llm_errors"] += 1

            # Fallback to keyword matching
            has_keywords = self._has_security_keywords(content)
            confidence = 0.5  # Lower confidence for fallback
            return has_keywords, confidence, f"LLM error, fallback: {str(e)}"

    def _build_llm_prompt(self, content: str) -> str:
        """Build prompt for LLM evaluation."""
        return f"""
Evaluate if this content is security knowledge (ASVS requirements, security best practices, 
threat models, vulnerabilities, etc.) vs noise (formatting, linting, version bumps, etc.).

Content to evaluate:
"{content}"

Respond with JSON:
{{
  "is_security_knowledge": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}
"""

    def filter(self, content: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Apply two-stage filter to content.

        Args:
            content: Content to filter

        Returns:
            Tuple of (is_valid_security_content, metadata_dict)
        """
        self.metrics["total_processed"] += 1

        # Stage 1: Regex filtering
        is_noise, regex_reason, pattern = self.filter_stage_1_regex(content)
        if is_noise:
            self.metrics["filtered_regex"] += 1
            return False, {
                "stage": 1,
                "reason": regex_reason.value if regex_reason else "unknown",
                "pattern": pattern,
                "confidence": 1.0,
            }

        # Stage 2: LLM filtering
        is_security, confidence, reasoning = self.filter_stage_2_llm(content)

        if is_security and confidence >= self.confidence_threshold:
            self.metrics["approved"] += 1
            return True, {
                "stage": 2,
                "reason": "approved_security_knowledge",
                "confidence": confidence,
                "reasoning": reasoning,
            }
        else:
            self.metrics["filtered_llm"] += 1
            return False, {
                "stage": 2,
                "reason": "low_relevance_score",
                "confidence": confidence,
                "reasoning": reasoning,
                "threshold": self.confidence_threshold,
            }

    def filter_batch(
        self, contents: List[str]
    ) -> List[Tuple[str, bool, Dict]]:
        """
        Filter multiple items efficiently.

        Args:
            contents: List of content strings

        Returns:
            List of (content, is_valid, metadata) tuples
        """
        results = []
        for content in contents:
            is_valid, metadata = self.filter(content)
            results.append((content, is_valid, metadata))
        return results

    def get_metrics(self) -> Dict[str, Any]:
        """Get filtering metrics."""
        total = self.metrics["total_processed"]
        if total == 0:
            return self.metrics

        return {
            **self.metrics,
            "approval_rate": (
                self.metrics["approved"] / total * 100 if total > 0 else 0
            ),
            "regex_filter_rate": (
                self.metrics["filtered_regex"] / total * 100 if total > 0 else 0
            ),
            "llm_filter_rate": (
                self.metrics["filtered_llm"] / total * 100 if total > 0 else 0
            ),
        }
