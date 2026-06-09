# Versiful Companion — Build Plan

> Status: Planning deliverable (no code/infra changes). Source of truth for *what* to build is
> [`docs/COMPANION_SPEC.md`](./COMPANION_SPEC.md); this doc translates that spec into an
> implementation-granularity, dependency-ordered plan grounded in the actual backend repo and
> aligned to [`docs/CICD_DEPLOYMENT_WORKFLOW.md`](./CICD_DEPLOYMENT_WORKFLOW.md).
> The companion UI mockup already exists on branch `feature/companion-ui-mockup` in
> `versiful-frontend` (all screens built against mock data in `CompanionContext.jsx`).

---

## Executive summary

**Recommended Neon approach — manual projects + Terraform-managed secret/wiring only.** Provision the Neon
**project per environment MANUALLY** (Neon console/CLI), once per env (`dev` / `staging` / `prod`), and record each
env's **pooled connection URI** — there is **no Neon Terraform provider** in this plan, and therefore **no Terraform
version bump** (keep the existing `>= 1.3.0` pin). **Terraform manages ONLY** the connection-string secret in AWS
Secrets Manager (add `neon_database_url` to the existing per-env secret) and the supporting wiring (Lambda
env/secret access + the Postgres driver in the LangChain layer). **One Neon project per env** is the chosen topology
(true blast-radius isolation for sensitive spiritual/PII data, a clean 1:1 with the existing per-env `*.tfvars` +
per-env state — not one shared project with a branch per env). Because nothing in Terraform talks to Postgres,
`vector` enablement + the two-table schema + HNSW indexes are created by an **idempotent migration script**
(psycopg/pg8000) run once per env against the pooled URI — still the prerequisite for the §5.5 memory backfill, and
now with **no dependency on any TF provider**. **No VPC** is needed (Neon is public + TLS; use the pooled endpoint).
See Part 2 §2.5 for the explicit manual per-env runbook.

**Phase order at a glance** (each phase = one shared branch name across both repos):

1. **Foundation** — Neon (manual project per env + secret wiring + schema migration) + memory system + LangGraph agent refactor + `phoneNumber` GSI + one-off backfill. *Everything builds on this.*
2. **Daily Verse + Settings fixes** — daily-verse worker, wire `CommunicationPreferences`, fix the fake Settings save, response style.
3. **Prayer Journal + Reflection Log** — `prayers` table + endpoints + agent tools; reflections endpoints + auto-summary.
4. **Reading Plans** — catalog + enrollment/progress tables + delivery worker + tools.
5. **Check-ins + My Walk** — inactivity dispatcher (+ capped time-sensitive pass) + journey aggregation + memory manager/delete.
6. **Landing / Features / Pricing reposition** — copy + pricing reframe (frontend-led; can ship incrementally).

**Top 5 gaps that must be closed before/while building:**
1. **No REST request/response contracts** exist for any new endpoint, and **no per-endpoint auth/subscription gating** is specified.
2. **`lastMessageAt` is not denormalized onto the `users` item today** (it lives only on `chat_sessions`, web-only) — the entire inactivity check-in foundation is missing, and unregistered SMS texters have no `users` item at all.
3. **The extraction JSON contract + dedup/upsert rules are only sketched** (no vector-similarity threshold, fuzzy-match rule, salience math, or embedding-failure policy).
4. **DynamoDB key/attribute/GSI details** need finalizing — the `phoneNumber`/`checkins_by_status` GSIs require new attribute definitions (`phoneNumber`, `status`, `scheduledFor`). (Naming convention is now *decided*: see the ADR below — camelCase for DynamoDB attributes/keys, snake_case only inside Neon SQL.)
5. **Neon schema/extension is created out-of-band** (by the idempotent migration script, not Terraform — Terraform only manages the secret/wiring) and the **secret-read path is divergent** (`shared/secrets_helper.get_secret(key)` vs `chat/helpers.get_secret()` returning the whole dict) — both must be reconciled for `neon_database_url`.

---

## Finalized decisions (ADRs)

**ADR-1 — Naming convention.** Use **camelCase** for all DynamoDB attribute and key names (matches the existing
repo and frontend: `bibleVersion`, `phoneNumber`, `scheduledFor`, `responseStyle`, `lastMessageAt`, `eventDate`,
`prayCount`, …). Use **snake_case only inside Neon SQL** — i.e. the `user_memories` and `reflections` table and
column names (`user_id`, `event_date`, `last_referenced_at`, …), which is idiomatic Postgres. Spec-inherited
snake_case in the DynamoDB portions of this plan is treated as camelCase. The cross-store join key is the Cognito
`sub`, stored as `userId` in DynamoDB and `user_id` in Neon.

**ADR-2 — Neon provisioning: manual projects + Terraform-managed secret/wiring only.** Neon **projects are created
by hand, one per environment** (dev/staging/prod) via the Neon console/CLI; the operator copies each env's **pooled
connection URI**. There is **no Neon Terraform provider** and **no Terraform version bump** (keep `>= 1.3.0`).
**Terraform manages only**: the `neon_database_url` entry in the existing per-env Secrets Manager secret, the Lambda
secret/env access, and the Postgres driver added to the LangChain layer. The `vector` extension + the two-table
schema + HNSW indexes are applied by an **idempotent migration script** (psycopg/pg8000) run once per env against
the pooled URI — with **no dependency on any TF provider** — and that script is the prerequisite for the §5.5
backfill. Topology is **one Neon project per env**. See Part 2 §2.5 for the per-env runbook.

---

# Part 1 — Gap analysis (design vs. what must be built)

This goes feature-by-feature. For each: **Specified** (what the spec nails down) vs **Underspecified / must decide**.
A consolidated **gap checklist** follows at the end of Part 1.

## Cross-cutting facts grounded in the repo (read before the per-feature gaps)

