# Versiful Companion — Shared REST API Conventions

> Status: Authoritative for all **new** companion feature endpoints (Wave 2+).
> Source of truth for *what* to build is [`COMPANION_SPEC.md`](./COMPANION_SPEC.md) §14;
> this doc closes **build-plan gap #1** ("No REST request/response contracts exist for
> any new endpoint, and no per-endpoint auth/subscription gating is specified").
>
> Every feature lambda (prayers, reflections, plans, walk, preferences) MUST follow
> these conventions so the frontend (`CompanionContext` → real API client) inherits a
> single consistent contract. Existing endpoints (auth/users/chat/subscription/sms) are
> unchanged; adopt these for everything new.

---

## 1. Transport & framing

- **HTTP API (API Gateway v2)**, `AWS_PROXY` integration, same as the existing chat
  routes. Lambdas return `{ "statusCode", "headers", "body" }` with a **JSON string**
  body.
- **Content type:** `application/json` for all request and response bodies.
- **camelCase everywhere on the wire** (matches DynamoDB attrs + frontend). SQL/Neon
  stays snake_case internally (ADR-1) and is mapped to camelCase at the API boundary.
- **Timestamps:** ISO-8601 UTC with trailing `Z` (e.g. `2026-06-09T14:08:00Z`).
- **IDs:** string UUIDs.

### CORS
Reuse the existing helper pattern (`web_handler.cors_headers()`): echo the configured
origin, `Access-Control-Allow-Methods` per route, `Allow-Headers: Content-Type,Authorization`,
`Allow-Credentials: true`. Every route also needs an `OPTIONS` integration.

---

## 2. Authentication

- **All companion endpoints require JWT** via the existing custom authorizer
  (`authorization_type = "CUSTOM"`, `authorizer_id = var.jwt_auth_id`) — EXCEPT the
  read-only reading-plan catalog (`GET /plans`, `GET /plans/{slug}`) which MAY be public
  (spec §14); those must never leak per-user data.
- Resolve the caller with the existing pattern (`web_handler.get_user_id_from_event` /
  `event["requestContext"]["authorizer"]["userId"]`). The user id is the Cognito `sub`
  and is the cross-store join key (`userId` in DynamoDB, `user_id` in Neon).
- **Never trust a `userId` from the body or query string.** Always derive it from the
  authorizer context. Every query/mutation is implicitly scoped to the caller's id.
- Missing/invalid auth → **401** with the standard error envelope.

---

## 3. Subscription gating (free vs premium)

Gating rules come from spec §16. Enforce on the **server** (the frontend gate is UX
only). Determine the caller's entitlement from the `users` item (`isSubscribed` /
`plan`), reusing `chat_handler.get_user_info()`.

| Capability | Free | Premium |
|---|---|---|
| Prayer journal | view-only / **3** prayers | unlimited + reminders |
| Reflection log | — | ✓ |
| Reading plans | 1 trial plan | all |
| Daily verse / Check-ins / My Walk (full) | — / teaser | ✓ |

- A premium-only **write** by a free user → **402 Payment Required** with
  `error.code = "subscription_required"`.
- A **limit** breach (e.g. free user creating a 4th prayer) → **402** with
  `error.code = "limit_reached"` and a `details` object describing the limit.
- Premium-only **reads** degrade to a teaser per spec rather than erroring where the UI
  expects a teaser (document per endpoint); otherwise return 402.

---

## 4. Response envelope

**Success** — the payload is returned under a top-level `data` key, plus an optional
`meta` (used for pagination, counts, cache hints):

```json
{
  "data": { "...": "resource or { items: [...] }" },
  "meta": { "count": 12, "nextCursor": null }
}
```

- Single resource: `data` is the object.
- Collections: `data` is `{ "items": [ ... ] }` and `meta.count` is the page size.
- `201 Created` for resource creation (return the created resource in `data`).
- `204 No Content` (empty body) is acceptable for deletes; or `200` with
  `{ "data": { "deleted": true, "id": "..." } }` (prefer the latter for the frontend).

**Error** — always this shape, never a bare string:

```json
{
  "error": {
    "code": "limit_reached",
    "message": "Free plan allows up to 3 prayers. Upgrade for unlimited.",
    "details": { "limit": 3, "current": 3 }
  }
}
```

`error.code` is a stable machine-readable slug (snake_case); `message` is
human-readable; `details` is optional.

