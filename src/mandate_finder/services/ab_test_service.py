"""A/B Testing statistical engine.

Provides:
  - Chi-squared test for open rate comparison
  - Mann-Whitney U test for reply rate comparison
  - Bayesian bandit (Thompson sampling) for multi-armed bandit
  - Auto-promotion when p < significance_threshold vs control
"""
from __future__ import annotations

import math
import random
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.models.ab_testing import ABTest, MessageVariant, ReplyEvent


# ---------------------------------------------------------------------------
# Pure-Python statistical helpers (no scipy dependency)
# ---------------------------------------------------------------------------

def _chi_square_p_value(observed: list[list[float]]) -> float:
    """Pearson chi-squared test of independence.

    Returns the p-value (two-sided).  Only implemented for 2×k tables;
    we use the chi-squared distribution with (rows-1)*(cols-1) degrees
    of freedom.
    """
    rows = len(observed)
    cols = len(observed[0])
    dof = (rows - 1) * (cols - 1)
    if dof < 1:
        return 1.0

    total = sum(sum(row) for row in observed)
    if total == 0:
        return 1.0

    # Row / column totals
    row_totals = [sum(row) for row in observed]
    col_totals = [sum(observed[r][c] for r in range(rows)) for c in range(cols)]

    chi2 = 0.0
    for r in range(rows):
        for c in range(cols):
            expected = row_totals[r] * col_totals[c] / total
            if expected > 0:
                chi2 += (observed[r][c] - expected) ** 2 / expected

    return 1.0 - _chi_square_cdf(chi2, dof)


def _chi_square_cdf(x: float, k: int) -> float:
    """CDF of the chi-squared distribution with k degrees of freedom."""
    if x <= 0:
        return 0.0
    return _lower_incomplete_gamma(k / 2.0, x / 2.0) / math.gamma(k / 2.0)


def _lower_incomplete_gamma(a: float, x: float, eps: float = 1e-12) -> float:
    """Series expansion of the lower incomplete gamma function γ(a, x)."""
    if x == 0:
        return 0.0
    s = 1.0 / a
    t = 1.0 / a
    for n in range(1, 200):
        t *= x / (a + n)
        s += t
        if abs(t) < eps:
            break
    return s * math.exp(-x + a * math.log(x))


def _mann_whitney_p_value(x: list[float], y: list[float]) -> float:
    """Two-sided Mann-Whitney U test p-value (normal approximation).

    Uses tie correction.  Returns p-value for the null that both
    samples come from the same distribution.
    """
    nx, ny = len(x), len(y)
    if nx == 0 or ny == 0:
        return 1.0

    combined = [(val, 0) for val in x] + [(val, 1) for val in y]
    combined.sort(key=lambda t: t[0])

    # Rank with tie correction
    n = nx + ny
    ranks = [0.0] * n
    i = 0
    tie_adjustment = 0.0
    while i < n:
        j = i
        while j < n and combined[j][0] == combined[i][0]:
            j += 1
        rank = (i + j + 1) / 2.0  # average rank for ties
        for k in range(i, j):
            ranks[k] = rank
        tie_len = j - i
        tie_adjustment += tie_len**3 - tie_len
        i = j

    r1 = sum(ranks[k] for k in range(n) if combined[k][1] == 0)
    u1 = r1 - nx * (nx + 1) / 2.0
    u2 = nx * ny - u1
    u = min(u1, u2)

    mu = nx * ny / 2.0
    denom = (nx * ny * (n + 1) - tie_adjustment / (n - 1)) / 12.0
    if denom <= 0:
        return 1.0
    sigma = math.sqrt(denom)
    if sigma == 0:
        return 1.0
    z = (u - mu) / sigma
    # Two-sided p-value from normal CDF
    p = 2.0 * _normal_cdf(-abs(z))
    return min(p, 1.0)


