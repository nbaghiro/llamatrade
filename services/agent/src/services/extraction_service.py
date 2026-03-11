"""Extraction service for extracting memory facts from conversations.

This service implements a two-tier extraction system:
- Tier 1: Heuristic (regex-based, inline, no cost)
- Tier 2: LLM (background, batched, uses Claude Haiku)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from llamatrade_db.models import MemoryFactCategory

from src.services.memory_service import ExtractedFact

logger = logging.getLogger(__name__)


# =============================================================================
# Extraction Patterns
# =============================================================================

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


# =============================================================================
# Heuristic Extractor
# =============================================================================


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


# =============================================================================
# LLM Extractor (Tier 2)
# =============================================================================

LLM_EXTRACTION_PROMPT = """Extract relevant facts from this conversation that would be useful to remember about the user.

Focus on:
1. Risk tolerance and investment preferences
2. Investment goals and time horizons
3. Asset/sector preferences (likes and dislikes)
4. Trading behavior and habits
5. Specific decisions they've made

Return a JSON array of facts. Each fact should have:
- "category": one of ["user_preference", "risk_tolerance", "investment_goal", "asset_preference", "strategy_decision", "trading_behavior", "feedback"]
- "content": the extracted fact as a clear, concise statement
- "confidence": confidence level from 0.5 to 1.0

Only extract facts that are clearly stated or strongly implied. Do not infer beyond what's explicitly said.
If no relevant facts are found, return an empty array [].

Conversation:
{messages}

Return only valid JSON, no other text."""


async def extract_facts_llm(
    messages: list[dict[str, str]],
    llm_client: Any,
) -> list[ExtractedFact]:
    """Extract facts from conversation using LLM.

    This is Tier 2 extraction: higher accuracy but has API cost.
    Should be run in background and batched.

    Args:
        messages: List of message dicts with "role" and "content"
        llm_client: LLM client for API calls

    Returns:
        List of extracted facts
    """
    import json

    if not messages:
        return []

    # Format messages for prompt
    formatted = "\n".join(f"{msg['role'].upper()}: {msg['content']}" for msg in messages)

    prompt = LLM_EXTRACTION_PROMPT.format(messages=formatted)

    try:
        # Call LLM (Haiku for cost efficiency)
        response = await llm_client.complete(
            prompt=prompt,
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            temperature=0.0,
        )

        # Parse response
        content = response.content.strip()

        # Handle potential markdown code blocks
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)

        parsed = json.loads(content)

        if not isinstance(parsed, list):
            logger.warning("LLM extraction returned non-list: %s", type(parsed))
            return []

        facts: list[ExtractedFact] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue

            category = item.get("category", "")
            content = item.get("content", "")
            confidence = item.get("confidence", 0.85)

            # Validate category
            valid_categories = {c.value for c in MemoryFactCategory}
            if category not in valid_categories:
                continue

            if not content or len(content) < 5:
                continue

            facts.append(
                ExtractedFact(
                    category=category,
                    content=content,
                    confidence=min(max(float(confidence), 0.5), 1.0),
                    extraction_method="llm",
                )
            )

        logger.info("Extracted %d facts via LLM", len(facts))
        return facts

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse LLM extraction response: %s", e)
        return []
    except Exception as e:
        logger.exception("LLM extraction failed: %s", e)
        return []


# =============================================================================
# Combined Extraction
# =============================================================================


async def extract_facts_combined(
    user_message: str,
    conversation_history: list[dict[str, str]] | None = None,
    context: ExtractionContext | None = None,
    llm_client: Any | None = None,
    use_llm: bool = False,
) -> list[ExtractedFact]:
    """Extract facts using combined heuristic + optional LLM extraction.

    Args:
        user_message: Current user message
        conversation_history: Optional full conversation for LLM
        context: Extraction context
        llm_client: LLM client for Tier 2 extraction
        use_llm: Whether to use LLM extraction

    Returns:
        Combined list of extracted facts
    """
    # Always run heuristic extraction
    facts = extract_facts_heuristic(user_message, context)

    # Optionally run LLM extraction
    if use_llm and llm_client and conversation_history:
        llm_facts = await extract_facts_llm(conversation_history, llm_client)

        # Merge, preferring LLM facts when they overlap
        existing_content = {f.content.lower() for f in facts}
        for llm_fact in llm_facts:
            if llm_fact.content.lower() not in existing_content:
                facts.append(llm_fact)

    return facts
