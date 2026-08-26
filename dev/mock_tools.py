"""
PLATFORM: Mock tools server for local development.

Provides fake tool endpoints and a mock registry so the agent-platform-sdk
can discover and call tools without a real APIM / platform backend.

Start via: docker compose -f docker-compose.dev.yml up
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Mock Tools Server", version="0.1.0")

# ---------------------------------------------------------------------------
# Mock product data
# ---------------------------------------------------------------------------
PRODUCTS: list[dict] = [
    {"id": "1", "name": "Generic Item A", "price": 29.99},
    {"id": "2", "name": "Generic Item B", "price": 49.99},
]

# ---------------------------------------------------------------------------
# Registry endpoints — SDK fetches tool schemas from here
# ---------------------------------------------------------------------------

@app.get("/registry/tools/products-api")
async def registry_products_api() -> dict:
    return {
        "tool_id": "products-api",
        "base_url": "http://mock-tools:8001",
        "transport": "rest",
        "operations": [
            {"method": "GET", "path": "/tools/products-api/products", "name": "list"},
            {"method": "GET", "path": "/tools/products-api/products/{id}", "name": "get"},
        ],
    }


@app.get("/registry/tools/basket-api")
async def registry_basket_api() -> dict:
    return {
        "tool_id": "basket-api",
        "base_url": "http://mock-tools:8001",
        "transport": "rest",
        "operations": [
            {"method": "GET", "path": "/tools/basket-api/basket", "name": "list"},
            {"method": "POST", "path": "/tools/basket-api/basket/items", "name": "add_items"},
        ],
    }


# ---------------------------------------------------------------------------
# Products API mock routes
# ---------------------------------------------------------------------------

@app.get("/tools/products-api/products")
async def list_products() -> list[dict]:
    return PRODUCTS


@app.get("/tools/products-api/products/{product_id}")
async def get_product(product_id: str) -> dict:
    for product in PRODUCTS:
        if product["id"] == product_id:
            return product
    raise HTTPException(status_code=404, detail="Product not found")


# ---------------------------------------------------------------------------
# Basket API mock routes
# ---------------------------------------------------------------------------

class AddItemRequest(BaseModel):
    product_id: str
    quantity: int


@app.get("/tools/basket-api/basket")
async def get_basket() -> dict:
    return {"items": [], "total": 0.0}


@app.post("/tools/basket-api/basket/items")
async def add_basket_items(body: AddItemRequest) -> dict:
    # PLATFORM: Stateless mock — always returns a single-item basket
    product = next((p for p in PRODUCTS if p["id"] == body.product_id), None)
    price = product["price"] if product else 0.0
    return {
        "items": [{"product_id": body.product_id, "quantity": body.quantity}],
        "total": price * body.quantity,
    }
