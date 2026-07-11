# Costorah — Startup & User Guide

This document is the end-user-facing guide to Costorah: what it does, how to get started, what each supported provider actually gives you, and how to troubleshoot common problems. It is written from real, current behavior — every claim below is checked against the implementation in this repository, not the product's eventual vision.

**How to read the status markers used throughout this document:**

- ✅ **Implemented** — real, working, backed by a live backend endpoint and tested code path.
- 🟡 **Partially Implemented** — the mechanism is real, but has a disclosed scope limit (e.g. a provider validates credentials but cannot yet import usage volume).
- ⬜ **Planned** — does not exist in the codebase today. Named only because it's on the public roadmap (see `CLAUDE.md`'s "Future Roadmap — EP-26" section), not because any part of it has been built.

For the full engineering history and architecture reference behind every claim in this document, see `CLAUDE.md` in the repository root.

---

## 1. Introduction

### What Costorah is

Costorah is an AI-cost-observability platform. You connect your AI provider accounts (OpenAI, Anthropic, and others), Costorah pulls usage and cost data from them on a schedule, and it surfaces that data through dashboards, analytics, budgets, and alerts — so you can see exactly what your organization is spending on AI, broken down by provider, project, and model, without manually exporting CSVs from five different vendor consoles.

### What problem it solves

Teams that use multiple AI providers (OpenAI for one workload, Anthropic for another, maybe a self-hosted Ollama instance for a third) have no single place to see total AI spend, catch a cost spike before the monthly bill arrives, or hold a project to a budget. Costorah is that single place: one dashboard, one set of budgets and alerts, across every provider you connect.

### How usage collection works (✅ Implemented, for OpenAI and Anthropic)

Once you've connected a provider with a valid API credential, Costorah periodically calls that provider's own **organization-level usage API** (not your individual conversations — an aggregate usage report the provider itself exposes) and imports the resulting records into Costorah's database, matched against Costorah's own pricing catalog to compute cost. This can happen automatically on a schedule, or on demand via a "Sync now" button. See **§12 Usage Collection** and **§13 Analytics** for detail, and **§4/§5** for exactly which endpoint each provider's real usage import uses.

### How provider integrations work (✅ Implemented)

You give Costorah an API key (and, for some providers, an endpoint URL) for a given provider. Costorah encrypts that key at rest, validates it live against the provider before saving, and then uses it — on your behalf, from Costorah's own servers — to periodically pull usage data. Costorah never asks you to install anything to connect a provider; a connection is just a stored, encrypted credential plus a validation/sync loop.

### How analytics works (✅ Implemented)

Once usage data has been imported, Costorah's dashboard renders it as KPI cards, time-series charts, a provider/model/project breakdown, and an hour-of-day × day-of-week spend heatmap — all filterable by project, provider, and model, and all computed with real SQL aggregation over your imported usage records (see §13).

### How budgets work (✅ Implemented)

You can define a spending ceiling scoped to your whole organization, a specific project, a specific provider, or a specific model, over a period (daily/weekly/monthly/yearly/custom), with one or more percentage thresholds (e.g. 50%/75%/90%/100%). Costorah evaluates every enabled budget automatically after each usage sync and shows you real-time status, a linear spend forecast for the rest of the period, and how much daily budget you have left (see §14).

### How alerts work (✅ Implemented, dashboard notifications only)

When a budget crosses one of its configured thresholds, Costorah fires an alert into your organization's in-product notification center (the bell icon, and a dedicated Alert Center page) — acknowledgeable, resolvable, dismissible, and re-openable. Today, alert delivery is dashboard-only; email/Slack/Teams/Discord delivery channels are designed for but not yet built (see §15).

---

## 2. Getting Started

### Creating an account (✅ Implemented)

Sign up at `costorah.com/signup`. You'll choose an account type (see below) and, for a password account, provide an email and password. A password account is created immediately, but **does not receive an active session until its email is verified** — you'll land on a "check your email" screen, not directly in the product.

### Email Verification (✅ Implemented)

After registering with a password, Costorah sends a verification email (via Resend) with a link valid for 24 hours. You must click it and complete verification before you can log in — this is enforced at login time, not just suggested. If a link expires, `costorah.com/login` and the dashboard's own verification screen both offer a "resend verification email" action (rate-limited to prevent abuse).

### Google Login (✅ Implemented)

"Continue with Google" is available on both the website's login/signup pages and the dashboard's own login page. A Google sign-in is automatically linked to an existing Costorah account if the email matches, or creates a new account if it doesn't — and since Google has already verified the email, a Google account skips email verification entirely. **One thing a first-time Google signup must do that a password signup doesn't**: because Google never gives Costorah a password, a brand-new Google account is required to set one on first login (a mandatory one-time "Set a password" step) before reaching onboarding — this exists so the account always has a fallback sign-in method.

### Business vs Personal account (✅ Implemented)

At signup you choose:
- **Personal** (default) — a single-user experience. Costorah creates one private workspace for you; you'll never see an organization switcher, member management, or a "Workspace" settings tab, because there's exactly one member (you) and it's never intended to have more.
- **Business** — a real, multi-user team workspace, with a name you choose. You get everything a Personal account gets, plus the ability to invite teammates (with role-based permissions: Viewer/Member/Admin/Owner), manage members, and transfer ownership.

A Personal account can later upgrade to Business from Settings, without losing any data — the same workspace simply stops being marked "personal" and gains the collaboration features. There is currently no way to create a *second* additional business workspace beyond the one created at signup or at upgrade time (see the EP-26 roadmap in `CLAUDE.md` for planned multi-workspace support).

### Creating your first project (✅ Implemented)

Projects are an organizational bucket for spend — e.g. "Chatbot," "Internal Tools." From the Projects page, click "New project," give it a name, and optionally set a budget. Projects are not required before connecting a provider or seeing usage; they're a way to slice existing usage data further, and provider connections can optionally be scoped to a project.

### Connecting your first provider (✅ Implemented, capability varies by provider — see §3)