- **Agent today** (`lambdas/chat/agent_service.py`): a single `RunnablePassthrough() | base_llm.bind_tools([get_versiful_info])` chain, `gpt-4o`, 10-message context window (`agent_config.yaml: history.context_window`). One tool. PostHog tracing wired. SMS vs web prompts split via config.
- **Chat path** (`lambdas/chat/chat_handler.py`): loads last 20 messages from `chat-messages` (DynamoDB, PK `threadId`, SK `timestamp`), invoked **directly** (not via API GW) by the SMS and web lambdas. The unregistered-SMS lookup is the `users_table.scan(FilterExpression=Attr('phoneNumber').eq(...), Limit=1)` the spec flags (§5.1) — confirmed present and buggy (Limit-before-filter).
- **Users table**: `aws_dynamodb_table.users` defines **only** `userId` (hash). No `phoneNumber` attribute/GSI yet. Attributes are camelCase (`firstName`, `bibleVersion`, `isSubscribed`, `plan`, `phoneNumber`).
- **User update path** (`lambdas/users/helpers.py: update_user_settings`): generic `PUT /users` that `UpdateItem`s **any** body field onto the `users` item via dynamic `SET`. This is the single mutation path that §5.4 chat tools and §12 web settings should both reuse. **No audit trail today.**
- **Secrets**: `terraform/modules/secrets/main.tf` jsonencodes a flat secret; OpenAI key is stored under key **`gpt`** (and code falls back to `openai_api_key`). Two read helpers exist and differ: `lambdas/shared/secrets_helper.get_secret(key)` (per-key) vs `lambdas/chat/helpers.get_secret()` (returns full dict; chat does `secrets.get('gpt')`). Lambdas get `SECRET_ARN` env + a `secretsmanager:GetSecretValue` IAM policy scoped to that secret.
- **Lambda layers** (`terraform/modules/lambdas/_layers.tf`): `core` (requests), `jwt`, `sms` (twilio), `langchain`. The langchain layer's **`requirements.txt` lists `langchain-core`, `langchain-openai`, `openai`, `pyyaml`, `posthog` — but NOT `langgraph`** (despite the layer description claiming langgraph). Layers built via `pip install --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.11`.
- **Lambda env wiring** (`_chat.tf`): table names + `POSTHOG_API_KEY` passed as env vars; chat function = 60s timeout / 512MB, web-chat = 30s / 256MB. IAM in `main.tf` grants DynamoDB to users/sms_usage/promo_codes + chat tables; **new tables need new IAM statements**.
- **Frontend** (`versiful-frontend`): all companion screens exist (`pages/Prayers.jsx`, `Journal.jsx`, `Plans.jsx`, `PlanDetail.jsx`, `MyWalk.jsx`, `Settings.jsx`; `components/{prayers,journal,plans,walk,settings,companion}/*`). They read/write a **pure client-side mock store** (`context/CompanionContext.jsx` → `mocks/companionData.js`) with **zero network calls**. Wiring = replace the mock mutators with a real API client (authed via `AuthContext`), keeping component props stable.
- **Deploy model** (CICD doc): backend `feature → dev → main`, deploy each env with `scripts/tf-env.sh <env> apply` (staging deploys *from the dev branch*); frontend `feature → dev → staging → main`, push auto-deploys, **never skip staging**. Same branch name across repos.

---

## F1. Daily Verse (spec §6)

**Specified:** Premium, opt-in (time + channel). Per-due-user context from memories/prayers/plan/reflections + `verse_history` exclusion list. LLM picks one verse + 1–2 sentence reflection in the user's translation, excludes recent refs, writes to `verse_history` (`context='daily_verse'`). Sunday recap. `daily_verse_worker` Lambda on EventBridge Scheduler (every 15 min, tz-bucketed). `lastDailyVerseAt` guard against double-send.

**Underspecified / must decide:**
- **Scheduler granularity vs timezone:** "every 15 min, tz-bucketed" requires storing the user's timezone (is `timezone` a `users` attr today? not confirmed) and a way to map `dailyVerseTime` (local) → UTC window. Decide tz source + DST handling.
- **`verse_history` write shape** — PK `userId` / SK `sentAt`, but the **pre-registration case** (SMS verses before a `userId` exists) needs either a `phoneNumber`-keyed item or a `phoneNumber` GSI + reconciliation on registration. Decide which, and the reconciliation trigger (registration already calls `ensure_sms_usage_record`/`link_sms_history_to_user` — hook here).
- **Sunday recap** generation: prompt, what counts as "this week's themes," and its own send/cost accounting (not in §16.1 model). Decide whether v1 ships recap or defers it.
- **Idempotency** under the 15-min scheduler: exact `lastDailyVerseAt` comparison + lock semantics so a slow run can't double-send.
- **Free-tier behavior:** daily verse is Premium; what does a free user toggling it see? (gating copy + 402-style response).

## F2. Prayer Journal (spec §7)

**Specified:** `prayers` DynamoDB table (PK `userId`, SK `prayerId`, listed attrs). Web `/prayers` CRUD + pray-now + mark-answered + celebration. Agent tools `save_prayer`/`list_active_prayers`/`mark_prayer_answered`. SMS keyword `PRAYERS`. Endpoints `GET/POST/PUT/DELETE /prayers`, `POST /prayers/{id}/answered`.

**Underspecified / must decide:**
- **Request/response JSON** for every endpoint (field names, validation, error codes). Frontend `AddPrayerModal`/`PrayerCard` already imply a shape (`title, body, category, people[], eventDate, reminderCadence, status, prayCount, lastPrayedAt, answerNote, answeredAt`) — codify it and match DynamoDB attrs exactly.
- **Auth + gating:** all prayer endpoints JWT; **free = view-only / 3 prayers** (§16) — where is the cap enforced (write path 402)?
- **`pray-now` concurrency:** `prayCount` increment should be an atomic `ADD`, not read-modify-write.
- **Answered → thanksgiving verse:** §7.1 says mark-answered generates a verse logged to `verse_history` + `reflections` — that couples the prayers handler to the agent/verse path and Neon. Decide sync vs async, and degradation if Neon down.
- **Reminders:** `reminderCadence`/`nextReminderAt` consumed by the check-in dispatcher (Phase 5) — define how a prayer reminder differs from an inactivity check-in (cost/consent).

## F3. Reflection Log (spec §8)

