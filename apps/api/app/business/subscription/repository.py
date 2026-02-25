from __future__ import annotations

from app.platform.security.repository import BaseRepository


class PlanRepository(BaseRepository):
    resource = "subscription.plan"


class PlanItemRepository(BaseRepository):
    resource = "subscription.plan_item"


class SubscriptionRepository(BaseRepository):
    resource = "subscription.subscription"


class SubscriptionItemRepository(BaseRepository):
    resource = "subscription.subscription_item"


class SubscriptionChangeRepository(BaseRepository):
    resource = "subscription.subscription_change"
