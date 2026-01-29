# Phase 42: API Path & Network Optimization Tasks

> [!IMPORTANT]
> This document was generated during Phase 41 (Optimization Analysis) to capture identified API inconsistencies that need resolution but were deferred to avoid breaking changes without backend verification.

## 1. Verify `getProductById` Endpoint
**File**: `web/src/utils/api.js`
**Function**: `getProductById(id)`

**Current State**:
```javascript
const PUBLIC_API_ROOT = (import.meta.env.PUBLIC_API_URL || 'http://localhost:8000').replace(/\/api\/v1\/?$/, "");
// ...
const API_V1 = import.meta.env.SSR ? INTERNAL_URL : PUBLIC_URL;
const API_ROOT = API_V1.replace(/\/v1$/, ""); 

export async function getProductById(id) {
    // Uses API_ROOT because ID endpoint is at /api/products/{id}
    const url = `${API_ROOT}/products/${id}`;
    // ...
}
```

**Issue**:
Most endpoints use `API_V1` (e.g., `/api/v1/catalog`, `/api/v1/orders`). `getProductById` specifically falls back to `API_ROOT` (root `/api/`), implying an older endpoint structure (`/api/products/{id}`).

**Task**:
1.  Check `services/product_service.py` or `routers/*` in Backend to see if `GET /api/v1/products/{id}` is available.
2.  If yes -> Update `api.js` to use `API_V1` and remove `API_ROOT`.
3.  If no -> Create a task to migrate the backend endpoint to V1 router, then update frontend.

## 2. SSR vs Client Requests
**Context**:
The `api.js` currently attempts to solve SSR execution by using `INTERNAL_API_URL` (docker network alias `app:8000`).

**Task**:
- Verify that `API_V1` and `API_ROOT` logic correctly handles both SSR (using internal docker DNS) and Client-side (using standard Public URL) to avoid CORS issues or "Network Unreachable" errors during build/hydration.
