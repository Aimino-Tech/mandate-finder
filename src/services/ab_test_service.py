import math
import random
from collections import Counter
from datetime import datetime

import numpy as np
from scipy import stats as scipy_stats

from src.config import settings
from src.models.ab_test import ABTest, ABTestVariant, MessageEvent, MessageVariant, SendTimeRecommendation


class ABTestService:
    def __init__(self, db_session):
        self.db = db_session

    def get_variant_performance(self, variant: MessageVariant) -> dict:
        events = self.db.query(MessageEvent).filter(MessageEvent.variant_id == variant.id).all()
        sent = sum(1 for e in events if e.sent_at)
        opened = sum(1 for e in events if e.opened_at)
        replied = sum(1 for e in events if e.replied_at)
        meetings = sum(1 for e in events if e.meeting_booked_at)

        return {
            "variant_id": variant.id,
            "variant_name": variant.name,
            "sent": sent,
            "opened": opened,
            "replied": replied,
            "meetings": meetings,
            "open_rate": opened / sent if sent else 0.0,
            "reply_rate": replied / sent if sent else 0.0,
            "meeting_rate": meetings / sent if sent else 0.0,
        }

    def run_chi_squared_opens(self, test: ABTest) -> dict:
        """Chi-squared test for open rate differences between variants."""
        results = []
        for av in test.variants:
            perf = self.get_variant_performance(av.variant)
            results.append(perf)

        if len(results) < 2:
            return {"p_value": 1.0, "significant": False, "error": "Need at least 2 variants"}

        control = next((r for r in results if r["variant_name"] == "control"), results[0])
        comparisons = []

        for variant in results:
            if variant["variant_id"] == control["variant_id"]:
                continue

            observed = np.array([
                [control["opened"], control["sent"] - control["opened"]],
                [variant["opened"], variant["sent"] - variant["opened"]],
            ])

            if np.any(observed.sum(axis=1) == 0):
                comparisons.append({
                    "variant_id": variant["variant_id"],
                    "variant_name": variant["variant_name"],
                    "p_value": 1.0,
                    "significant": False,
                    "error": "Insufficient sends",
                })
                continue

            chi2, p_value = scipy_stats.chisquare(f_obs=observed, axis=None)
            comparisons.append({
                "variant_id": variant["variant_id"],
                "variant_name": variant["variant_name"],
                "p_value": float(p_value),
                "significant": bool(p_value < test.significance_threshold),
            })

        any_significant = any(c["significant"] for c in comparisons)
        min_p = min(c["p_value"] for c in comparisons) if comparisons else 1.0

        return {"p_value": float(min_p), "significant": any_significant, "comparisons": comparisons}

    def run_mann_whitney_reply(self, test: ABTest) -> dict:
        """Mann-Whitney U test for reply rate differences between variants."""
        results = []
        for av in test.variants:
            perf = self.get_variant_performance(av.variant)
            results.append(perf)

        if len(results) < 2:
            return {"p_value": 1.0, "significant": False, "error": "Need at least 2 variants"}

        control = next((r for r in results if r["variant_name"] == "control"), results[0])
        comparisons = []

        for variant in results:
            if variant["variant_id"] == control["variant_id"]:
                continue

            events_control = self.db.query(MessageEvent).filter(
                MessageEvent.variant_id == control["variant_id"],
                MessageEvent.sent_at.isnot(None),
            ).all()

            events_variant = self.db.query(MessageEvent).filter(
                MessageEvent.variant_id == variant["variant_id"],
                MessageEvent.sent_at.isnot(None),
            ).all()

            control_reply_times = [
                (e.replied_at - e.sent_at).total_seconds()
                for e in events_control if e.replied_at and e.sent_at
            ] + [1.0] * (len(events_control) - sum(1 for e in events_control if e.replied_at))

            variant_reply_times = [
                (e.replied_at - e.sent_at).total_seconds()
                for e in events_variant if e.replied_at and e.sent_at
            ] + [1.0] * (len(events_variant) - sum(1 for e in events_variant if e.replied_at))

            if len(control_reply_times) < 2 or len(variant_reply_times) < 2:
                comparisons.append({
                    "variant_id": variant["variant_id"],
                    "variant_name": variant["variant_name"],
                    "p_value": 1.0,
                    "significant": False,
                    "error": "Insufficient data for Mann-Whitney",
                })
                continue

            stat, p_value = scipy_stats.mannwhitneyu(control_reply_times, variant_reply_times, alternative="two-sided")
            comparisons.append({
                "variant_id": variant["variant_id"],
                "variant_name": variant["variant_name"],
                "p_value": float(p_value),
                "significant": bool(p_value < test.significance_threshold),
            })

        any_significant = any(c["significant"] for c in comparisons)
        min_p = min(c["p_value"] for c in comparisons) if comparisons else 1.0

        return {"p_value": float(min_p), "significant": any_significant, "comparisons": comparisons}

    def auto_promote(self, test: ABTest) -> ABTest | None:
        """Auto-promote winning variant if p < threshold and min_sample_size met."""
        total_sent = self._get_test_send_count(test)
        if total_sent < test.min_sample_size:
            return None

        if test.metric == "open_rate":
            result = self.run_chi_squared_opens(test)
        else:
            result = self.run_mann_whitney_reply(test)

        if not result["significant"]:
            return None

        best = self._find_best_variant(test)
        if best is None:
            return None

        test.winning_variant_id = best.id
        test.status = "completed"

        for av in test.variants:
            if av.variant_id != best.id:
                av.variant.is_active = False

        self.db.commit()
        return test

    def _find_best_variant(self, test: ABTest) -> MessageVariant | None:
        best = None
        best_rate = -1.0

        for av in test.variants:
            perf = self.get_variant_performance(av.variant)
            rate = perf["reply_rate"] if test.metric == "reply_rate" else perf["open_rate"]
            if rate > best_rate:
                best_rate = rate
                best = av.variant

        return best

    def _get_test_send_count(self, test: ABTest) -> int:
        variant_ids = [av.variant_id for av in test.variants]
        return (
            self.db.query(MessageEvent)
            .filter(MessageEvent.variant_id.in_(variant_ids), MessageEvent.sent_at.isnot(None))
            .count()
        )

    def get_optimal_send_time(self, persona_key: str) -> dict:
        rec = (
            self.db.query(SendTimeRecommendation)
            .filter(SendTimeRecommendation.persona_key == persona_key)
            .first()
        )

        if not rec:
            return {"persona_key": persona_key, "optimal_hour_utc": 14, "optimal_day_of_week": 2, "confidence": 0.0, "sample_size": 0}

        return {
            "persona_key": rec.persona_key,
            "optimal_hour_utc": rec.optimal_hour_utc,
            "optimal_day_of_week": rec.optimal_day_of_week,
            "confidence": rec.confidence,
            "sample_size": rec.sample_size,
        }

    def adapt_variant_pool(self, test: ABTest) -> list[dict]:
        """Adaptive learning: evolve variant pool based on historical performance."""
        variant_ids = [av.variant_id for av in test.variants]
        performances = [self.get_variant_performance(av.variant) for av in test.variants]

        performances.sort(key=lambda p: p["reply_rate"], reverse=True)
        top_n = max(1, len(performances) // 2)
        top_variants = performances[:top_n]

        if not top_variants:
            return performances

        avg_reply_rate = sum(p["reply_rate"] for p in top_variants) / len(top_variants)

        suggestions = []
        for p in performances:
            if p["reply_rate"] < avg_reply_rate * 0.5:
                suggestions.append({
                    "variant_id": p["variant_id"],
                    "variant_name": p["variant_name"],
                    "action": "deprecate",
                    "reason": f"Reply rate {p['reply_rate']:.3f} below 50% of top average {avg_reply_rate:.3f}",
                })

        return suggestions

    def thompson_sampling_select(self, test: ABTest) -> MessageVariant | None:
        """Bayesian bandit: Thompson sampling for continuous optimization."""
        if not test.variants:
            return None

        best_sample = None
        best_value = -float("inf")

        for av in test.variants:
            perf = self.get_variant_performance(av.variant)
            alpha = perf["replied"] + 1
            beta = (perf["sent"] - perf["replied"]) + 1
            sample = random.betavariate(alpha, beta)

            if sample > best_value:
                best_value = sample
                best_sample = av.variant

        return best_sample if best_value > 0 else test.variants[0].variant
