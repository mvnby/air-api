## Summary

- What changed:
- Why:

## Scope

- [ ] Backend
- [ ] Storefront (`web/`)
- [ ] Manager frontend (`manager_frontend/`)
- [ ] Infra/CI/CD
- [ ] DB migration

## Validation

- Local checks run:
  - [ ] `pytest -q` (or targeted tests)
  - [ ] `cd web && npm run build` (if touched)
  - [ ] `cd manager_frontend && npm run build` (if touched)
- Manual checks:
  - [ ] Main user flow verified
  - [ ] No visible regressions in touched areas

## Legacy Admin Check

- [ ] This PR changes `admin/*` (legacy SQLAdmin)
- [ ] If yes, justification provided (why compat fix is needed and why not manager-first)

## Deployment Notes

- [ ] No special deploy steps
- [ ] Requires Alembic migration
- [ ] Requires post-deploy script/manual data operation

If special steps required, describe exact commands:

```bash
# Example
# docker compose exec app alembic upgrade head
```

## Risk and Rollback

- Risk level: Low / Medium / High
- Rollback plan:

## Screenshots / Logs (optional)