**Specified:** `reflections` is a **Neon** table (embedded on write). Auto-suggest "save takeaway," reading-plan reflections, manual entry, `recall`. Web `/journal` timeline + search + source filter. Endpoints `GET /reflections?q=&source=`, `POST`, `DELETE /reflections/{id}`. SMS `SAVE` keyword.

**Underspecified / must decide:**
- **Search semantics** of `?q=`: is it vector similarity (pgvector) or substring? Decide and document; affects index + latency.
- **`SAVE` keyword state:** "save the last reflection/takeaway" requires tracking what "last" means per phone (the last assistant turn? a pending suggested takeaway?). Define the state.
- **Embedding on write** failure policy (store row, backfill embedding later — §15.1a) needs a concrete retry/queue mechanism.
- **`source` enum** alignment: spec uses `auto_summary | manual | reading_plan`; frontend mock uses the same — lock it.
- **Gating:** reflection log is Premium (§16) — enforce on `POST`/`GET`.

## F4. Reading Plans (spec §9)

**Specified:** 7-plan seed catalog. Tables `reading_plans`, `reading_plan_days` (catalog — table *or* seed config), `user_reading_plans`, `user_reading_plan_progress` (keys given). `reading_plan_delivery` worker. Tools `enroll_reading_plan`, `get_reading_progress`. Endpoints `GET /plans`, `GET /plans/{slug}`, `POST /plans/{slug}/enroll`, `GET /plans/enrolled`, `POST /plans/enrolled/{id}/complete-day`, `POST /plans/enrolled/{id}/pause`.

**Underspecified / must decide:**
- **Catalog as table vs seed config** — pick one (seed config is simpler at this scale; table is queryable). Decide and where `reading_plan_days` content (passages/prompts) is authored — **content does not exist yet** for all 7 plans (frontend generates placeholder days).
- **`complete-day` writes a reflection to Neon** (`user_reading_plan_progress.reflectionId` → Neon `reflections.id`) — cross-store write contract + failure handling.
- **Delivery** worker dedup/idempotency (`lastDeliveredDay`/`lastDeliveredAt`) and how it reuses the daily-verse tz/scheduler machinery.
- **Public vs authed:** `GET /plans` / `GET /plans/{slug}` marked "public ok" — confirm and ensure no per-user data leaks.
- **Pause/resume** maps to `status` on `user_reading_plans` — same field the `pause_reading_plan()` tool writes (parity).

## F5. Check-ins (spec §10) — highest-risk

**Specified:** Inactivity-driven re-engagement is **primary**; context selectors personalize the one message; time-sensitive dated items are a **capped** secondary pass. `checkins` table (PK `userId`, SK `checkinId`, GSI `checkins_by_status` PK `status` SK `scheduledFor`). Consent/STOP/quiet-hours/frequency-cap. Dispatcher Lambda hourly, two passes. `checkinEnabled/checkinFrequency/checkinInactivityDays/lastMessageAt` on `users`.

**Underspecified / must decide (this is the most underspecified feature):**
- **`lastMessageAt` denormalization onto `users` does not exist today.** It must be written on **every inbound turn** (SMS *and* web) in the chat path. SMS texters who never registered have **no `users` item**, so the inactivity scan can only target registered users — confirm scope and the write site (chat_handler `process_chat_message`).
- **Inactivity scan mechanics:** §10.6 says scan opted-in users filtering `lastMessageAt <= now - threshold`. With a single `users` table keyed only by `userId`, this is a **`Scan` with filter** today — define the candidate query, the optional sparse `lastActiveBucket` GSI escape hatch, and the cooldown bookkeeping.
- **Cooldown / frequency-cap state:** where "last checked-in at" + per-period counts live (on `users`? derived from `checkins`?). Define the exact ceiling logic for `weekly`/`biweekly` and the time-sensitive ≤1/week cap.
- **Quiet hours + timezone** again depends on a stored tz.
- **Selector ranking** ("time-sensitive date > struggle > plan nudge > general") needs a concrete scoring function over Neon memories + DynamoDB prayers/plans.
- **Reply matching:** how a reply "flows back" and sets `responded` (match by phone + open `checkins` row within a window).
- **Message generation cost:** each send is an LLM call from worker context — confirm worker has the langchain layer + OpenAI key.

## F6. Journey View "My Walk" + Memory Manager/Delete (spec §11, §11.2a)

**Specified:** `GET /walk/summary` aggregates counts/recent items across tables (one Lambda, cached briefly). Memory controls: `GET /walk/memories`, `DELETE /walk/memories/{id}`, `DELETE /walk/memories` — read/delete Neon `user_memories` (single-store, pgvector row dropped with the row). Frontend `MyWalk.jsx` + `MemoryManager.jsx` exist.

**Underspecified / must decide:**
- **`/walk/summary` response schema** — `MyWalk.jsx` + sub-components (`ThemeCloud`, `PrayerSummary`, `ReflectionSummary`, `PlanProgressCard`, `MilestoneTimeline`, `DailyVerseCard`) imply a rich aggregate shape (themes, counts, recents, milestones, gentle prompts, upcoming check-ins). Codify it; it touches **both** stores.
- **Milestones + gentle prompts** are auto-generated — define the generation rules (derived on read? materialized?).
- **Caching**: "cached briefly" — where (in-Lambda memo? a TTL attr?) and invalidation.
- **`GET /walk/memories` shape** + whether `reflections` are exposed under a secondary tab (spec says optional).
- **Delete confirmation/audit** for GDPR/CCPA right-to-be-forgotten — log the delete.

## F7. Settings / Comms Preferences / Response Style (spec §12)

**Specified:** Fix `Settings.jsx handleSaveChanges` (currently `setTimeout`, never calls API) → `PUT /users`. Mount the unused `CommunicationPreferences.jsx`, back it with `users`-item attrs (§4.4) via `GET/PUT /users/preferences`. Response style (tone/length) injected into system prompt like `bibleVersion`.

