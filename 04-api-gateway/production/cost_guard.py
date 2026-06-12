"""
Cost Guard - Bao ve budget LLM.

Yeu cau lab:
- Moi user co budget $10/thang
- Track spending trong Redis
- Reset theo thang

Trong local lab, neu chua co Redis/REDIS_URL, module fallback ve in-memory
de app van chay duoc. Khi deploy production, set REDIS_URL de state khong
bi mat khi restart/scale.
"""
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import HTTPException

try:
    import redis
except ImportError:  # Local fallback neu redis package chua duoc cai.
    redis = None

logger = logging.getLogger(__name__)


# Gia token tham khao cho GPT-4o-mini.
PRICE_PER_1K_INPUT_TOKENS = 0.00015
PRICE_PER_1K_OUTPUT_TOKENS = 0.0006
DEFAULT_MONTHLY_BUDGET_USD = 10.0
REDIS_TTL_SECONDS = 32 * 24 * 3600


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    input_cost = (input_tokens / 1000) * PRICE_PER_1K_INPUT_TOKENS
    output_cost = (output_tokens / 1000) * PRICE_PER_1K_OUTPUT_TOKENS
    return round(input_cost + output_cost, 6)


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


@dataclass
class UsageRecord:
    user_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    request_count: int = 0
    month: str = field(default_factory=current_month)

    @property
    def total_cost_usd(self) -> float:
        return estimate_cost_usd(self.input_tokens, self.output_tokens)


class CostGuard:
    def __init__(
        self,
        monthly_budget_usd: float = DEFAULT_MONTHLY_BUDGET_USD,
        warn_at_pct: float = 0.8,
        redis_url: str | None = None,
    ):
        self.monthly_budget_usd = monthly_budget_usd
        self.warn_at_pct = warn_at_pct
        self._records: dict[str, UsageRecord] = {}
        self._redis = self._connect_redis(redis_url or os.getenv("REDIS_URL", ""))

    def _connect_redis(self, redis_url: str):
        if not redis_url or redis is None:
            logger.warning("Redis not configured - using in-memory cost guard")
            return None

        try:
            client = redis.Redis.from_url(redis_url, decode_responses=True)
            client.ping()
            logger.info("Cost guard connected to Redis")
            return client
        except Exception as exc:
            logger.warning("Redis unavailable - using in-memory cost guard: %s", exc)
            return None

    def _key(self, user_id: str, suffix: str = "cost") -> str:
        return f"budget:{user_id}:{current_month()}:{suffix}"

    def _get_record(self, user_id: str) -> UsageRecord:
        month = current_month()
        record = self._records.get(user_id)
        if not record or record.month != month:
            record = UsageRecord(user_id=user_id, month=month)
            self._records[user_id] = record
        return record

    def _current_cost(self, user_id: str) -> float:
        if self._redis:
            return float(self._redis.get(self._key(user_id, "cost")) or 0)
        return self._get_record(user_id).total_cost_usd

    def check_budget(self, user_id: str, estimated_cost: float = 0.0) -> None:
        """
        Kiem tra budget truoc khi goi LLM.
        Raise 402 neu current + estimated_cost vuot $10/thang.
        """
        current = self._current_cost(user_id)
        projected = current + estimated_cost

        if projected > self.monthly_budget_usd:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Monthly budget exceeded",
                    "used_usd": round(current, 6),
                    "estimated_cost_usd": round(estimated_cost, 6),
                    "budget_usd": self.monthly_budget_usd,
                    "resets_at": "first day of next month UTC",
                },
            )

        if current >= self.monthly_budget_usd * self.warn_at_pct:
            logger.warning(
                "User %s at %.0f%% monthly budget",
                user_id,
                current / self.monthly_budget_usd * 100,
            )

    def record_usage(
        self, user_id: str, input_tokens: int, output_tokens: int
    ) -> UsageRecord:
        """Ghi nhan usage sau khi LLM tra response."""
        cost = estimate_cost_usd(input_tokens, output_tokens)
        self.check_budget(user_id, cost)

        if self._redis:
            pipe = self._redis.pipeline()
            pipe.incrbyfloat(self._key(user_id, "cost"), cost)
            pipe.incrby(self._key(user_id, "input_tokens"), input_tokens)
            pipe.incrby(self._key(user_id, "output_tokens"), output_tokens)
            pipe.incrby(self._key(user_id, "requests"), 1)
            for suffix in ["cost", "input_tokens", "output_tokens", "requests"]:
                pipe.expire(self._key(user_id, suffix), REDIS_TTL_SECONDS)
            pipe.execute()

            return UsageRecord(
                user_id=user_id,
                input_tokens=int(self._redis.get(self._key(user_id, "input_tokens")) or 0),
                output_tokens=int(self._redis.get(self._key(user_id, "output_tokens")) or 0),
                request_count=int(self._redis.get(self._key(user_id, "requests")) or 0),
                month=current_month(),
            )

        record = self._get_record(user_id)
        record.input_tokens += input_tokens
        record.output_tokens += output_tokens
        record.request_count += 1

        logger.info(
            "Usage: user=%s req=%s cost=$%.6f/$%.2f monthly",
            user_id,
            record.request_count,
            record.total_cost_usd,
            self.monthly_budget_usd,
        )
        return record

    def get_usage(self, user_id: str) -> dict:
        if self._redis:
            cost = float(self._redis.get(self._key(user_id, "cost")) or 0)
            requests = int(self._redis.get(self._key(user_id, "requests")) or 0)
            input_tokens = int(self._redis.get(self._key(user_id, "input_tokens")) or 0)
            output_tokens = int(self._redis.get(self._key(user_id, "output_tokens")) or 0)
        else:
            record = self._get_record(user_id)
            cost = record.total_cost_usd
            requests = record.request_count
            input_tokens = record.input_tokens
            output_tokens = record.output_tokens

        return {
            "user_id": user_id,
            "month": current_month(),
            "requests": requests,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "budget_usd": self.monthly_budget_usd,
            "budget_remaining_usd": max(0, round(self.monthly_budget_usd - cost, 6)),
            "budget_used_pct": round(cost / self.monthly_budget_usd * 100, 1),
            "storage": "redis" if self._redis else "memory",
        }


cost_guard = CostGuard(
    monthly_budget_usd=float(os.getenv("MONTHLY_BUDGET_USD", DEFAULT_MONTHLY_BUDGET_USD))
)


def check_budget(user_id: str, estimated_cost: float) -> bool:
    """
    API dung dung theo de bai Exercise 4.4.

    Return True neu con budget, False neu vuot. Dong thoi ghi nhan estimated_cost
    vao Redis/in-memory de lan check tiep theo thay spending da tang.
    """
    try:
        cost_guard.check_budget(user_id, estimated_cost)
    except HTTPException:
        return False

    if cost_guard._redis:
        cost_guard._redis.incrbyfloat(cost_guard._key(user_id, "cost"), estimated_cost)
        cost_guard._redis.expire(cost_guard._key(user_id, "cost"), REDIS_TTL_SECONDS)
    else:
        record = cost_guard._get_record(user_id)
        # Estimated-only path: convert cost to equivalent input tokens for tracking.
        equivalent_input_tokens = int(estimated_cost / PRICE_PER_1K_INPUT_TOKENS * 1000)
        record.input_tokens += equivalent_input_tokens
        record.request_count += 1

    return True
