"""product-service: catalogue listing, search and lookup."""
from __future__ import annotations

from fastapi import HTTPException

from common.observability import create_app

app = create_app("product-service")

CATEGORIES = ["electronics", "books", "home", "toys"]
PRODUCTS = [
    {
        "id": f"p{i}",
        "name": f"Product {i}",
        "category": CATEGORIES[(i - 1) % len(CATEGORIES)],
        "price": round(5 + i * 1.75, 2),
        "stock": 100 - i,
    }
    for i in range(1, 13)
]


@app.get("/products")
def list_products(category: str | None = None) -> dict:
    items = PRODUCTS if not category else [p for p in PRODUCTS if p["category"] == category]
    return {"count": len(items), "products": items}


@app.get("/products/search")
def search(q: str = "") -> dict:
    needle = q.lower()
    items = [p for p in PRODUCTS if needle in p["name"].lower() or needle in p["category"].lower()]
    return {"count": len(items), "products": items}


@app.get("/products/{product_id}")
def get_product(product_id: str) -> dict:
    for product in PRODUCTS:
        if product["id"] == product_id:
            return product
    raise HTTPException(404, "product not found")