def _normal_cdf(x: float) -> float:
    """Standard normal CDF using math.erfc (machine precision)."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


# ---------------------------------------------------------------------------
# Thompson sampling (Bayesian bandit)
# ---------------------------------------------------------------------------

def thompson_sample(variants: list[tuple[UUID, int, int]], rng: random.Random | None = None) -> UUID:
    """Select a variant using Thompson sampling.

    Each tuple is (variant_id, successes, failures).
    Returns the ID of the selected variant.
    """
    rng = rng or random.Random()
    best_beta = -1.0
    best_id = variants[0][0]
    for vid, success, failure in variants:
        # Sample from Beta(1+success, 1+failure)
        alpha = 1.0 + success
        beta = 1.0 + failure
        sample = rng.betavariate(alpha, beta)
        if sample > best_beta:
            best_beta = sample
            best_id = vid
    return best_id


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class ABTestService:
    """Statistical engine for A/B testing."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- Variant CRUD -------------------------------------------------------

    async def create_variant(self, campaign_id: UUID, subject: str, body: str,
                             cta: str | None = None,
                             personalization_level: str = "low",
                             is_control: bool = False) -> MessageVariant:
        variant = MessageVariant(
            campaign_id=campaign_id,
            subject=subject,
            body=body,
            cta=cta,
            personalization_level=personalization_level,
            is_control=is_control,
        )
        self.db.add(variant)
        await self.db.commit()
        await self.db.refresh(variant)
        return variant

    async def get_variant(self, variant_id: UUID) -> MessageVariant | None:
        return await self.db.get(MessageVariant, variant_id)

    async def list_variants(self, campaign_id: UUID) -> Sequence[MessageVariant]:
        result = await self.db.execute(
            select(MessageVariant).where(MessageVariant.campaign_id == campaign_id)
            .order_by(MessageVariant.created_at)
        )
        return result.scalars().all()

    async def update_variant(self, variant_id: UUID, **kwargs: Any) -> MessageVariant | None:
        variant = await self.db.get(MessageVariant, variant_id)
        if not variant:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(variant, key):
                setattr(variant, key, value)
        await self.db.commit()
        await self.db.refresh(variant)
        return variant

    async def delete_variant(self, variant_id: UUID) -> bool:
        variant = await self.db.get(MessageVariant, variant_id)
        if not variant:
            return False
        await self.db.delete(variant)
        await self.db.commit()
        return True

    # -- ABTest CRUD --------------------------------------------------------

    async def create_test(self, campaign_id: UUID, name: str,
                          control_variant_id: UUID | None = None,
                          significance_threshold: float = 0.05) -> ABTest:
        test = ABTest(
            campaign_id=campaign_id,
            name=name,
            control_variant_id=control_variant_id,
            significance_threshold=significance_threshold,
        )
        self.db.add(test)
        await self.db.commit()
        await self.db.refresh(test)
        return test

    async def get_test(self, test_id: UUID) -> ABTest | None:
        return await self.db.get(ABTest, test_id)

    async def list_tests(self, campaign_id: UUID) -> Sequence[ABTest]:
        result = await self.db.execute(
            select(ABTest).where(ABTest.campaign_id == campaign_id)
            .order_by(ABTest.started_at.desc())
        )
        return result.scalars().all()

    async def update_test(self, test_id: UUID, **kwargs: Any) -> ABTest | None:
        test = await self.db.get(ABTest, test_id)
        if not test:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(test, key):
                setattr(test, key, value)
        await self.db.commit()
        await self.db.refresh(test)
        return test

    # -- Reply events -------------------------------------------------------

    async def record_reply(self, campaign_id: UUID, channel: str,
                           message_id: UUID | None = None,
                           handled_by_human: bool = False,
                           raw_data: dict[str, object] | None = None) -> ReplyEvent:
        event = ReplyEvent(
            campaign_id=campaign_id,
            message_id=message_id,
            channel=channel,
            handled_by_human=handled_by_human,
            raw_data=raw_data,
        )
        self.db.add(event)
        # Increment reply_count on the message variant if message_id given
        if message_id:
            await self.db.execute(
                update(MessageVariant)
                .where(MessageVariant.id == message_id)
                .values(reply_count=MessageVariant.reply_count + 1)
            )
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def list_replies(self, campaign_id: UUID,
                           limit: int = 100) -> Sequence[ReplyEvent]:
        result = await self.db.execute(
            select(ReplyEvent).where(ReplyEvent.campaign_id == campaign_id)
            .order_by(ReplyEvent.detected_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    # -- Statistical computations -------------------------------------------

    async def compute_stats(self, test_id: UUID) -> dict[str, Any]:
        """Compute per-variant statistics and p-values vs control."""
        test = await self.db.get(ABTest, test_id)
        if not test:
            return {"error": "Test not found"}

        variants = await self.list_variants(test.campaign_id)
        if not variants:
            return {"error": "No variants found"}

        # Identify control
        control = None
        if test.control_variant_id:
            control = await self.db.get(MessageVariant, test.control_variant_id)
        if not control:
            # Use the first variant marked is_control, or first variant
            control = next((v for v in variants if v.is_control), variants[0])

        stats: list[dict[str, Any]] = []
        winner_id: UUID | None = None
        best_p = 1.0

        for v in variants:
            n = v.send_count
            open_rate = v.open_count / n if n > 0 else 0.0
            reply_rate = v.reply_count / n if n > 0 else 0.0
            meeting_rate = v.meeting_count / n if n > 0 else 0.0

            p_value: float | None = None
            if v.id != control.id and n > 0 and control.send_count > 0:
                # Chi-squared test for open rate
                obs = [[v.open_count, v.send_count - v.open_count],
                       [control.open_count, control.send_count - control.open_count]]
                p_open = _chi_square_p_value(obs)

                # Mann-Whitney U test on reply rate (binary: has_replied)
                v_replies = [1.0] * v.reply_count + [0.0] * (v.send_count - v.reply_count)
                c_replies = [1.0] * control.reply_count + [0.0] * (control.send_count - control.reply_count)
                p_reply = _mann_whitney_p_value(v_replies, c_replies)

                # Use the more significant p-value
                p_value = min(p_open, p_reply)

                if p_value is not None and p_value < best_p:
                    best_p = p_value
                    winner_id = v.id

            stats.append({
                "variant_id": v.id,
                "label": f"Variant {v.personalization_level}" if not v.is_control else "Control",
                "n": n,
                "open_rate": round(open_rate, 4),
                "reply_rate": round(reply_rate, 4),
                "meeting_rate": round(meeting_rate, 4),
                "is_control": v.id == control.id,
                "is_winner": False,
                "p_value_vs_control": p_value,
            })

        # Check if best_p is below significance threshold
        is_significant = best_p < test.significance_threshold

        if is_significant and winner_id:
            for s in stats:
                if s["variant_id"] == winner_id:
                    s["is_winner"] = True
                    break
            # Auto-update winning variant
            test.winning_variant_id = winner_id
            await self.db.commit()
            await self.db.refresh(test)

        return {
            "test_id": test_id,
            "campaign_id": test.campaign_id,
            "status": test.status,
            "significance_threshold": test.significance_threshold,
            "best_p_value": best_p,
            "is_significant": is_significant,
            "winner_id": winner_id,
            "stats": stats,
        }

    async def auto_promote(self, test_id: UUID) -> dict[str, Any]:
        """Evaluate and auto-promote the winning variant if p < threshold."""
        test = await self.db.get(ABTest, test_id)
        if not test:
            return {"promoted": False, "reason": "Test not found"}

        if test.status == "completed":
            return {"promoted": False, "reason": "Test already completed"}

        result = await self.compute_stats(test_id)
        if "error" in result:
            return {"promoted": False, "reason": result["error"]}

        if result.get("is_significant") and result.get("winner_id"):
            test.status = "completed"
            test.ended_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(test)
            return {
                "promoted": True,
                "winner_id": result["winner_id"],
                "best_p_value": result["best_p_value"],
                "stats": result["stats"],
            }

        return {
            "promoted": False,
            "reason": "Significance threshold not yet reached",
            "best_p_value": result.get("best_p_value"),
        }

    async def get_dashboard(self, test_id: UUID) -> dict[str, Any]:
        """Build a full performance dashboard for the test."""
        test = await self.db.get(ABTest, test_id)
        if not test:
            return {"error": "Test not found"}

        result = await self.compute_stats(test_id)

        variants_list = result.get("stats", [])
        winning = next((v for v in variants_list if v.get("is_winner")), None)

        # Generate recommendation
        recommendation: str | None = None
        if winning:
            recommendation = (
                f"Variant '{winning['label']}' is statistically significant "
                f"(p={winning['p_value_vs_control']:.4f}, threshold={test.significance_threshold}). "
                "Consider promoting it to production."
            )
        elif result.get("is_significant") is False and len(variants_list) > 1:
            recommendation = (
                "No variant has reached statistical significance yet. "
                "Continue collecting data."
            )
        else:
            recommendation = "Insufficient data to make a recommendation."

        return {
            "test": {
                "id": test.id,
                "campaign_id": test.campaign_id,
                "name": test.name,
                "control_variant_id": test.control_variant_id,
                "winning_variant_id": test.winning_variant_id,
                "significance_threshold": test.significance_threshold,
                "status": test.status,
                "started_at": test.started_at,
                "ended_at": test.ended_at,
            },
            "variants": variants_list,
            "winning_variant": winning,
            "recommendation": recommendation,
        }

    async def promote_variant(self, test_id: UUID,
                              variant_id: UUID) -> dict[str, Any]:
        """Manually promote a specific variant as winner."""
        test = await self.db.get(ABTest, test_id)
        if not test:
            return {"promoted": False, "reason": "Test not found"}

        variant = await self.db.get(MessageVariant, variant_id)
        if not variant:
            return {"promoted": False, "reason": "Variant not found"}

        if variant.campaign_id != test.campaign_id:
            return {"promoted": False, "reason": "Variant does not belong to this test's campaign"}

        test.winning_variant_id = variant_id
        test.status = "completed"
        test.ended_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(test)

        return {"promoted": True, "winner_id": variant_id, "test_id": test_id}

    async def export_report(self, test_id: UUID) -> dict[str, Any]:
        """Generate an export report with all variant data and p-values."""
        test = await self.db.get(ABTest, test_id)
        if not test:
            return {"error": "Test not found"}

        result = await self.compute_stats(test_id)
        stats = result.get("stats", [])
        total_n = sum(s["n"] for s in stats)

        return {
            "test_name": test.name,
            "campaign_id": test.campaign_id,
            "variants": [
                {
                    "label": s["label"],
                    "n": s["n"],
                    "open_rate": s["open_rate"],
                    "reply_rate": s["reply_rate"],
                    "meeting_rate": s["meeting_rate"],
                    "is_control": s["is_control"],
                    "is_winner": s["is_winner"],
                    "p_value_vs_control": s["p_value_vs_control"],
                }
                for s in stats
            ],
            "total_n": total_n,
            "winner_id": result.get("winner_id"),
            "p_value_threshold": test.significance_threshold,
            "generated_at": datetime.now(timezone.utc),
        }

    # -- Bayesian bandit (Thompson sampling) --------------------------------

    async def bandit_select(self, campaign_id: UUID) -> UUID | None:
        """Select the best variant using Thompson sampling."""
        variants = await self.list_variants(campaign_id)
        if not variants:
            return None
        if len(variants) == 1:
            return variants[0].id

        arms = [
            (v.id, v.open_count + v.reply_count,
             v.send_count - v.open_count - v.reply_count)
            for v in variants
        ]
        return thompson_sample(arms)
