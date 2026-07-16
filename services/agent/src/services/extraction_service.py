"""Extraction service for extracting memory facts from conversations.

Uses heuristic (regex-based, inline, no-cost) extraction.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from llamatrade_db.models import MemoryFactCategory

from src.services.memory_service import ExtractedFact

logger = logging.getLogger(__name__)


# Extraction Patterns

# Patterns are tuples of (regex, category, confidence_modifier)
# confidence_modifier adjusts base confidence (0.7 for heuristic)

PREFERENCE_PATTERNS: list[tuple[str, str, float]] = [
    # User preferences - general
    (
        r"(?:I\s+(?:prefer|like|want|love)|my preference is)\s+(.+?)(?:\.|,|$)",
        MemoryFactCategory.USER_PREFERENCE,
        0.0,
    ),
    (
        r"(?:I'm a fan of|I really like|I tend to prefer)\s+(.+?)(?:\.|,|$)",
        MemoryFactCategory.USER_PREFERENCE,
        0.0,
    ),
    # Investor/trader identity
    (
        r"(?:I'm|I am)\s+(?:a|an)\s+(.+?(?:investor|trader))",
        MemoryFactCategory.TRADING_BEHAVIOR,
        0.1,
    ),
    (
        r"(?:I consider myself|I'd say I'm)\s+(?:a|an)\s+(.+?)(?:\.|,|$)",
        MemoryFactCategory.TRADING_BEHAVIOR,
        0.0,
    ),
    # Investment goals
    (
        r"(?:my goal is|I'm (?:trying|looking) to|I want to)\s+(.+?)(?:\.|,|$)",
        MemoryFactCategory.INVESTMENT_GOAL,
        0.0,
    ),
    (
        r"(?:I'm (?:saving|investing) for|my (?:investment )?objective is)\s+(.+?)(?:\.|,|$)",
        MemoryFactCategory.INVESTMENT_GOAL,
        0.1,
    ),
    (
        r"(?:retirement|retire) (?:in|within)\s+(\d+\s+years?)",
        MemoryFactCategory.INVESTMENT_GOAL,
        0.15,
    ),
    # Asset preferences (likes)
    (
        r"(?:I\s+(?:like|prefer|favor))\s+(?:investing in\s+)?(.+?)(?:\s+(?:stocks|ETFs|sector))",
        MemoryFactCategory.ASSET_PREFERENCE,
        0.0,
    ),
    (
        r"(?:I'm (?:interested|bullish) (?:in|on))\s+(.+?)(?:\.|,|$)",
        MemoryFactCategory.ASSET_PREFERENCE,
        0.0,
    ),
    # Asset preferences (dislikes)
    (
        r"(?:I\s+(?:don't|do not)\s+(?:want|like)|avoid|stay away from)\s+(.+?)(?:\.|,|$)",
        MemoryFactCategory.ASSET_PREFERENCE,
        0.0,
    ),
    (
        r"(?:I'm (?:not interested|bearish) (?:in|on))\s+(.+?)(?:\.|,|$)",
        MemoryFactCategory.ASSET_PREFERENCE,
        0.0,
    ),
    # Risk tolerance - explicit
    (
        r"(?:my\s+)?risk\s+tolerance\s+(?:is|:)\s*(\w+)",
        MemoryFactCategory.RISK_TOLERANCE,
        0.15,
    ),
    (
        r"(?:I\s+(?:have|am)\s+(?:a\s+)?)?(\w+)\s+risk\s+(?:tolerance|appetite)",
        MemoryFactCategory.RISK_TOLERANCE,
        0.1,
    ),
    (
        r"(?:I'm\s+(?:a\s+)?|I\s+consider\s+myself\s+)?(conservative|moderate|aggressive)\s+(?:investor|with\s+my)",
        MemoryFactCategory.RISK_TOLERANCE,
        0.15,
    ),
    # Risk tolerance - drawdown
    (
        r"(?:I\s+(?:can|could)\s+(?:handle|tolerate)|max(?:imum)?\s+)?(?:drawdown|loss)\s+(?:of\s+)?(\d+%?)",
        MemoryFactCategory.RISK_TOLERANCE,
        0.1,
    ),
    # Trading behavior
    (
        r"(?:I\s+(?:usually|typically|normally)|I\s+like\s+to)\s+rebalance\s+(\w+)",
        MemoryFactCategory.TRADING_BEHAVIOR,
        0.1,
    ),
    (
        r"(?:I\s+(?:hold|keep)\s+positions\s+for)\s+(.+?)(?:\.|,|$)",
        MemoryFactCategory.TRADING_BEHAVIOR,
        0.0,
    ),
    (
        r"(?:my\s+(?:investment\s+)?horizon\s+is|I'm\s+(?:a\s+)?(?:long|short)\s+term)",
        MemoryFactCategory.TRADING_BEHAVIOR,
        0.1,
    ),
    # Strategy decisions
    (
        r"(?:I(?:'ll|\s+will)\s+go\s+with|let's\s+use|I\s+choose)\s+(.+?)(?:\.|,|$)",
        MemoryFactCategory.STRATEGY_DECISION,
        0.0,
    ),
    (
        r"(?:I\s+(?:decided|want)\s+to\s+use|I'm\s+going\s+with)\s+(?:the\s+)?(.+?)(?:\s+strategy|\.|,|$)",
        MemoryFactCategory.STRATEGY_DECISION,
        0.0,
    ),
    # Feedback
    (
        r"(?:I\s+(?:like|love|prefer)\s+(?:this|that|the))\s+(.+?)(?:\.|,|$)",
        MemoryFactCategory.FEEDBACK,
        -0.1,  # Lower confidence for feedback
    ),
    (
        r"(?:that(?:'s|\s+is)\s+(?:exactly|perfect|great|what\s+I\s+(?:want|need)))",
        MemoryFactCategory.FEEDBACK,
        -0.1,
    ),
]

# Additional patterns for specific contexts
ALLOCATION_PATTERNS: list[tuple[str, str, float]] = [
    (
        r"(\d+)[/:](\d+)\s+(?:allocation|split)",
        MemoryFactCategory.STRATEGY_DECISION,
        0.1,
    ),
    (
        r"(\d+)%\s+(?:stocks?|equit(?:y|ies)).*?(\d+)%\s+(?:bonds?|fixed\s+income)",
        MemoryFactCategory.STRATEGY_DECISION,
        0.15,
    ),
]

# Risk level keywords for extraction
RISK_KEYWORDS = {
    "conservative": "conservative risk tolerance",
    "low": "low risk tolerance",
    "moderate": "moderate risk tolerance",
    "medium": "moderate risk tolerance",
    "balanced": "balanced/moderate risk tolerance",
    "aggressive": "aggressive risk tolerance",
    "high": "high risk tolerance",
}


# Heuristic Extractor


@dataclass
class ExtractionContext:
    """Context for extraction to improve accuracy."""

    current_page: str | None = None
    strategy_name: str | None = None
    recent_topics: list[str] | None = None


def extract_facts_heuristic(
    user_message: str,
    context: ExtractionContext | None = None,
) -> list[ExtractedFact]:
    """Extract facts from user message using heuristic patterns.

    This is Tier 1 extraction: fast, no API cost, moderate accuracy.

    Args:
        user_message: The user's message content
        context: Optional extraction context

    Returns:
        List of extracted facts
    """
    if not user_message or len(user_message) < 10:
        return []

    facts: list[ExtractedFact] = []
    seen_content: set[str] = set()  # Avoid duplicate extractions

    # Normalize message for matching
    message_lower = user_message.lower().strip()

    # Apply preference patterns
    for pattern, category, confidence_mod in PREFERENCE_PATTERNS:
        matches = re.finditer(pattern, user_message, re.IGNORECASE)
        for match in matches:
            content = match.group(1) if match.lastindex else match.group(0)
            content = _clean_extracted_content(content)

            if not content or content.lower() in seen_content:
                continue

            if len(content) < 3 or len(content) > 200:
                continue

            seen_content.add(content.lower())
            facts.append(
                ExtractedFact(
                    category=category,
                    content=content,
                    confidence=0.7 + confidence_mod,
                    extraction_method="heuristic",
                )
            )

    # Apply allocation patterns
    for pattern, category, confidence_mod in ALLOCATION_PATTERNS:
        matches = re.finditer(pattern, user_message, re.IGNORECASE)
        for match in matches:
            # Format allocation as readable string
            if match.lastindex and match.lastindex >= 2:
                content = f"{match.group(1)}/{match.group(2)} allocation"
            else:
                content = match.group(0)

            content = _clean_extracted_content(content)
            if content and content.lower() not in seen_content:
                seen_content.add(content.lower())
                facts.append(
                    ExtractedFact(
                        category=category,
                        content=content,
                        confidence=0.7 + confidence_mod,
                        extraction_method="heuristic",
                    )
                )

    # Extract explicit risk level mentions
    for keyword, risk_text in RISK_KEYWORDS.items():
        if keyword in message_lower:
            # Check if it's in a risk context
            risk_patterns = [
                f"{keyword} risk",
                f"risk.*{keyword}",
                f"{keyword}.*investor",
                f"i'm {keyword}",
                f"i am {keyword}",
            ]
            for rp in risk_patterns:
                if re.search(rp, message_lower):
                    if risk_text not in seen_content:
                        seen_content.add(risk_text)
                        facts.append(
                            ExtractedFact(
                                category=MemoryFactCategory.RISK_TOLERANCE,
                                content=risk_text,
                                confidence=0.85,
                                extraction_method="heuristic",
                            )
                        )
                    break

    # Post-process: enhance confidence based on context
    if context:
        for fact in facts:
            # Boost confidence for strategy decisions when on strategy page
            if (
                context.current_page == "strategy_editor"
                and fact.category == MemoryFactCategory.STRATEGY_DECISION
            ):
                fact.confidence = min(fact.confidence + 0.1, 1.0)

    logger.debug("Extracted %d facts via heuristic from message", len(facts))
    return facts


def _clean_extracted_content(content: str) -> str:
    """Clean extracted content string.

    Args:
        content: Raw extracted content

    Returns:
        Cleaned content
    """
    if not content:
        return ""

    # Strip whitespace
    content = content.strip()

    # Remove trailing punctuation
    content = content.rstrip(".,;:!?")

    # Remove leading articles for cleaner storage
    content = re.sub(r"^(?:a|an|the)\s+", "", content, flags=re.IGNORECASE)

    # Normalize whitespace
    content = re.sub(r"\s+", " ", content)

    return content
