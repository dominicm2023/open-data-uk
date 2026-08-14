# MVP definition

Decided 2026-08-13. Audience: **data practitioners** (analysts, journalists,
researchers, civic devs). Interface: **search site + open API**. Hosting:
**cheap VPS + domain**.

## In scope

1. **Geo-aware search** — the Brighton→Glasgow fix. Extract place names from
   queries, geo-tag datasets via publisher/title, boost matching results, and
   be honest when a place has no indexed data instead of serving the
   best-titled match from the wrong end of the country.
2. **Open API** — documented JSON endpoints (`/api/search`, `/api/stats`),
   CORS, light rate limiting, attribution note in responses. FastAPI's
   auto-docs at `/docs`. MCP endpoint as stretch goal.
3. **Trust surface** — about page with the data-quality stats (the 56%
   no-licence story), source list, suggest-a-source link.
4. **Repo + contribution flow** — public GitHub, README, sources.yaml PR
   guide, endpoint-validation CI for suggested sources.
5. **Deployment** — Dockerfile/systemd, scheduled re-harvest (cron), domain.

## Out of scope for MVP (explicitly)

- AI chatbot (Haiku RAG layer) — post-MVP, costs money per query
- Dataset change alerts / monitoring
- Series grouping (annual editions), reranker
- Additional harvester protocols beyond CKAN + DCAT

## Quality bar

Niche-query test suite passes; no wrong-geography top-3 without an honest
banner; API stable enough to document.