From the Connections page (or the onboarding wizard's "Connect your first provider" step), pick a provider, paste in an API key, and save. Costorah validates the key live against the provider before storing it and tells you immediately whether it's valid. See §3–§11 for exactly what each of the 7 supported providers requires and what Costorah can and cannot pull from it.

### Running your first sync (✅ Implemented)

Once a connection is validated, click "Sync now" on that connection (or "Sync all" for every connection in your organization) to pull usage data immediately, rather than waiting for the next scheduled sync. You'll see the sync's status, how many records/tokens/cost were imported, and any error, right on the Connections page.

### Viewing your dashboard (✅ Implemented)

The Overview page shows real-time KPI cards (total spend, today's spend, this month, total tokens/requests, active providers, projects, average cost per request), a getting-started checklist while your account is new, and — once you have real usage — spend trend/provider distribution/top-models charts and a recent-activity feed. Analytics gives you the same data with filtering, a token trend chart, a spend heatmap, and CSV export.

---

## 3. Supported AI Providers

Costorah has a real, working adapter for 7 providers. Every one of them supports **live credential validation** and goes through the **identical background sync pipeline** (checkpointing, retries, scheduling) — there is no special-cased "second-class" provider in how connections are managed. What genuinely differs between providers is whether Costorah can pull **usage volume** from them at all, because that depends entirely on whether the provider itself exposes a bulk, organization-level usage-history API — something outside Costorah's control.

| Provider | Auth type | Credential validation | Usage volume import | Notes |
|---|---|---|---|---|
| OpenAI | API key | ✅ Live (`GET /v1/models`) | ✅ Real (`GET /v1/organization/usage/completions`) | Full production support |
| Anthropic | API key | ✅ Live (`GET /v1/models`) | ✅ Real (`GET /v1/usage`, admin scope) | Full production support |
| Google Gemini (AI Studio) | API key | ✅ Live (`GET /v1beta/models`, live model catalog) | ⬜ None — no bulk usage API on this credential | Validates and syncs; live model list (EP-26.0.2); imports 0 usage records by design |
| Azure OpenAI | API key + endpoint | ✅ Live (deployments list) | ⬜ None — cost data lives in Azure Cost Management, a different credential | Validates and syncs; imports 0 usage records by design |
| OpenRouter | API key | ✅ Live (`GET /models`) | 🟡 Attempted — see below | Real, live-catalog model list; usage import calls a real endpoint, but its data may be empty depending on your key's permission level (EP-26.0.1) |
| Grok (xAI) | API key | ✅ Live (`GET /models`) | ⬜ None — no documented bulk usage API | Validates and syncs; imports 0 usage records by design |
| Ollama | None (local/self-hosted) | ✅ Live (reachability check, `GET /api/tags`) | ⬜ None — free, self-hosted, no billing concept | "Validation" here means "is the server reachable," not "is a secret correct" |

**Why 4 of 7 providers show zero usage volume by design — and why that's not a bug.** Costorah's sync engine calls every connected provider's real, live usage-history API on every sync — there is no code path that skips a provider or fakes results. For OpenAI and Anthropic, that API exists and returns real per-request usage data. For Google, Azure, Grok, and Ollama, no equivalent bulk, key-scoped usage-history endpoint exists on the provider's own platform at all today — Google's cost data lives behind Cloud Billing/BigQuery (a different credential entirely), Azure's behind Azure Cost Management (ARM auth, not the API key you connect), Grok has no documented bulk endpoint, and Ollama is free/local with no billing concept at all. Costorah will not fabricate per-model or per-date breakdowns from an aggregate number — that would misrepresent your actual spend. If any of these platforms ships a real bulk usage API in the future, wiring it in requires implementing exactly one new adapter method — no architecture change.

**OpenRouter is a special case, as of the EP-26.0.1 update.** Unlike the four providers above, OpenRouter does have a real, documented usage-history endpoint (`GET /api/v1/activity`), and Costorah's sync now calls it on every sync, importing real per-model, per-day usage when it succeeds. However, that endpoint may require a more privileged credential type ("management key") than the standard API key you paste into the Connect Provider form — this was not fully confirmed against a live account before shipping (see the "Limitations" note in the OpenRouter section below). In practice this means: **if your key has sufficient permission, OpenRouter usage import works exactly like OpenAI/Anthropic's; if it doesn't, your connection will show "healthy" and sync successfully but import 0 records — the same honest "nothing to report" outcome the four zero-volume providers show, not an error.** Check your connection's sync status and "Last error" field on the Connections page to tell the two cases apart.

For each provider, the sections below cover: supported authentication, where to find/create your API key, required permissions, current usage-collection capability, and limitations.

### Google Gemini (AI Studio) — account setup and connection walkthrough

**Platform vs. Vertex AI — read this first.** "Google Gemini" in Costorah means one specific product: **Google AI Studio / the Gemini Developer API** (`generativelanguage.googleapis.com`), authenticated by a simple API key. It is **not** Google Cloud's **Vertex AI** — a separate, much larger enterprise ML platform that uses OAuth/GCP-service-account credentials instead of an API key, and that exposes Gemini through a different endpoint with genuinely richer, GCP-Cloud-Billing-backed usage telemetry. Costorah's dashboard shows this distinction directly on each Google connection as **Provider: Google · Platform: AI Studio · Service: Gemini API** — a label that exists specifically to make clear this is the AI Studio integration, not a (not-yet-built) Vertex AI one. If your organization uses Vertex AI Gemini instead of a plain AI Studio key, Costorah cannot connect to it today — see "Future: Vertex AI" below.

**How to create a Google AI Studio account.** Go to [aistudio.google.com](https://aistudio.google.com) and sign in with any Google account — no separate signup, no credit card required to start (AI Studio has a free tier for low-volume use).

**How to generate an API key.** In AI Studio, click **Get API key** (left sidebar) → **Create API key**. You can create it under a new or existing Google Cloud project; if you want billed, higher-rate-limit usage rather than the free tier, link it to a GCP project with billing enabled. Copy the key immediately (it starts with `AIza...`).

**How to connect it to Costorah.** Connections → Add connection → Google Gemini, paste the key, save. Costorah validates it live against `GET /v1beta/models` before storing it — the identical endpoint used for both validation and model discovery.

**Supported models.** As of EP-26.0.2, Costorah pulls Google's **live model catalog** (`GET /v1beta/models`, paginated) rather than a fixed list — every model your key currently has access to is discovered automatically, including context-window and output-token limits Google reports per model. If the live call ever fails (network issue, or Google's API being briefly unreachable), Costorah falls back to a small static list of the most current, well-known Gemini models (currently Gemini 2.5 Pro / Flash / Flash-Lite) so the Connect Provider form is never empty — but the live catalog is always the primary source.

**Usage collection.** ⬜ **Not available.** Google's AI Studio / Gemini Developer API has no bulk, key-scoped usage-history endpoint — there is nothing for Costorah to call. Your Google connection will validate successfully, show "healthy," and sync on schedule exactly like every other provider — it will just import 0 usage records, honestly, every time. This is not a bug, a missing feature, or a broken integration; it's a real gap on Google's own AI Studio API surface, re-confirmed as part of EP-26.0.2's research. The data that *would* answer "how much did I spend on Gemini" lives in a different Google product (Vertex AI's Cloud Billing / Billing Export to BigQuery), which requires a different credential type than the API key you connect here — see "Future: Vertex AI" below.

**Limitations.**
- No usage/cost data is imported for Google connections, ever, under the current AI Studio integration — by design, not a defect. Track your actual Gemini spend via [Google AI Studio's own usage page](https://aistudio.google.com) or your linked GCP project's Cloud Billing console in the meantime.
- The live model catalog reflects whatever models your specific API key/project currently has access to — Google occasionally deprecates or renames models faster than most providers; a model that disappears from the live catalog will also disappear from Costorah's Connect Provider form automatically (no code change needed on Costorah's side).
- Pricing (cost-per-token) for Gemini models must still be seeded into Costorah manually via the admin pricing API — Google's `models.list` response does not include per-token pricing the way OpenRouter's does.

**Future: Vertex AI (not built yet).** A second, separate "Platform: Vertex AI · Service: Gemini Enterprise" integration is the natural next step for organizations that need real Gemini usage/cost data — Vertex AI's Cloud Billing Export gives GCP customers exactly the bulk, queryable usage history AI Studio lacks. This would be a distinct connectable service (OAuth/service-account auth, GCP-project-scoped) layered on top of the same `Provider: Google` umbrella, never merged with the AI Studio integration above. Not started — see CLAUDE.md's EP-26.0.2 section for the full architecture reasoning.

### OpenRouter — account setup and connection walkthrough

**How to create an OpenRouter account.** Go to [openrouter.ai](https://openrouter.ai) and sign up (Google/GitHub/email). OpenRouter is a routing/gateway service in front of dozens of underlying AI vendors (Anthropic, OpenAI, Google, DeepSeek, Mistral, Qwen, Meta/Llama, xAI/Grok, and more) — one account, one API key, one bill, routed to whichever model you request.

**How to generate an API key.** In the OpenRouter dashboard, go to Settings → Keys → Create Key. Name it (e.g. "Costorah"), copy it immediately.

**How to connect it to Costorah.** Connections → Add connection → OpenRouter, paste the key, save. Costorah validates it live against `GET /models` before storing it.

**Supported models.** Costorah pulls OpenRouter's **live model catalog** (`GET /models`) rather than a fixed list — every model OpenRouter currently routes to is visible, including real-time per-token pricing OpenRouter itself publishes. Because OpenRouter is a gateway, its model identifiers are `vendor/model` slugs (e.g. `anthropic/claude-sonnet-4`, `openai/gpt-4o`, `google/gemini-2.5-pro`, `deepseek/deepseek-r1`). Costorah's Analytics page shows these split into "Underlying Vendor" and "Model" (e.g. **Anthropic** / **Claude Sonnet 4**) rather than the raw slug, so you can see who's actually serving each request even though it's routed through OpenRouter.

**Usage collection.** Costorah's sync calls OpenRouter's `GET /api/v1/activity` endpoint on every sync, requesting one day at a time for up to the last 30 days (OpenRouter's own retention window). ⚠️ **Disclosed limitation**: whether your standard OpenRouter API key has enough permission to call this endpoint was not confirmed against a live account before this feature shipped (OpenRouter's own documentation describes it as needing a "management key," a more privileged credential type) — see the "OpenRouter is a special case" note above. If your key works, you'll see real per-model daily usage on your dashboard exactly like OpenAI/Anthropic; if it doesn't, your connection stays healthy but imports 0 records, with the reason visible in the connection's sync status.

**Limitations.**
- Usage import's actual data depends on your specific API key's permission level (see above) — this is the one provider connection where "0 records imported" doesn't unambiguously mean "no usage happened."
- OpenRouter's own credential-validation endpoint (`GET /models`) is unauthenticated on OpenRouter's side — a successful connection save confirms the key is reachable and well-formed, not that it's genuinely valid (a truly invalid key is only caught the first time it's actually used to make a request).
- Costorah does not fabricate a vendor/model breakdown from any aggregate number — if usage import isn't working for your key, you will see zero records, never an invented estimate.

### Provider Validation Matrix (EP-26.0.2.1)

Every row below was verified by reading and exercising the actual adapter/service code for that provider (unit + lifecycle tests, all hermetic via mocked HTTP transports — see CLAUDE.md's EP-26.0.2.1 section for the full methodology). No live OpenAI/Anthropic/Google/OpenRouter/Azure/Grok credential was available in this sandbox at validation time; every "✅" below reflects a passing, mocked-but-realistic test exercising the real code path, not an assumption.

| Provider | Historical Usage | Live Sync (pipeline runs) | Model Discovery | Health Check | Scheduler | Analytics | Budgets | Alerts | Known Limitations | Recommended Account Type |
|---|---|---|---|---|---|---|---|---|---|---|
| OpenAI | ✅ Real | ✅ | ✅ Live (`GET /v1/models`) | ✅ Live | ✅ | ✅ | ✅ | ✅ | None beyond needing an org-level key with usage-read access. | Standard API key, org billing enabled. |
| Anthropic | ✅ Real | ✅ | ✅ Live (`GET /v1/models`) | ✅ Live | ✅ | ✅ | ✅ | ✅ | Usage import requires an **Admin**-scoped key (`GET /v1/usage`) — a normal workspace key can validate and sync but will import 0 records. | An **Admin** API key, not a regular workspace key. |
| Google Gemini (AI Studio) | ⬜ Unavailable (no bulk usage API on this credential) | ✅ (runs the real pipeline, imports 0 records honestly) | ✅ Live (`GET /v1beta/models`, paginated, EP-26.0.2) | ✅ Live | ✅ | ✅ (renders correctly with 0 usage) | ✅ (usable, will just never trigger from Gemini spend) | ✅ (usable, same caveat) | No usage/cost data, ever, on this credential — a real Google platform gap, not a Costorah defect. See §3's Google walkthrough. | Any AI Studio key — this limitation is independent of account tier. |
| OpenRouter | 🟡 Attempted, real when the key has permission | ✅ | ✅ Live (`GET /models`) | ✅ Live (but unauthenticated on OpenRouter's side, so it only confirms reachability, not validity) | ✅ | ✅ | ✅ | ✅ | Usage import depends on the key's permission level for `GET /api/v1/activity` — see §3's OpenRouter walkthrough; not fully confirmed against a live account. | A key with confirmed "management"-level access, if you want real usage import; a standard key still works for validation/model-browsing. |
| Azure OpenAI | ⬜ Unavailable (cost data lives in Azure Cost Management, a different credential) | ✅ (runs the real pipeline, imports 0 records honestly) | 🟡 Static list (verified via code read — `list_models()` is not a live catalog call; health check *is* live against the deployments endpoint) | ✅ Live (deployments list) | ✅ | ✅ (renders correctly with 0 usage) | ✅ | ✅ | Requires both an API key and the resource endpoint (`base_url`) to validate at all — a config-validation failure, not a network error, if the endpoint is missing. Model discovery is a static list, unlike OpenAI/Anthropic/Google/OpenRouter/Ollama's live catalogs — a real gap this EP found, not previously documented; see CLAUDE.md's EP-26.0.2.1 section. | An Azure OpenAI resource with at least one deployed model. |
| Grok (xAI) | ⬜ Unavailable (no documented bulk usage endpoint) | ✅ (runs the real pipeline, imports 0 records honestly) | 🟡 Static list (verified via code read — `list_models()` is not a live catalog call) | ✅ Live | ✅ | ✅ (renders correctly with 0 usage) | ✅ | ✅ | No usage/cost data — an xAI platform gap. Model discovery is a static list, same gap-class as Azure above. | Any xAI API key. |
| Ollama | ⬜ N/A (free, local, no billing concept) | ✅ (runs the real pipeline, imports 0 records honestly) | ✅ Live (`GET /api/tags`) | ✅ Live (reachability only — no credential to validate) | ✅ | ✅ (renders correctly with 0 usage) | ✅ (usable, will just never trigger) | ✅ (usable, same caveat) | "Health check" here means "is the server reachable," not "is a secret correct" — Ollama has no secret. | A reachable, running local/LAN Ollama server — no account needed. |

**Reading this table**: every ✅ in every column except "Historical Usage" means the code path is real, wired, and was exercised (by real tests against realistic mocked responses, or by reading and confirming the shared pipeline it reuses) — not that live usage data flows for that provider. "Live Sync (pipeline runs)" is deliberately a separate column from "Historical Usage": every provider without exception goes through the identical `ProviderSyncService` → `UsageCollectionService` pipeline on every sync (EP-24.3), so "the sync ran successfully" and "usage records were imported" are two different, independently-true-or-false facts — a provider can be ✅ on the former and ⬜ on the latter, and the dashboard is designed to make that distinction visible (via the "Usage API"/"No usage API" badge and each connection's own sync status) rather than implying usage exists where it doesn't.

---

## 4. OpenAI

**Status: ✅ Full production support** — credential validation and real usage import.

### How to create an OpenAI API key

1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys) (requires an OpenAI account with billing set up).
2. Click "Create new secret key," name it (e.g. "Costorah"), and copy the key immediately — OpenAI only shows it once.

### How to connect it

In Costorah, go to Connections → Add connection → OpenAI, paste the key, and save. Costorah validates it immediately against `GET /v1/models` and tells you if it's invalid.

### How usage gets collected

Costorah's usage sync calls **`GET /v1/organization/usage/completions`** — OpenAI's organization-level usage-reporting endpoint. This means the data returned is scoped to your whole OpenAI organization, not just calls made through Costorah's connection — **any usage on that OpenAI account, from any client (your own app, a script, another tool using the same org's key), will appear in Costorah**, because the endpoint reports at the organization level. This is important context for §6–§10 below: a tool that uses an API key from the *same OpenAI organization* Costorah is connected to will have its usage reflected automatically, with no separate integration needed.

### How Costorah calculates tokens

Each usage record returned by OpenAI includes prompt/completion token counts; Costorah stores these directly, split by input and output token type, per model, per day.

### How Costorah calculates costs

Costorah maintains its own pricing catalog (`ModelPricing`, keyed by provider + model) with per-token rates. Every imported usage event is matched against this catalog to compute cost. **If a specific OpenAI model has no pricing entry yet, Costorah still imports the usage event — with token counts intact — but no cost is calculated for it** (this is a disclosed, deliberate "fail open" behavior, not a bug: an unpriced model is still visible in your usage data, just without a dollar figure attached until pricing is added).

---

## 5. Anthropic

**Status: ✅ Full production support** — credential validation and real usage import.

### How to create an API key

1. Go to the [Anthropic Console](https://console.anthropic.com/) → Settings → API Keys.
2. Create a new key.
3. **Important**: Costorah's usage-import call requires an **Admin API key** (Anthropic's `/v1/usage` endpoint requires admin scope). A standard, non-admin API key can still be validated and connected, but if it lacks admin scope, Costorah's sync will honestly return zero usage records for it rather than erroring — check your key's role in the Console if usage isn't appearing.

### Everything relevant, by product surface

- **Claude Web** (chat.claude.ai) — a browser chat product with no API key at all. Not trackable by Costorah in any way. See §7.
- **Claude API** (the developer API at `api.anthropic.com`) — what Costorah connects to and monitors, as described above.
- **Claude Console** (console.anthropic.com) — where you manage API keys and billing. Not itself a source of usage; it's the management surface for the API key Costorah uses.
- **Claude Code** — Anthropic's terminal-based coding agent. See §6 for the full breakdown of what can and can't be monitored, depending on how it's authenticated.
- **Claude CLI** — if this refers to a tool authenticating with an Anthropic API key from the same organization as your connected Costorah credential, its usage is included in the same organization-level usage report described above. If it authenticates via a Claude.ai (Pro/Max) subscription login instead of an API key, its usage is not trackable — see §6 and §7.

### What Costorah can monitor

Any usage billed against the **same Anthropic organization/workspace** as the API key you've connected — regardless of which specific tool or script made the call — because Anthropic's usage endpoint reports at the organization level, not per-request-source.

### Limitations

- Requires an Admin-scoped API key for usage data to populate at all.
- Cannot distinguish "Claude Code called this" from "my own script called this" — the usage report has no per-tool attribution; it's organization-wide.
- Cannot see anything from Claude.ai's subscription-based products (Pro/Max chat, browser conversations) — those aren't billed through the API and have no usage-API equivalent.

---

## 6. Claude Code

Claude Code can be run in several different ways, and **whether Costorah can monitor its usage depends entirely on how it's authenticated — not on where it's running.**

### A. Claude Code in a terminal (local)

- **If authenticated with an Anthropic API key** (from the same organization/workspace as a connection you've validated in Costorah): ✅ its usage is included automatically in Costorah's next sync, via the organization-wide usage report described in §5. No separate setup, because Costorah never talks to Claude Code directly — it only ever talks to Anthropic's own usage API.
- **If authenticated via a Claude.ai subscription login** (Pro/Max plan, not an API key): ⬜ not trackable. Subscription-based usage has no equivalent bulk usage-history API Costorah can call.

### B. Claude Code inside Docker

Same rule as (A) — Costorah has no awareness of *where* the process runs (a container, a VM, bare metal). What matters is exclusively which credential Claude Code authenticates with. Running it in Docker changes nothing about trackability.

### C. Claude Code inside other containers/sandboxes

Same rule as (A) and (B) — identical reasoning.

### D. Claude Code Remote Development

Same rule again — a remote/cloud dev environment running Claude Code is trackable under exactly the same condition: an API key from an organization Costorah has a connected, valid credential for.

### Summary table

| Scenario | If using an API key (same org as a Costorah connection) | If using a Claude.ai subscription login |
|---|---|---|
| Terminal | ✅ Tracked (via org-wide usage report) | ⬜ Not tracked |
| Docker | ✅ Tracked | ⬜ Not tracked |
| Other containers | ✅ Tracked | ⬜ Not tracked |
| Remote dev | ✅ Tracked | ⬜ Not tracked |

### What gets tracked vs. what doesn't

**Tracked**: aggregate token counts and cost, attributed to whatever model was called, on whatever date — exactly the same shape of data as any other API usage on that organization.
**Not tracked**: which specific tool, session, or terminal invocation produced the usage (Anthropic's usage API has no per-client-application attribution); the content of any conversation or prompt (Costorah only ever imports aggregate usage/cost metadata, never prompt/response content, for any provider); anything authenticated via a Claude.ai subscription rather than an API key.

---

## 7. Claude Web

"Claude Web" (chat.claude.ai) is Anthropic's consumer chat product — the direct equivalent of ChatGPT's web interface, not the developer API.

- **Normal chat usage / "ChatGPT-style" usage**: a signed-in browser conversation at claude.ai. ⬜ **Cannot be monitored by Costorah under any circumstance** — there is no API involved at all; nothing is ever sent to any endpoint Costorah could poll.
- **Pro Plan / Max Plan**: subscription tiers of Claude.ai. Same limitation — these are billed and used entirely outside the API surface Costorah connects to.
- **API usage**: if you separately use the Anthropic *API* (not Claude.ai) with a key from a connected organization, that usage is tracked exactly as described in §5/§6 — but this is a fundamentally different product from Claude Web itself.

**Clarification, stated plainly**: normal browser conversations at claude.ai (or any AI provider's own consumer chat product) cannot be tracked by Costorah unless that usage is routed through the provider's developer API. There is no workaround for this — it isn't a missing feature, it's a boundary of what any third-party observability tool can see, since consumer chat products don't expose per-account usage telemetry to anyone but the provider itself.

---

## 8. OpenAI ChatGPT

Mirrors §7's distinction exactly, for OpenAI's own consumer product line.

| Tier | Trackable by Costorah? |
|---|---|
| ChatGPT (free) | ⬜ No |
| ChatGPT Plus | ⬜ No |
| ChatGPT Pro | ⬜ No |
| ChatGPT Team | ⬜ No |
| ChatGPT Enterprise | ⬜ No |
| **API Platform** (platform.openai.com, i.e. the developer API) | ✅ Yes — exactly as described in §4 |

**Clarification, stated plainly**: only usage through OpenAI's API Platform (an API key, billed to an OpenAI organization) can be tracked. Every ChatGPT consumer tier — even paid ones — is a separate, subscription-billed product with no usage-reporting API Costorah (or any third-party tool) can call.

---

## 9. Cursor

Cursor is a code editor with built-in AI features. Costorah has **no dedicated Cursor integration** — there is no Cursor-specific adapter, connector, or product-level partnership anywhere in this codebase.

- **API Keys**: Cursor supports "bring your own API key" for some of its AI features, letting you use your own OpenAI/Anthropic/etc. key instead of Cursor's own bundled access. **If** you configure Cursor to use an API key from an organization you've also connected in Costorah, that usage is included in the same org-wide usage report described in §4/§5 — the exact same mechanism as Claude Code in §6. There is nothing Cursor-specific about this; it works because Costorah tracks at the *provider organization* level, not the *calling tool* level.
- **Supported providers**: whatever provider Cursor is configured to call through — subject to the same per-provider capability table in §3 (only OpenAI and Anthropic keys produce trackable usage volume today).
- **Usage tracking / cost calculations**: identical mechanism and identical limitation as §6 — if Cursor is using Cursor's own bundled/subscription access rather than your own API key, ⬜ **not trackable**, for the same reason ChatGPT/Claude Web aren't.

---

## 10. VS Code Extensions

No VS Code extension has a dedicated Costorah integration. The rule is the same one established in §6/§9, repeated per extension for clarity:

| Extension | Trackable? |
|---|---|
| Continue.dev | ✅ only if configured with an API key from an org you've connected in Costorah; ⬜ otherwise |
| Cline | ✅ only if configured with an API key from an org you've connected in Costorah; ⬜ otherwise |
| Roo Code | ✅ only if configured with an API key from an org you've connected in Costorah; ⬜ otherwise |
| GitHub Copilot | ⬜ Not trackable — Copilot does not use a customer-supplied OpenAI/Anthropic API key; it uses GitHub's own backend access, which has no usage API Costorah can call |
| Cursor | See §9 |
| Claude Code (as a VS Code/editor integration) | See §6 |
| Any other API-key-based extension | ✅ only if it lets you supply your own key from a connected provider organization; ⬜ otherwise |

**The general principle, restated once more since it governs every one of §6–§10**: Costorah tracks usage at the *provider organization* level via each provider's own bulk usage-reporting API — never at the *calling tool* level, because no tool reports directly to Costorah. Any tool that lets you plug in your own API key from an organization you've connected (and validated) in Costorah will have its usage reflected, automatically, with zero extra configuration. Any tool using its own bundled/subscription access — no matter how popular or "AI-native" the tool is — cannot be tracked, because that usage never touches an API surface Costorah (or any third party) can query.

---

## 11. Self-Hosted Models

| Tool | Status |
|---|---|
| **Ollama** | ✅ Connection supported. Credential validation checks server reachability (`GET /api/tags`) — there is no API key concept, since Ollama has no billing. ⬜ Usage volume import: not applicable — Ollama is free and self-hosted, so there is no cost to calculate and no usage-history API to pull from. |
| LM Studio | ⬜ Not supported — no adapter exists in this codebase. |
| vLLM | ⬜ Not supported — no adapter exists in this codebase. |
| Open WebUI | ⬜ Not supported — this is a chat UI layered on top of another backend (often Ollama), not itself a provider Costorah connects to. |
| Anything else self-hosted | ⬜ Not supported unless it's Ollama. |

Because self-hosted models have no real dollar cost, Ollama's presence in Costorah's provider catalog exists to give you visibility into a connection's *health* (is the server reachable) rather than cost tracking, which doesn't apply.

---

## 12. Usage Collection

### Automatic Sync (✅ Implemented)

Each organization can enable auto-sync (Settings → Workspace tab) with a configurable interval: 5 minutes, 15 minutes, 1 hour, 6 hours, or 24 hours. A background scheduler checks, on a short internal tick, which organizations are due for a sync (based on when their last scheduled sync completed) and dispatches them automatically — no user action required once enabled.

### Manual Sync (✅ Implemented)

"Sync now" on any individual connection, or "Sync all" for every connection in your organization, triggers an immediate sync regardless of the auto-sync schedule.

### Scheduler (✅ Implemented)

The background scheduler uses both an in-process guard and a Redis-backed distributed lock to ensure the same organization is never synced twice concurrently, even across multiple backend processes. If Redis is unavailable, it safely falls back to the in-process guard alone rather than blocking sync entirely.

### Polling (not applicable — event-driven, not polling-based, for sync itself)

Usage sync is schedule/trigger-driven, not a polling loop from the frontend. Separately, the **dashboard UI** does poll certain status endpoints (e.g. sync status every 20 seconds while the Connections page is open) purely to refresh what's shown on screen — this is a UI-refresh mechanism, not how usage collection itself works.

### Retries (✅ Implemented)

Every individual HTTP request to a provider is retried automatically on transient failures (rate limits, network errors, provider-side 5xx errors) with exponential backoff. Authentication failures, quota-exceeded errors, and invalid-request errors are never retried, since retrying them can't succeed.

### Checkpoints (✅ Implemented)

Each connection's sync progress is checkpointed — the next sync resumes from where the last one left off (an incremental date range) rather than re-requesting a provider's entire usage history on every run.

---

## 13. Analytics

### Charts (✅ Implemented)

Spend Trend (a time-series line chart), Provider Distribution (a pie chart), Top Models, and Token Trend (stacked input/output token area chart).

### Heatmaps (✅ Implemented)

A 7-day × 24-hour grid on the Analytics page showing when, by hour and day of week, your AI spend actually occurs — cell intensity scaled to cost.

### KPIs (✅ Implemented)

The Overview page's top row: Total Spend, Today's Spend, This Month, Total Tokens, Total Requests, Active Providers, Projects, Average Cost per Request — plus, once budgets exist, Budget Remaining, Active Alerts, Critical Alerts, and Projected End-of-Month Spend.

### Providers (✅ Implemented)

A per-provider breakdown of spend, token counts (input/output split), request counts, and distinct model count.

### Projects (✅ Implemented)

A per-project spend ranking, including each project's own budget and how much of it has been used.

### Budgets & Alerts

See §14/§15 below.

### Filtering (✅ Implemented)

Every breakdown chart/table on the Analytics page can be filtered by Project, Provider, and Model simultaneously.

### Export (✅ Implemented)

CSV export is available for Spend, Providers, Projects, and Models data on the Analytics page.

---

## 14. Budgets

### Creating (✅ Implemented)

From the Budgets page, click "New budget." Choose a scope (organization-wide, or scoped to a specific project/provider/model), an amount and currency, a period (daily/weekly/monthly/yearly, or a custom date range), and one or more alert thresholds (defaults to 50%/75%/90%/100%, fully customizable — including values above 100%, e.g. 110%, for a "significantly over budget" tier).

### Thresholds (✅ Implemented)

Each threshold is evaluated independently — crossing 50% and later 90% in the same period produces two separate alerts, not one alert that silently changes message. A new period always starts fresh; a threshold you crossed last month doesn't stay "already alerted" this month.

### Forecast (✅ Implemented, simple linear model)

Every budget shows a **projected end-of-period spend** (a linear extrapolation of your spend-so-far run-rate to the full period) and a **remaining daily allowance** (how much more you could spend per day for the rest of the period without exceeding budget). This is intentionally a simple, deterministic calculation — not machine learning, not seasonality-aware. A more sophisticated forecasting model is on the roadmap (see `CLAUDE.md`'s EP-26.6).

### Alerts (✅ Implemented — see §15 for delivery)

Budget evaluation runs automatically after every usage sync (scheduled or manual) for every enabled budget in the organization.

---

## 15. Alerts

### Dashboard notifications (✅ Implemented)

Every fired alert appears in the notification bell (in the app header) and on a dedicated Alert Center page, where you can filter by severity/status, search, and take lifecycle actions: Acknowledge, Resolve, Dismiss, or Reopen.

### Email Alerts (⬜ Planned, not built)

Costorah has real, working transactional email (verification, password reset, invitation emails, all via Resend) — but **budget/alert notifications are not yet delivered by email**. The alert-dispatch architecture was deliberately designed so that adding email (or another channel) later is a matter of adding a new subscriber to the existing event stream, not a redesign — but no such subscriber has been built yet.

### Threshold Alerts (✅ Implemented)

Covered in §14 — this is the one alert *type* that's fully real today (budget threshold crossings). Costorah's alert data model also supports other alert types (provider health, usage spikes) at the schema level, but nothing evaluates real data against those types yet — only budget thresholds are currently wired to a live evaluation engine.

### Future Slack / Future Teams / Future Discord (⬜ Planned, not built)

No integration with any of these three exists today. Named here only because they're the natural next delivery channels once email delivery (above) exists, following the same "new subscriber to an existing event stream" pattern.

---

## 16. Troubleshooting

**Provider won't connect**
Check that the API key is valid and has not been revoked in the provider's own console. Costorah validates every credential live at save time — if the save fails, the error message tells you which of a small set of categories the failure falls into (invalid key, unauthorized, quota exceeded, timeout, network failure, provider unavailable) rather than a raw, possibly-sensitive error from the provider.

**Invalid API Key**
Regenerate the key in the provider's own console and update the connection in Costorah (use "Rotate key" rather than deleting and recreating the connection, to preserve its usage history).

**No usage imported**
First check the provider capability table in §3 — if you connected Google, Azure, Grok, or Ollama, **zero usage volume is expected and correct**, not a malfunction (see §3's explanation). If you connected **OpenRouter**, zero volume is *possible but not guaranteed* — it depends on whether your API key has sufficient permission for OpenRouter's usage-history endpoint (see §3's OpenRouter walkthrough); check the connection's "Last error" field before assuming this is expected. For OpenAI/Anthropic, confirm: (1) the connection shows a "healthy" validation status, not just "created"; (2) for Anthropic specifically, that your API key has Admin scope (§5); (3) that at least one sync has actually run — check the connection's "Last sync" timestamp, or click "Sync now."

**Sync failed**
Click "Refresh status" on the connection to see the specific error. A failed sync doesn't lose progress — the next sync (manual or scheduled) resumes from the last successful checkpoint automatically.

**Email not received**
Check spam/junk. Verification and password-reset links expire (24 hours and 1 hour respectively) — request a new one rather than continuing to search for an old email. If your account was created before Costorah's email system existed, or in an environment without email configured, contact support.

**OAuth issues / Google login**
If "Continue with Google" fails, try again — most failures are timing-sensitive (an expired one-time login attempt) rather than a persistent problem. If you're a brand-new Google user and get stuck before reaching your dashboard, check whether you're being asked to set a password first (§2) — this is a required one-time step, not an error.

**Provider limitations**
See §3's capability table before assuming a "no usage" result is a bug — 5 of 7 supported providers do not expose bulk usage data by design of the provider's own platform, not a Costorah gap.

---

## 17. Frequently Asked Questions

**Why doesn't ChatGPT Web appear in my usage?**
Because ChatGPT Web (chat.openai.com/chatgpt.com) is a subscription-billed consumer product with no usage-reporting API. Only usage through OpenAI's API Platform (an API key) is trackable. See §8.

**Can Claude conversations be tracked?**
Only if they go through the Anthropic API (a key from an organization you've connected in Costorah) — never browser conversations at claude.ai. See §5/§7.

**Can Cursor usage be tracked?**
Only if Cursor is configured to use your own API key from a connected provider organization, not Cursor's own bundled/subscription access. See §9.

**Can Ollama usage be tracked?**
Connections can be validated (server reachability), but there's no cost or usage-history data to import — Ollama is free and self-hosted. See §11.

**Can Google Gemini be tracked?**
Credential validation: yes, live, against a live model catalog too (EP-26.0.2 — Costorah now discovers your actual available Gemini models via `GET /v1beta/models` instead of a fixed list). Usage volume: not yet — Google's AI Studio API key has no bulk usage-history endpoint at all; that data lives behind a separate Google product (Vertex AI's Cloud Billing/BigQuery export), a different credential Costorah doesn't currently integrate with. See §3.

**Can Azure usage be tracked?**
Same answer as Google — credentials validate live, but usage volume requires Azure Cost Management (a different, ARM-scoped credential), which isn't wired in yet. See §3.

**Can I monitor multiple providers?**
Yes — connect as many of the 7 supported providers as you like; all appear together on the same dashboard, budgets, and analytics.

**Can multiple workspaces share providers?**
No — a provider connection belongs to exactly one workspace (organization). If you have both a Personal workspace and a Business workspace, each needs its own separate connection to the same provider, even if it's the same underlying API key. There is currently no cross-workspace provider-sharing mechanism (see the EP-26.2 "Multi-Workspace Management" roadmap item in `CLAUDE.md` for planned future work in this area).

---

## 18. Production Deployment Guide (EP-26.0.3)

This section is written for whoever actually deploys Costorah, not for a developer running it locally (§2 already covers that). See `RELEASE_CHECKLIST.md` (repo root) for the full pre-launch checklist this section supports.

### Required environment variables

| Variable | Required in production? | Purpose |
|---|---|---|
| `DATABASE_URL` | ✅ Always | Neon (or any Postgres) connection string, `postgresql+asyncpg://...` |
| `REDIS_URL` (or `REDIS_HOST`/`REDIS_PORT`/`REDIS_PASSWORD`) | Strongly recommended | Backs rate limiting, the scheduler's cross-process lock, and the realtime event bus — all three degrade gracefully without Redis (documented, tested fallback behavior), but a production deployment without it loses cross-instance coordination |
| `APP_SECRET_KEY` | ✅ Always in production | Root of `EncryptionService` (credential encryption at rest) — boot refuses to start with the dev default when `APP_ENV=production` |
| `APP_SECRET_KEY_PREVIOUS` | Only during a key rotation | Lets old ciphertext keep decrypting during a rotation window |
| `JWT_SECRET` | ✅ Always in production | Signs access tokens — same production-default-refusal enforcement as `APP_SECRET_KEY` |
| `SESSION_COOKIE_DOMAIN` | ✅ For the website↔dashboard subdomain flow | Set to `.costorah.com` in production so the session cookie is valid on both `costorah.com` and `app.costorah.com` (§6). Left unset it defaults to host-only, which is correct for local dev but breaks the cross-subdomain handoff in production. |
| `RESEND_API_KEY` / `EMAIL_FROM` | ✅ Always in production | Boot refuses to start without both when `APP_ENV=production` — verification, password-reset, and invitation emails have no transport otherwise |
| `RESEND_WEBHOOK_SECRET` | Recommended | Enables the delivery-event webhook receiver (`POST /v1/webhooks/resend`, EP-25.3) — without it the endpoint returns 503 rather than accepting unverifiable payloads |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Optional | "Continue with Google" is additive, not required — omitting these returns 503 on the Google OAuth start/link endpoints but never breaks password auth |
| `SCHEDULER_ENABLED` | Optional (default `True`) | Set to `False` only if you deliberately want no background sync (e.g. a read-only staging mirror) |
| `SCHEDULER_TICK_INTERVAL_SECONDS` | Optional (default `60`) | How often the scheduler checks which organizations are due |
| `API_CORS_ORIGINS` | ✅ Always in production | Must include the real `https://costorah.com`, `https://www.costorah.com`, `https://app.costorah.com` — a missing entry here surfaces to users as a generic "Could not reach the server." (§10's own documented incident) |
| `DASHBOARD_URL` | ✅ Always in production | The website's post-auth redirect target and the target embedded in invitation/verification email links |
| `API_BASE_URL` | ✅ Always in production | Used to build absolute links in emails |

Never commit real values for any of these — `backend/.env.example` documents every variable with a placeholder; `backend/.env` (gitignored) holds real local-dev values only.

### Provider onboarding (production)

Every provider's own account-creation and API-key-generation walkthrough lives in §3–§11 above (OpenAI, Anthropic, Google, OpenRouter, Azure, Grok, Ollama). Nothing about onboarding a *production* connection differs from a development one — the same encrypted-credential storage, live validation, and sync pipeline runs identically in both environments; the only production-specific consideration is making sure `RESEND_API_KEY`/`EMAIL_FROM` are set so the invitation/verification emails those workflows depend on actually send (see above).

### Troubleshooting (production-specific)

- **"Could not reach the server." on login/signup from the website** — almost always a missing `API_CORS_ORIGINS` entry for the exact origin the request came from (`www.` vs. bare domain matters), not a real outage. See §10's full incident writeup for the exact diagnostic steps.
- **A freshly-deployed backend crashes on boot with `ModuleNotFoundError: No module named 'cryptography'`** — a real, previously-shipped incident (EP-22.1, §15): confirm the deploy's build step ran `pip install -e "."` against the *declared* production dependencies, not a dev venv that happened to have `cryptography` installed transitively. Fixed in the dependency declaration since EP-22.1; only relevant if deploying from a commit that predates it.
- **Website nav routes 404 in production but work locally** — a Cloudflare **project-type** mismatch (Pages vs. Workers), not an application bug; see §10's deployment checklist.
- **A provider connection stays "healthy" but never imports usage** — check the Provider Validation Matrix in §3 first; for 4 of 7 providers (Google, Azure, Grok, Ollama) this is expected, permanent, honest behavior, not a bug to chase.
- **Scheduler never seems to run** — confirm `SCHEDULER_ENABLED` isn't set to `False`, and check `GET /v1/organizations/{org_id}/provider-connections/scheduler/status` for the org's own `auto_sync_enabled`/interval settings (Settings → Workspace tab).
- **Emails never arrive** — confirm `RESEND_API_KEY`/`EMAIL_FROM` are actually set in the deployed environment (not just `.env.example`); a missing key doesn't error, it silently logs `email_send_skipped_unconfigured` and the request that triggered it still succeeds (by design — registration/reset must never block on email transport, §24).

### Known provider limitations (production)

Unchanged from §3's own Provider Validation Matrix — repeated here because it's the single most common source of a "is this broken?" support question: **Google, Azure OpenAI, Grok, and Ollama will never show non-zero historical usage**, by design, because none of those four platforms exposes a bulk usage-history API on the credential type Costorah connects to. This is a real, external platform constraint, not a Costorah defect — see §3 for the full per-provider explanation and CLAUDE.md's EP-26.0.2.1/EP-26.0.3 sections for the underlying validation evidence.

### Production recommendations

1. Before inviting external beta users, perform at least one real Connect → Validate → Sync walkthrough against a live OpenAI or Anthropic account on the actual deployed environment — every provider's code has been validated hermetically (mocked HTTP against researched, realistic response shapes) but never against a live account from within this development sandbox. See `RELEASE_CHECKLIST.md`'s "Go / No-Go Decision" for the full reasoning.
2. Confirm Redis is genuinely reachable in production, not just configured — the scheduler's cross-process locking and the login rate limiter both degrade to weaker, single-process behavior without it (safe, documented, but not the intended production posture).
3. Re-run `alembic upgrade head` against the real production database as part of every deploy, not just in CI against a throwaway instance.
4. Monitor `/health` and `/ready` from your load balancer/uptime tooling — both already report Postgres and Redis connectivity, no additional instrumentation needed to start.

---

*This document reflects the implementation as of the EP-26.0.3 milestone. See `CLAUDE.md` for the full engineering changelog, `RELEASE_CHECKLIST.md` for the pre-launch checklist, and the "Future Roadmap — EP-26" section for what's planned but not yet built.*
