# Lessons Learned: Docker Environment Configuration

## Issue: PriceWithToggle Component Not Rendering

**Date**: 2026-01-30  
**Severity**: High  
**Root Cause**: Incorrect `PUBLIC_API_URL` in `docker-compose.yml`

---

## Problem Description

The `PriceWithToggle.vue` component was not rendering on the catalog and product pages. Installation toggles were missing, and the "Add to Cart" buttons were invisible.

**Symptoms:**
- Browser console showed CORS errors
- API calls to `http://api.mvn.by/api/v1/config` blocked by browser
- Components failed to hydrate

## Root Cause

The `docker-compose.yml` had:

```yaml
environment:
  - PUBLIC_API_URL=http://api.mvn.by/api/v1  # ← WRONG for local dev
```

This URL is the **production API**, which:
1. Cannot be accessed from `localhost` due to CORS policy
2. Causes Vue components to fail API calls and not render

## Solution

For **local development**, use:

```yaml
environment:
  - PUBLIC_API_URL=http://localhost:8000/api/v1  # For browser (local dev)
  - INTERNAL_API_URL=http://app:8000/api/v1      # For SSR (docker network)
```

> [!IMPORTANT]
> **Before deploying to production**, revert `PUBLIC_API_URL` back to the production API URL!

## Prevention Checklist for Future Agents

1. **If Vue components don't render**: Check browser console for CORS errors
2. **If CORS errors exist**: Verify `PUBLIC_API_URL` in `docker-compose.yml`
3. **For local dev**: `PUBLIC_API_URL` must point to `localhost:8000`
4. **After changing env vars**: Run `docker compose up -d --build web` (not just restart)
5. **The `INTERNAL_API_URL`**: Uses Docker network DNS (`app:8000`) for SSR - this is CORRECT

## Related Files
- `docker-compose.yml` - Environment configuration
- `web/src/utils/api.js` - API URL resolution logic
- `web/src/components/PriceWithToggle.vue` - Component that makes API calls