**Underspecified / must decide:**
- **`/users/preferences` vs `PUT /users`:** §12 implies a dedicated preferences route, but §5.4 says the attrs live on `users` and reuse the existing update path (no new endpoint). **Resolve the contradiction** — recommend reusing `PUT /users`/`GET /users` (the generic update path already writes arbitrary attrs) and treating `/users/preferences` as either an alias or dropped. Document the decision.
- **`responseStyle` shape:** frontend mock uses an object `{tone, length}`; user model field is `response_style`. Lock the attribute name/shape (camelCase `responseStyle` object recommended) and the prompt-injection text.
- **Attribute defaults + validation** for the §4.4 list (e.g. `dailyVerseTime` format, `checkinFrequency` enum).
- **Naming convention:** *Decided (ADR-1, below)* — **camelCase** for DynamoDB attributes/keys (matches existing data + frontend), **snake_case only inside Neon SQL**. So `responseStyle`, `bibleVersion`, etc. on the `users` item.

## F8. Account-management chat tools (spec §5.4)

**Specified:** `set_daily_verse`, `set_checkin_frequency`, `update_bible_version`, `set_response_style`, `pause/resume_reading_plan`, `get_account_status`. All mutate the same `users` attrs as web settings (parity). Confirm-then-apply read-back; billing stays out of chat (return Stripe portal link / STOP path); TCPA audit trail (`source=chat`, timestamp); idempotent.