### Standard status codes
| Code | When |
|---|---|
| 200 | OK (read / update / delete-ack) |
| 201 | Resource created |
| 400 | Validation error (`code: "validation_error"`, `details` lists fields) |
| 401 | Missing/invalid JWT (`code: "unauthorized"`) |
| 402 | Subscription/limit gate (`code: "subscription_required"` \| `"limit_reached"`) |
| 403 | Authenticated but not allowed (`code: "forbidden"`) |
| 404 | Not found / not owned by caller (`code: "not_found"`) |
| 409 | Conflict / idempotency (`code: "conflict"`) |
| 422 | Semantically invalid (rare; prefer 400) |
| 500 | Unhandled server error (`code: "internal_error"`, no internals leaked) |

> **Ownership = 404, not 403.** If a resource exists but belongs to another user,
> return **404** (don't reveal existence).

---

## 5. Pagination

Cursor-based, opaque, forward-only (suits DynamoDB `LastEvaluatedKey` and Neon
keyset paging):

- Request: `?limit=<n>&cursor=<opaque>` — `limit` default **25**, max **100**.
- Response `meta`: `{ "count": <items on this page>, "nextCursor": <opaque|null> }`.
- `nextCursor: null` means no more pages. Clients pass it back verbatim as `cursor`.
- The cursor is an opaque base64 token (e.g. base64 of the DynamoDB `LastEvaluatedKey`
  JSON, or the Neon keyset tuple). Never expose raw keys.

Filtering uses explicit query params documented per endpoint (e.g.
`GET /prayers?status=active`, `GET /reflections?q=&source=`). For `reflections?q=`,
search is **vector similarity** over Neon when a query is supplied (spec §8), else
recency order — document the chosen semantics in the handler.

---

## 6. Validation & idempotency

- Reject unknown/oversized bodies; validate required fields and enums server-side;
  return **400** `validation_error` with `details.fields`.
- Coerce/normalize before write (trim strings, lowercase enums, validate `YYYY-MM-DD`
  dates, normalize phone numbers via the existing `normalize_phone_number`).
- **Idempotent counters** use atomic DynamoDB `ADD` (e.g. `prayCount`), never
  read-modify-write.
- Preference/account mutations follow the existing generic `users` update path
  (`users/helpers.update_user_settings`) so chat tools (§5.4) and web settings stay in
  parity — **no new preferences table** (resolved: reuse `GET/PUT /users`, treat
  `/users/preferences` as an alias if mounted; spec inconsistency #1).
- Mutations SHOULD write an **audit trail** entry (`{ts, source, field, old, new}`,
  `source` ∈ `web|chat`) where the spec requires it (§5.4 TCPA).

---

## 7. Cross-store writes & graceful degradation

Companion data spans **DynamoDB** (system of record: prayers, verse_history, reading
plans, checkins, users) and **Neon** (`user_memories`, `reflections` only). Conventions:

- `userId` (Cognito `sub`) joins the stores; **no FK enforcement**, app-level joins are
  fine.
- Endpoints that touch Neon (reflections, `/walk/memories`) MUST use the shared Neon
  access layer (`neon_client` + `memory_store`) which **degrades gracefully** — a Neon
  outage returns a clear `503`/empty result for Neon-only reads, but must NEVER break a
  DynamoDB-backed core action. For a mixed write (e.g. prayer "answered" → thanksgiving
  verse + reflection), the DynamoDB write is authoritative; the Neon reflection is
  best-effort and its failure is logged, not surfaced as a request failure.
- Deletes of memories/reflections are **single-store Neon** ops (the pgvector
  `embedding` is on the same row, so a normal row delete removes it; §11.2a).

---

## 8. Example contracts (illustrative — feature agents finalize fields)

**Create prayer** — `POST /prayers` (JWT; free capped at 3)
```json
// request
{ "title": "Mom's surgery", "body": null, "people": ["mom"],
  "category": "family", "eventDate": "2026-06-12", "reminderCadence": "weekly" }
// 201
{ "data": { "id": "f1e2...", "userId": "...", "title": "Mom's surgery",
            "status": "active", "prayCount": 0, "createdAt": "2026-06-09T14:08:00Z" } }
// 402 (free limit)
{ "error": { "code": "limit_reached", "message": "Free plan allows up to 3 prayers.",
             "details": { "limit": 3, "current": 3 } } }
```

**List reflections** — `GET /reflections?q=anxiety&limit=25`
```json
{ "data": { "items": [ { "id": "...", "content": "...", "source": "auto_summary",
            "verseReference": "Isaiah 41:10", "createdAt": "..." } ] },
  "meta": { "count": 25, "nextCursor": "eyJpZCI6..." } }
```

**Delete one memory** — `DELETE /walk/memories/{id}` (JWT; Neon single-store)
```json
{ "data": { "deleted": true, "id": "..." } }
```
