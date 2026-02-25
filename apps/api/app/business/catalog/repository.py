from __future__ import annotations

from app.platform.security.repository import BaseRepository


class CatalogProductRepository(BaseRepository):
    resource = "catalog.product"


class CatalogPricebookRepository(BaseRepository):
    resource = "catalog.pricebook"


class CatalogPricebookItemRepository(BaseRepository):
    resource = "catalog.pricebook_item"