**Underspecified / must decide:**
- **Audit trail mechanism** — there is none today. Decide: an `audit` list attr on `users`, a new audit table, or a log sink. The spec mandates it.
- **Natural-language mapping** for `set_checkin_frequency` ("less often" → which `checkinInactivityDays`?) — define the mapping table.
- **Tool error/permission behavior** (e.g., enrolling/pausing a plan the user doesn't have).
- **`get_account_status`** needs SMS usage (lives in `sms_usage` table) + plan + prefs + prayer/plan snapshot → cross-table read contract.

## F9. Memory system: retrieval + extraction + embeddings (spec §5, §15.1a)

**Specified:** Episodic = DynamoDB `chat_messages` (loaded as today). Semantic = Neon `user_memories` + `reflections` (pgvector). Companion context block prepended to system prompt. Structured retrieval **primary**, vector **secondary**. Extraction = post-turn GPT-4o-mini → JSON (`memories/prayers/verses/suggest_checkin`), upsert with dedup + salience bump + embedding-on-write. Async on SMS, inline on web. No LangGraph Postgres checkpointer; degrade gracefully if Neon down.

**Underspecified / must decide:**
- **Extraction JSON contract** is a sketch — finalize the full schema, the exact prompt, and validation/coercion of the model output.
- **Dedup/upsert rule**: the spec says "vector similarity / fuzzy match on `summary`" but gives **no threshold, no distance metric choice at query time, no salience math** (how much to bump, decay cadence). Define them.
- **Embedding model + key**: OpenAI `text-embedding-3-small` (1536d) reusing the `gpt` secret. Confirm the OpenAI SDK is in the langchain layer (it is: `openai==1.109.1`) and add an embeddings call path.
- **Async-on-SMS mechanism**: a separate `memory_extractor` Lambda invoked async by the chat path, or `InvocationType='Event'` self-invoke — decide and wire IAM.
- **Degradation contract**: precise behavior when Neon connect fails (skip memory block, still answer, log, no user-visible error) — write it as a tested code path.
- **LangGraph node boundaries**: `guardrails → load_history(DDB) → retrieve_memory(Neon) → generate+tools → extract → persist`. Decide state schema and how the existing PostHog callback threads through nodes.
- **Connection management**: short-lived pooled connections via Neon **pooled endpoint**; per-invocation connect/close vs a module-level pool (Lambda concurrency caveat).

## F10. Backfill (spec §5.5)

**Specified:** One-off, idempotent batch script that **replays existing `chat_messages` through the live §5.2 extractor** (not a divergent path). Depends on Neon project + `NEON_DATABASE_URL` + the `user_memories` schema/connection module. Tiny scale (effectively one user with substantive history).

**Underspecified / must decide:**
- **Where it runs** (local script using the conda env, a one-off Lambda, or a notebook) and how it reads the live extractor without circular Lambda deps.
- **Batching/ordering** of `chat_messages` per user (chronological by `threadId`) and rate-limit handling for embeddings.
- **Verification** that re-running is idempotent (depends on the upsert rule from F9).

## F11. Landing / Features / How-It-Works / Pricing copy (spec §13)

**Specified:** New hero, companion value sections, pricing reframe to "personal Bible companion," update `LandingPage.jsx`/`FeaturesPage.jsx`/`HowItWorksPage.jsx`/`Subscription.jsx`. (Frontend mockup already has revised hero/carousel per git status.)

**Underspecified / must decide:**
- **Free vs Premium copy inconsistency** (§16 note): exhaustion page markets "Web Chat (Free & Unlimited)" while `Chat.jsx` enforces a 3-message trial. **Pick one and make copy + enforcement match.**
- **Whether to add a cheaper "daily-verse-only" tier** (Appendix A open question) — decide in/out for v1.
- **Incremental shipping** so marketing never over-promises a not-yet-live feature.

---

## Spec inconsistencies & open decisions found (flagged)

1. **`/users/preferences` vs `PUT /users`** — §14 lists `GET/PUT /users/preferences`, but §4.4 + §5.4 say prefs are plain `users` attrs written by the existing update path with "no new endpoint." Pick one (recommend: reuse `PUT/GET /users`).
2. **Naming convention drift** — *RESOLVED (ADR-1):* **camelCase** for all DynamoDB attributes/keys (e.g. `bibleVersion`, `eventDate`, `phoneNumber`, `scheduledFor`); **snake_case only inside Neon SQL** (`user_memories`, `reflections` columns). Spec-inherited snake_case in the DynamoDB parts of this plan is normalized to camelCase.
3. **`langgraph` missing from the langchain layer's `requirements.txt`** even though the layer description and §15.3 assume it. Must be added before any LangGraph code deploys.
4. **`lastMessageAt` ambiguity** — it already exists on `chat_sessions` (web only, set in `update_session_metadata`) but §10/§4.4 want it on the **`users`** item driven by *all* inbound (incl. SMS). These are different fields; don't conflate.
5. **Extraction model** — §5.2 specifies GPT-4o-mini for extraction while the main agent uses `gpt-4o`; confirm the cheaper model for extraction and that cost is acceptable (it is, per §16.1 which excludes inference but margins are healthy).
6. **Check-in scope vs unregistered texters** — inactivity scan needs a `users` item + opt-in; unregistered SMS users have neither. Spec implicitly limits check-ins to registered/subscribed users — state it.
7. **Free web gating** — §16 itself flags the "Free & Unlimited" vs 3-message-trial contradiction.
8. **Secret-read divergence** — `shared/secrets_helper.get_secret(key)` vs `chat/helpers.get_secret()` (whole dict). Adding `neon_database_url` must work for both worker and chat lambdas.
9. **Neon provisioning** — *Decided (ADR-2):* Neon **projects are created manually per env** (no Neon Terraform provider, **no TF version bump** — keep `>= 1.3.0`). Terraform manages only the `neon_database_url` secret + Lambda wiring + the layer Postgres driver; schema is applied by an out-of-band migration script. See Part 2.

---

## Part 1 — Consolidated gap checklist

**Data model / DynamoDB**
- [x] **RESOLVED (ADR-1):** attribute naming is **camelCase** for all DynamoDB attributes/keys; **snake_case only inside Neon SQL**.
- [ ] Finalize `users` additions: `phoneNumber` attribute + `phoneNumber` GSI (projection list); comms-pref attrs (§4.4) with types/defaults; `lastMessageAt`; `lastDailyVerseAt`; `responseStyle` object; `timezone`; audit mechanism.
- [ ] Finalize `verse_history` schema + the pre-registration `phoneNumber` keying/GSI + reconciliation-on-registration hook.
- [ ] Finalize `prayers` schema (atomic `prayCount` increment) + free-tier 3-prayer cap enforcement.
- [ ] Finalize `checkins` schema + `checkins_by_status` GSI (attribute defs `status`,`scheduledFor`) + cooldown/cap bookkeeping location.
- [ ] Decide reading-plan catalog: DynamoDB table vs seed config; author day content for all 7 plans; finalize `user_reading_plans` / `user_reading_plan_progress` shapes.
- [ ] Add IAM statements for every new table + GSI (read/write) to the lambda role.

**Neon / schema**
- [ ] Finalize `user_memories` + `reflections` DDL (as in §4.1) and an **idempotent migration runner** (extension + tables + HNSW indexes), run out-of-band per env — no TF provider involved (ADR-2).
- [ ] Decide connection driver (`psycopg[binary]` vs `pg8000`) + add to the langchain layer; add `pgvector` python adapter or manual casting.
- [ ] Define connection lifecycle (pooled endpoint, per-invoke connect/close) + degradation-on-failure contract.

**Agent / memory**
- [ ] Specify LangGraph state schema + node boundaries; port PostHog tracing.
- [ ] Finalize extraction prompt + full JSON contract + output validation.
- [ ] Define dedup/upsert: distance metric, similarity threshold, fuzzy-`summary` rule, salience bump/decay math.
- [ ] Define embedding-on-write + failure/backfill-retry mechanism.
- [ ] Decide async-on-SMS extraction mechanism (separate `memory_extractor` lambda vs async self-invoke) + IAM.
- [ ] Implement `lastMessageAt`-on-`users` write on every inbound turn (SMS + web), scoped to registered users.

**API**
- [ ] Author request/response JSON + status codes for **every** new endpoint (prayers, reflections, plans, walk, walk/memories, preferences).
- [ ] Define per-endpoint auth (JWT) + subscription gating (free vs premium) + the 402/limit responses.
- [ ] Resolve `/users/preferences` vs `PUT /users`.

**Agent tools (§5.4)**
- [ ] Define each tool's args, the `users`-attr writes, NL mapping (esp. `set_checkin_frequency`), read-back text, idempotency, and audit-trail write.
- [ ] Define `get_account_status` cross-table read (sms_usage + users + prayers + plans).

**Check-ins**
- [ ] Define inactivity candidate query (+ optional `lastActiveBucket` GSI), selector ranking function, cooldown/cap logic, quiet-hours/tz handling, reply-matching, and worker LLM/secret/layer wiring.

**Workers / infra**
- [ ] EventBridge Scheduler design + timezone bucketing for daily-verse / plan-delivery / check-in dispatcher.
- [ ] Decide consolidated companion REST lambda vs per-feature lambdas (cold-start vs blast radius).
- [ ] `neon_database_url` flow into Secrets Manager + reconcile both `get_secret` helpers.

**Frontend wiring**
- [ ] Replace `CompanionContext` mock mutators with a real authed API client; keep component props stable; add loading/error states; gate premium screens; reconcile free-web copy vs enforcement.

**Backfill**
- [ ] Decide runner + batching/ordering + verify idempotency.

**Testing**
- [ ] Unit: extraction parsing/dedup, retrieval assembly, gating, tool writes, dispatcher selection/caps.
- [ ] Integration: Neon up/down degradation, GSI queries, end-to-end SMS + web turns.
- [ ] Manual env verification gates per phase (see Part 3).

---

# Part 2 — Neon provisioning (manual projects + Terraform-managed secret/wiring only)

> **Decision (ADR-2):** Neon **projects are created manually, one per environment**. There is **no Neon Terraform
> provider** and **no Terraform version bump** (keep `>= 1.3.0`). Terraform owns only the connection-string secret +
> Lambda wiring + the layer Postgres driver. (For reference, a maintained community provider does exist —
> `kislerdm/neon` — but it requires Terraform ≥ 1.14, can't run SQL, and stores the connection URI/passwords in TF
> state; we deliberately **do not** use it here.)

## 2.1 What is manual vs. Terraform-managed

| Concern | Owner | Notes |
|---|---|---|
| Neon **project** (one per env: dev/staging/prod) | **Manual** (Neon console/CLI) | Operator creates it and copies the **pooled connection URI**. |
| `vector` extension + 2-table schema + HNSW indexes | **Migration script** (out-of-band) | Idempotent psycopg/pg8000 runner; not Terraform; not a TF provider. |
| `neon_database_url` in Secrets Manager | **Terraform** | New key on the existing per-env secret. |
| Lambda secret/env access (IAM already scopes `SECRET_ARN`) | **Terraform** | Workers/chat read `neon_database_url`. |
| Postgres driver in the LangChain layer | **Terraform** (layer build) | `psycopg[binary]` (or `pg8000`) + `pgvector` + `langgraph`. |

No Terraform code ever talks to Postgres or to the Neon control plane, so there is **no Neon API key in Terraform**,
no `kislerdm/neon` provider, and no version-floor change.

## 2.2 Environment topology — **one Neon project per env**

Keep **one Neon project per environment** (dev/staging/prod). It mirrors the existing per-env isolation model
(separate `backend.<env>.hcl`, separate `<env>.tfvars`, env-prefixed resource names) and gives true blast-radius
isolation for sensitive spiritual/PII data — a botched dev change can't touch prod, and each env has its own pooled
URI in its own secret. This is **not** one shared project with a branch per env (cheaper, but couples compute and
makes a single project deletion or credential compromise span all envs). Use Neon branching for ephemeral dev
previews if desired, not as the environment boundary. Enable branch protection on the prod project (paid plans).

## 2.3 Connection string → Secrets Manager → Lambdas

1. **Manual URI → secret (via Terraform).** After creating the env's Neon project, copy its **pooled** connection
   URI and put it into the env's Secrets Manager secret (`terraform/modules/secrets/main.tf`) as a new
   `neon_database_url` key. Add a `variable "neon_database_url"` to the secrets module and supply it per env. Two
   acceptable ways to populate it:
   - **Via `tf apply` with a sensitive var** — pass it in the env's `<env>.tfvars` (already gitignored) or via
     `TF_VAR_neon_database_url` so `tf-env.sh <env> apply` writes it into the secret. Simple and keeps the secret's
     contents under one apply. *(Caveat: the value lands in TF state — the S3 backend is already remote/encrypted; keep it that way.)*
   - **Out-of-band** — set the `neon_database_url` value directly in Secrets Manager (console/CLI) and have Terraform
     manage only the secret *resource* (not that key's value), referencing it by ARN. Avoids the URI in TF state.
   - **Recommend:** the sensitive-var route for consistency with the existing secret (which is already fully
     Terraform-managed), unless keeping the URI out of state is a hard requirement — then go out-of-band.
   Use the **pooled** URI (Lambda + Postgres needs pooling).
2. **Read in Lambdas.** Extend `lambdas/shared/secrets_helper.py` so workers/chat read `get_secret('neon_database_url')`.
   Note the chat path uses a *different* helper (`lambdas/chat/helpers.get_secret()` returning the whole dict, then
   `secrets.get(...)`) — reconcile both so chat/extraction lambdas and worker lambdas resolve the same key.
3. **`vector` extension + DDL.** Run the idempotent migration (§2.4) once per env *after* the project exists — this
   is out-of-band and **does not depend on any TF provider**.
4. **VPC?** **No.** Neon is public + TLS; the spec confirms no VPC needed. Use the pooled endpoint (PgBouncer-backed)
   for short-lived Lambda connections.
5. **Connection lifecycle.** Open a short-lived pooled connection per invocation (or a guarded module-level
   connection) and always degrade gracefully if connect fails.

## 2.4 Provisioning the schema (out-of-band migration script — no TF involved)

Add an **idempotent migration runner** (a `db/` or `migrations/` folder in `versiful-backend`):

```sql
-- 0001_init.sql (run once per env, idempotent) -- snake_case is correct here: Neon SQL (ADR-1)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS user_memories ( ... as spec §4.1 ... );
CREATE INDEX IF NOT EXISTS idx_memories_user_active ON user_memories(user_id, status, salience DESC);
CREATE INDEX IF NOT EXISTS idx_memories_embedding ON user_memories USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS reflections ( ... as spec §4.1 ... );
CREATE INDEX IF NOT EXISTS idx_reflections_user ON reflections(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reflections_embedding ON reflections USING hnsw (embedding vector_cosine_ops);
```

Run it via a tiny Python runner using the chosen driver against `neon_database_url` — e.g. a manual
`python migrate.py <env>` step in the deploy runbook (§2.5). It is **fully decoupled from Terraform** (no
`null_resource`, no provider), so `terraform apply` never depends on DB connectivity. This same runner + connection
module is the prerequisite for the §5.5 backfill.

## 2.5 Manual per-env runbook

Do this **once per environment** (dev → staging → prod), before promoting any app code that reads Neon to that env:

1. **Create the Neon project** (Neon console or CLI), named e.g. `versiful-companion-<env>`, region matching AWS
   (e.g. `aws-us-east-1`), Postgres 16, with a pooled endpoint enabled. (Manual — not Terraform.)
2. **Copy the pooled connection URI** for that project's default branch/database/role.
3. **Populate the env's Secrets Manager secret** with `neon_database_url` = that pooled URI — either by setting the
   sensitive Terraform var and running `cd terraform && ../scripts/tf-env.sh <env> apply`, or out-of-band in Secrets
   Manager (§2.3 step 1).
4. **Run the migration script** against that URI (`python migrate.py <env>`) to create the `vector` extension, the
   `user_memories` + `reflections` tables, and the HNSW indexes (idempotent).
5. **Ready for backfill** (§5.5): with the schema in place and `neon_database_url` resolvable, run the one-off
   backfill to replay existing `chat_messages` through the live extractor.

> Security note: the pooled URI contains credentials. If using the Terraform sensitive-var route it lands in TF
> state — keep the S3 state backend encrypted + access-controlled (already the case). If that's unacceptable, use the
> out-of-band route so the value never enters state.

## 2.6 Postgres driver in the LangChain layer

- Add a driver to `lambdas/layers/langchain/requirements.txt`. Candidates:
  - **`psycopg[binary]` (psycopg3)** — modern, has manylinux2014 wheels (works with the existing `--platform manylinux2014_x86_64 --only-binary=:all:` build). Recommended.
  - **`pg8000`** — pure-Python, zero binary deps (smallest, most Lambda-portable) — a safe fallback if wheel/size issues arise.
- Add **`pgvector`** (Python) for the `vector` type adapter, or cast embeddings to the `vector` literal manually.
- **Also add `langgraph`** here (currently missing) for the agent refactor, and confirm total **layer size stays under the 250 MB unzipped Lambda limit** (the comment in `_layers.tf` flags this constraint). **Skip `langgraph-checkpoint-postgres`** per the spec (no Postgres checkpointer).

## 2.7 Where this fits in the `terraform/` tree (sketch — do not create yet)

```
terraform/
  modules/
    secrets/
      main.tf                  # add "neon_database_url" = var.neon_database_url to jsonencode
      variables.tf             # add variable "neon_database_url" (sensitive)
    lambdas/
      _workers.tf              # NEW: daily_verse_worker, reading_plan_delivery, checkin_dispatcher,
                               #      (optional) memory_extractor + EventBridge Scheduler schedules + IAM
      _companion_tables.tf     # NEW: prayers, verse_history, reading-plan tables, checkins (+ GSIs)
      _users_gsi.tf (or edit dynamodb module)  # add phoneNumber attr + GSI on users
  main.tf                      # pass var.neon_database_url into module "secrets"
                               # (NO neon provider, NO required_version change — keep >= 1.3.0)
```
There is **no `modules/neon/`** and **no `provider "neon"`** — the Neon project is created by hand (§2.5) and only
its pooled URI flows into Terraform as a sensitive variable.

---

# Part 3 — Build plan (sequenced, dependency-ordered)

**CICD rules honored throughout** (per `CICD_DEPLOYMENT_WORKFLOW.md`):
- **Same branch name in both repos** for any phase touching both.
- **Backend:** `feature/<name> → dev → main`. Deploy per env with `cd terraform && ../scripts/tf-env.sh <env> apply` (`plan` first for prod). **Staging deploys from the `dev` branch** (no backend staging branch).
- **Frontend:** `feature/<name> → dev → staging → main`, push auto-deploys, **never skip staging**, never merge feature→main directly.
- **Promotion gate each phase:** verify in dev → (staging) → prod before the next phase's prod deploy.
- **Neon:** **manually create** the env's Neon project, populate its `neon_database_url` secret (via `tf-env.sh <env> apply` with the sensitive var, or out-of-band), then run the migration script against that URI (§2.4–§2.5) **before** app code that reads Neon is promoted to that env.

### Phase 0 (prep, can start immediately, low-risk) — branch `chore/companion-foundation-prep`
- Add `langgraph` + `psycopg[binary]` + `pgvector` to the langchain layer `requirements.txt` (verify layer < 250 MB). Add the `neon_database_url` secret key + variable to the secrets module wiring (no value yet, or per-env value once projects exist). Record the naming decision (ADR-1) and the manual-Neon decision (ADR-2) — already captured in this doc. **No Terraform version bump and no Neon provider** (ADR-2). *Deploy: dev only to validate the layer build.* **Independent / parallelizable** with nothing blocking it.

## Phase 1 — Foundation: Neon + memory + LangGraph + backfill — branch `feature/companion-memory-foundation`
*Everything else depends on this. Highest effort.*

**Infra / Terraform (backend):**
- **Manually create the dev Neon project** (§2.5), copy its pooled URI, and add `neon_database_url` to the dev secret (Terraform-managed secret key — no Neon provider, no TF version bump).
- Add `phoneNumber` attribute + GSI on `users` (fixes §5.1 Scan + correctness bug); add `verse_history` table (needed early so extraction can record verses); add IAM for new resources.
- Run the **migration script** (extension + `user_memories` + `reflections` + HNSW) against the dev Neon URI (out-of-band, §2.4).

**Backend:**
- Neon connection module (pooled, degrade-on-failure) in shared code; reconcile both `get_secret` helpers.
- Refactor `agent_service.py` chain → LangGraph `StateGraph`: `guardrails → load_history(DDB) → retrieve_memory(Neon) → generate+tools → extract → persist`; port PostHog tracing; keep SMS/web prompt split.
- Memory retrieval node (structured-primary: salience/recency/status from Neon + verse_history dedup list from DDB; vector secondary).
- Extraction node + finalized JSON contract + dedup/upsert + salience math + embedding-on-write (`text-embedding-3-small`, reuse `gpt` key). **Async on SMS** (separate `memory_extractor` lambda or async self-invoke), **inline on web**.
- Write `lastMessageAt` onto the `users` item on every inbound turn (chat path), scoped to registered users.
- One-off **backfill** runner reusing the live extractor (depends on schema + connection module).
- `recall(query)` tool (vector) registered in the agent.

**Frontend:** none required this phase (memory is invisible until My Walk). Optionally none.

**Deploy & verify:** (manual dev Neon project + secret) + dev apply + migration → run a few SMS/web turns, confirm memories appear in Neon and recall works, confirm graceful degradation when Neon is unreachable; run backfill in dev; **then** (manual staging Neon project + secret) + staging apply + migration + verify; **then** (manual prod Neon project + secret) + main → prod apply + migration + verify. Run backfill in prod last.

**Parallelizable within Phase 1:** (a) the manual Neon project creation + secret wiring + migration script, and (b) the LangGraph refactor scaffolding can be built in parallel; they converge at the retrieval/extraction nodes. The `phoneNumber` GSI fix is fully independent and can land first.

## Phase 2 — Daily Verse + Settings/Prefs fixes + Response style — branch `feature/companion-daily-verse`
**Infra:** `daily_verse_worker` Lambda + EventBridge Scheduler (15-min, tz-bucketed) + IAM; add `lastDailyVerseAt`/comms-pref/`timezone`/`responseStyle` handling on `users` (attributes, no new table).
**Backend:** worker builds per-user context + exclusion list, sends, writes `verse_history` (`context='daily_verse'`); inject `responseStyle` into the system prompt like `bibleVersion`; confirm `GET/PUT /users` covers prefs (resolve the `/users/preferences` question).
**Frontend (both-repo branch):** fix `Settings.jsx handleSaveChanges` → real `PUT /users`; mount + wire `CommunicationPreferences.jsx`; add the response-style control; replace those `CompanionContext` mock mutators with the authed API client.
**Deploy & verify:** backend dev apply + frontend dev push → verify a scheduled verse + persisted settings; frontend dev→staging→main; backend staging→prod.
**Parallelizable:** worker (backend) and Settings wiring (frontend) are largely independent within the phase.

## Phase 3 — Prayer Journal + Reflection Log — branch `feature/companion-prayers-reflections`
**Infra:** `prayers` DynamoDB table + IAM; reflections use the Neon table from Phase 1 (no new infra). Decide consolidated companion REST lambda vs per-feature.
**Backend:** prayers handler + endpoints (atomic `prayCount`, gating); agent tools `save_prayer`/`list_active_prayers`/`mark_prayer_answered`; reflections endpoints + `log_reflection` tool + auto-summary; SMS keywords `PRAYERS` + `SAVE`; answered→thanksgiving-verse path (writes verse_history + reflection).
**Frontend:** wire `Prayers.jsx`/`PrayerCard`/`AddPrayerModal`/`AnsweredCelebration` and `Journal.jsx`/`ReflectionTimeline`/`AddReflectionModal` + the chat "save reflection" affordance to real endpoints; premium-gate.
**Deploy & verify:** dev → staging → prod per repo rules; verify chat `save_prayer` and web parity write the same data.
**Parallelizable:** Prayers and Reflections are independent slices — could even be two sub-branches if desired, but keeping them in one phase keeps the agent-tool registration in one place.

## Phase 4 — Reading Plans — branch `feature/companion-reading-plans`
**Infra:** catalog decision (table vs seed config) + `user_reading_plans` + `user_reading_plan_progress` tables + IAM; `reading_plan_delivery` worker + Scheduler.
**Backend:** plans endpoints (catalog public; enroll/progress/complete-day/pause authed); tools `enroll_reading_plan`/`get_reading_progress`/`pause`/`resume`; delivery worker (reuses tz/scheduler machinery); complete-day writes a Neon reflection. **Author the day content for all 7 plans.**
**Frontend:** wire `Plans.jsx`/`PlanDetail.jsx`/`PlanCard`/`PlanProgress`/`PlanDayCard`/`EnrollButton` to endpoints; premium-gate (1 trial plan free).
**Deploy & verify:** standard promotion; verify delivery + progress + reflection linkage.
**Parallelizable with Phase 3** (different tables/endpoints/screens) **once Phase 1–2 are live** — could run on a separate branch concurrently if two people are working, merging both to dev before staging.

## Phase 5 — Check-ins + My Walk (+ Memory Manager/Delete) — branch `feature/companion-checkins-mywalk`
*Highest compliance risk; depends on prayers/plans/memories data from prior phases.*
**Infra:** `checkins` table + `checkins_by_status` GSI + IAM; `checkin_dispatcher` worker (hourly) + Scheduler; ensure worker has langchain layer + OpenAI + Neon access.
**Backend:** inactivity scan (candidate query + optional `lastActiveBucket` GSI) + selector ranking + cooldown/cap/quiet-hours/STOP + reply matching + log rows; capped time-sensitive due-date pass (writes from extraction's `suggest_checkin`); `/walk/summary` aggregation (cached) + memory endpoints `GET /walk/memories`, `DELETE /walk/memories/{id}`, `DELETE /walk/memories` (single-store Neon deletes + audit); `get_account_status` + remaining §5.4 account tools + audit trail.
**Frontend:** wire `MyWalk.jsx` + `walk/*` components and `MemoryManager.jsx` (per-item delete + clear-all with confirm); check-in toggle/frequency/threshold already in CommunicationPreferences (Phase 2) — connect any remaining bits + "upcoming check-ins" preview.
**Deploy & verify:** deploy with check-ins **opt-in/off by default**; verify caps, quiet hours, STOP, and that deletes drop Neon rows; promote carefully (consider dev/staging soak before prod).

## Phase 6 — Landing / Features / How-It-Works / Pricing reposition — branch `feature/companion-landing-reposition`
*Frontend-led; mostly copy.* Reposition hero + add companion value sections + reframe pricing (`LandingPage`, `FeaturesPage`, `HowItWorksPage`, `Subscription`). **Resolve the free-web "unlimited vs 3-message-trial" copy/enforcement inconsistency.** Decide the cheaper daily-verse-only tier (in/out). Ship incrementally so copy never over-promises unshipped features. Frontend `dev → staging → main`.

## Parallelization summary
- **Independent now:** Phase 0 prep; the `phoneNumber` GSI fix; authoring reading-plan content; finalizing API contracts/ADRs (doc work).
- **Within Phase 1:** manual Neon project + secret wiring + migration script ∥ LangGraph refactor (converge at nodes).
- **Across phases:** Phase 3 (prayers/reflections) and Phase 4 (plans) are mutually independent once 1–2 land. Phase 6 copy can trickle out alongside 2–5.
- **Strictly sequential:** Phase 1 before everything; Phase 5 (My Walk/check-ins) after the data-producing phases (2–4).

---

## Appendix — quick reference of the repo facts the plan relies on
- Agent: single LangChain chain, `gpt-4o`, 1 tool, 10-msg window (`agent_service.py`, `agent_config.yaml`).
- Buggy phone lookup: `users_table.scan(... Limit=1)` in `chat_handler.process_chat_message`.
- `users` table = `userId` only; camelCase attrs; generic `PUT /users` writes arbitrary fields (`users/helpers.py`).
- Secrets: OpenAI under key `gpt`; `SECRET_ARN` env + scoped IAM; two divergent `get_secret` helpers.
- Layers built `manylinux2014_x86_64 / py3.11`; langchain layer **missing `langgraph`**.
- `lastMessageAt` exists on `chat_sessions` (web) — **not** on `users`.
- Frontend companion screens all exist; `CompanionContext` is mock-only (no network) → wiring target.
- Deploy: backend `tf-env.sh <env> apply` (staging from dev branch); frontend auto-deploys, never skip staging; same branch name across repos.
