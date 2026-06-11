from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from enum import Enum
from statistics import mean

import numpy as np
from scipy import signal as scipy_signal

from market_intelligence.models import JobPosting, TrendPoint, TrendSeries


def _decompose(values: Sequence[float]) -> tuple[list[float], list[float], list[float]]:
    n = len(values)
    if n < 14:
        return list(values), [0.0] * n, [0.0] * n
    arr = np.array(values, dtype=np.float64)
    window = min(7, n // 2)
    trend = np.convolve(arr, np.ones(window) / window, mode="same")
    detrended = arr - trend
    period = _detect_period(detrended)
    seasonal = np.zeros_like(arr)
    if period and period < n // 2:
        for i in range(n):
            seasonal[i] = np.mean([detrended[j] for j in range(i, n, period)])
        residual = detrended - seasonal
    else:
        residual = detrended
    return trend.tolist(), seasonal.tolist(), residual.tolist()


def _detect_period(detrended: np.ndarray) -> int | None:
    n = len(detrended)
    if n < 14:
        return None
    try:
        f, Pxx = scipy_signal.periodogram(detrended)
        valid = (f > 0) & (f < 0.5)
        if not valid.any():
            return None
        peak_idx = np.argmax(Pxx[valid])
        peak_f = f[valid][peak_idx]
        period = int(round(1.0 / peak_f))
        return period if 3 <= period <= n // 2 else None
    except Exception:
        return None


def compute_trend_series(postings: list[JobPosting], *, category_attr: str = "role_category", days: int = 90) -> list[TrendSeries]:
    grouped: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    cutoff = datetime.now() - timedelta(days=days)
    for p in postings:
        if p.posted_at < cutoff:
            continue
        val = getattr(p, category_attr, "unknown")
        key = str(val.value if isinstance(val, Enum) else val)
        grouped[key][p.posted_at.date()] += 1
    series_list: list[TrendSeries] = []
    for category, daily_counts in grouped.items():
        dates_sorted = sorted(daily_counts.keys())
        if not dates_sorted:
            continue
        start, end = dates_sorted[0], dates_sorted[-1]
        all_dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        values = [float(daily_counts.get(d, 0)) for d in all_dates]
        trend, seasonal, residual = _decompose(values)
        points = [TrendPoint(date=d, value=v, moving_avg=trend[i] if i < len(trend) else None, seasonal=seasonal[i] if i < len(seasonal) else None, residual=residual[i] if i < len(residual) else None) for i, (d, v) in enumerate(zip(all_dates, values))]
        growth_rate = _growth_rate(values)
        direction = "up" if growth_rate > 0.05 else "down" if growth_rate < -0.05 else "stable"
        series_list.append(TrendSeries(category=category, points=points, growth_rate=round(growth_rate, 4), direction=direction))
    series_list.sort(key=lambda s: s.growth_rate, reverse=True)
    return series_list


def _growth_rate(values: Sequence[float]) -> float:
    if len(values) < 7:
        return 0.0
    first_half = values[:len(values) // 2]
    second_half = values[len(values) // 2:]
    avg_first = mean(first_half) if first_half else 0.0
    avg_second = mean(second_half) if second_half else 0.0
    return 0.0 if avg_first == 0 else (avg_second - avg_first) / avg_first


def top_growing_roles(postings: list[JobPosting], *, limit: int = 10, days: int = 90, min_volume: int = 5) -> list[TrendSeries]:
    series = compute_trend_series(postings, category_attr="role_category", days=days)
    series = [s for s in series if s.direction == "up" and sum(p.value for p in s.points) >= min_volume]
    return series[:limit]
