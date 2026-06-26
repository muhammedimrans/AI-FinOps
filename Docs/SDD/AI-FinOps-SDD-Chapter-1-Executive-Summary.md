# AI FinOps — Software Design Document (SDD)
## Chapter 1: Executive Summary

| Field | Value |
|---|---|
| **Document title** | AI FinOps — Software Design Document |
| **Chapter** | 1 — Executive Summary |
| **Version** | 0.1 (Draft) |
| **Status** | Draft for Review |
| **Author** | Khan — Founder |
| **Last updated** | June 26, 2026 |
| **Classification** | Confidential — Internal |
| **Reviewers** | _TBD_ |

> **In one sentence.** AI FinOps is a finance-grade, cross-provider control plane that gives an organization a single view of everything it spends on AI — API consumption, per-seat tooling, hyperscaler AI services, and agentic workloads — together with the controls to **attribute, govern, forecast, and optimize** that spend.

This chapter establishes the problem we are solving, the competitive landscape, the specific gap AI FinOps fills, the product vision, the target customer, the business value to both the customer and the company, and the metrics by which success will be judged. Numbered references appear in **Section 1.8**.

---

## 1.1 Problem Statement

AI has become a top-line, fast-growing cost center that most organizations can neither see, attribute, nor control with the tools they own today.

The spend is large and accelerating. Gartner forecasts roughly **$2.59 trillion** in global AI spending in 2026 [3], and nearly every finance-engineering organization is now exposed to it: **98% of FinOps teams manage AI spend, up from 31% two years ago** [1]. But the spend behaves unlike any cost these teams have governed before.

**1. The unit of cost is the token, not the compute-hour.** AI consumption is variable and non-deterministic. A single user action can trigger an agent loop that fires dozens of model calls, so cost no longer tracks request volume in any predictable way [5][6]. Trend-based budgeting — the foundation of the cloud cost playbook — breaks down [5].

**2. The spend is fragmented across vendors and modalities.** A typical organization's AI cost is spread simultaneously across:
- **Provider APIs** — OpenAI, Anthropic, Google Gemini, xAI, and others;
- **Per-seat AI SaaS** — Cursor, Claude Code, GitHub Copilot, ChatGPT Team;
- **Hyperscaler AI services** — AWS Bedrock, Azure OpenAI, Google Vertex;
- **Shadow / individual usage** that no one centrally owns.

This spend "transcends technology category boundaries" — it lands in enterprise agreements, SaaS, startup model vendors, neo-clouds, and multiple hyperscalers at once [5][28] — which means every existing cost tool, each built for a single category, sees only a slice.

**3. The consequences are visibility, governance, and optimization failures.**
- **No attribution.** Finance receives a handful of opaque per-vendor invoices but cannot map spend to a team, product, feature, or customer. Visibility into AI cost is the **#1 challenge** FinOps practitioners report, ahead of allocation and ROI [2].
- **No governance.** Budgets, allocation policy, and approvals act _after_ the invoice arrives, not before commitment.
- **No optimization discipline.** Without a per-task view, the most expensive model gets used for everything, oversized prompts go unnoticed, and dormant seats are never reclaimed.

The cost of this gap is measurable. Only **7.5% of enterprises embed FinOps into AI projects**, and **~41% of enterprises waste more than 15% of their AI spend** [4]. At the unit level, GitHub Copilot reportedly lost up to **$80 per user per month** against a $10 subscription, and Cursor reportedly spent **~$650M/year** on Anthropic API calls [9] — yet roughly **half of AI product companies do not track LLM API costs at all** [9]. When a bill triples, diagnosing _which_ calls drove it routinely costs **10+ engineering-days** because the data does not exist in one place [12].

**The problem in one line:** AI spend is large, growing, non-deterministic, fragmented across vendors and modalities, and largely ungoverned — and organizations are increasingly being asked to fund AI investment from optimization savings they currently have no way to find [1].

---

## 1.2 Existing Market

The market is real and institutionalizing rapidly — the FinOps Foundation has renamed its mission from managing "the value of cloud" to "the value of technology," and, with the Linux Foundation, announced intent to form a **Tokenomics Foundation** for open AI-billing standards, backed by Microsoft, Google, Oracle, SAP, ServiceNow, JPMorganChase and others, alongside the **FOCUS** cost-and-usage normalization spec [1][6]. The category is being defined. The tooling to serve it is not yet built.

Today's adjacent players cluster into five segments, **each serving a different buyer and only a partial slice of the problem**:

| Segment | Representative players | Primary buyer | What it does | What it misses |
|---|---|---|---|---|
| **LLM observability** | Helicone (acq. Mintlify, Mar 2026), Langfuse, LangSmith, Arize Phoenix | Engineering | Per-request tracing, debugging, latency, cost-per-call | Org-level governance, chargeback, subscription seats, finance-grade attribution |
| **AI gateways** | Portkey (~1T tokens/day), LiteLLM, Cloudflare AI Gateway, Kong AI Gateway | Platform / Infra | Routing, fallback, caching, reliability; cost is a byproduct | Budgets, policy, multi-modality, financial reporting |
| **Cloud FinOps** | Apptio Cloudability, CloudHealth, Vantage, Kubecost, Flexera | Finance / FinOps | Cloud infra cost (compute, storage, k8s); governance model | Built for the compute-hour, not the token; largely blind to AI SaaS seats |
| **APM extensions** | Datadog LLM Observability, New Relic | Operations | AI as another telemetry tab beside infra metrics | Cost governance, attribution, optimization |
| **Consumer trackers** | A large field of free browser/menu-bar apps for Claude, ChatGPT, Cursor, Gemini | Individual developer | Personal rate-limit awareness | No org rollup, attribution, policy, or chargeback |

Two segment notes matter for positioning. **Vantage and Kubecost** have begun adding native AI/provider visibility (e.g., Anthropic and OpenAI) [10], which validates demand — but they remain anchored in cloud-infrastructure cost models and do not unify per-seat AI subscriptions. And the **LLM observability** category, though adjacent, is sized and growing fast on its own (~$2.69B in 2026, projected ~$9.26B by 2030 at ~36% CAGR) [7], confirming budget is flowing into AI cost tooling generally.

---

## 1.3 Market Gap

The clearest articulation of the gap comes from the industry body itself: **granular monitoring of AI spend — tokens, LLM requests, and GPU utilization — is the single most-requested tooling capability in the FinOps Foundation's 2026 survey, and the report explicitly states that commercial tooling has not yet delivered it at scale** [2][30].

Mapping that against the existing market:

- **Engineering tools** (observability, gateways) optimize for the _developer_ and the _request_. They do not do chargeback, budget policy, finance-grade attribution, or multi-modality (per-seat subscriptions are invisible to them).
- **Cloud FinOps tools** own the _finance buyer_ and the _governance model_, but were architected for cloud infrastructure and are largely blind to token-level economics and AI SaaS subscription spend.
- **Consumer trackers** serve _individuals_, not organizations — no rollup, policy, or chargeback.

**No incumbent occupies the intersection.** The unmet need is a single platform that is, at once:

1. **Cross-provider** — every API, gateway, hyperscaler service, and per-seat tool;
2. **Cross-modality** — usage-based, subscription, and agentic spend in one cost model;
3. **Finance-grade** — attribution, chargeback/showback, budgets, policy, forecasting, and audit;
4. **Optimization-native** — recommendations quantified as projected savings;
5. **Deployment-flexible** — managed SaaS _or_ self-hosted for data-sensitive and regulated buyers.

The three hardest, highest-value problems the FinOps Foundation names for AI — **understanding the full scope of AI spend, attributing it to business units, and quantifying its value** [4][27] — map one-to-one onto this intersection. **That intersection is the AI FinOps opportunity.**

---

## 1.4 Product Vision

> **Vision.** Every organization can see, govern, and optimize the full cost of its AI — across every provider, tool, team, and agent — with the same rigor it applies to cloud, and without surrendering control of its data.

AI FinOps is a **unified control plane for AI spend**. It ingests usage and cost from provider APIs, AI gateways, hyperscaler AI services, and per-seat AI subscriptions through a normalized, **extensible provider-adapter model** — so new providers (today xAI; tomorrow whoever ships next) are onboarded as configuration, not re-architecture — and normalizes everything to a common, **FOCUS-aligned** cost-and-usage schema.

On that foundation it delivers three capabilities, matching the company's mandate to **monitor, govern, and optimize**:

- **Monitor** — a single, real-time, finance-grade view of all AI spend, attributed to team, project, feature, customer, and agent. One source of truth, replacing a folder of vendor invoices.
- **Govern** — budgets, allocation policy, approval workflows, anomaly and overrun alerts, chargeback/showback, and audit trails. Controls that act _before_ commitment, not after the bill.
- **Optimize** — model right-sizing and small-language-model (SLM) substitution (which can cut specialized-task cost dramatically [10]), caching and prompt-efficiency insights, provider/price arbitrage, and dormant-seat reclamation — each surfaced as a quantified, projected saving.

The platform is deployable as **managed SaaS** or **self-hosted** for regulated and data-sensitive customers, and is designed to become the **system of record for AI spend** — the finance-owned source of truth that engineering, platform, and leadership share.

---

## 1.5 Customer

| Dimension | Definition |
|---|---|
| **Economic buyer** | Mid-market: VP Engineering / CTO / Head of Platform. Enterprise: the FinOps / Finance function (Director of FinOps, VP Finance, CFO org). Increasingly a single senior decision — **~78% of FinOps practices now report to the CTO or CIO** [30]. |
| **Primary users** | FinOps / Platform / DevOps practitioners (configure adapters, set policy, run dashboards); engineering managers (team budgets, unit economics); finance analysts (chargeback, forecast, ROI). |
| **Beachhead segment** | AI-native and AI-forward scale-ups (≈ Series A–C) and AI-heavy divisions of larger firms with meaningful, multi-provider AI spend. They feel fragmentation and surprise bills first, carry the least legacy tooling, and procure fastest. |
| **Expansion segment** | Enterprise platform and FinOps teams — the 98% now mandated to manage AI spend, often lean teams of **8–10 practitioners managing $100M+** and explicitly asking for tooling that does not yet exist [1][29]. Plus agencies / MSPs governing spend on clients' behalf. |

The wedge is the scale-up that already pays four to seven figures a month across several AI vendors and has no unified view; the durable account is the enterprise FinOps team that adopts AI FinOps as its standard for the AI Scope.

---

## 1.6 Business Value

**Value to the customer (the ROI case).**
- **Direct savings.** Optimization typically recovers a meaningful double-digit share of AI spend. Model right-sizing and SLM substitution alone can reduce specialized-task cost by a large margin [10]; dormant-seat reclamation and provider arbitrage add more. Against the finding that **~41% of enterprises waste >15% of AI spend** [4], even partial capture funds the platform many times over.
- **Avoided risk.** Surprise overruns are eliminated; root-cause analysis on a cost spike compresses from the **10+ engineering-days** it routinely takes today [12] to minutes.
- **Governance and accountability.** Per-unit attribution, audit trails, and the data to decide where to invest versus cut — increasingly the metric that matters, with **~64% of FinOps teams now using "value delivered" as a KPI** rather than raw savings [4].

**Value to the company (why this is venture-scale).**
- **TAM and timing.** AI spend is forecast in the trillions and growing [3]; 98% of FinOps teams are now mandated to manage it [1]; and the most-requested tool in the category does not yet exist [2]. This is a **category-creation moment** with institutional tailwinds — FinOps Foundation, the forming Tokenomics Foundation, and the FOCUS standard [1][6].
- **Durable, expanding position.** As the finance-owned **system of record for AI spend**, the product is sticky (rip-out cost is high once budgets, policy, and chargeback run through it), expands naturally (more providers connected, more seats, more teams; platform fee + usage-based pricing), and compounds via **cross-customer benchmarking data** on model price/performance — a data advantage adjacent incumbents cannot easily replicate.

---

## 1.7 Success Metrics

The North Star is **AI spend under governance** — the annualized AI spend actively monitored and governed through the platform. Supporting metrics are grouped below. _Targets are draft and will be validated with design partners._

| Category | Metric | Draft target |
|---|---|---|
| **North Star** | Annualized AI spend under governance | Growth MoM; primary board metric |
| **Customer outcome** | Median AI cost reduction within 90 days of onboarding | ≥ 20% |
| | Share of AI spend attributable to team / project / feature | ≥ 90% |
| | Time-to-root-cause for a cost anomaly | < 1 hour (from days) |
| **Trust & accuracy** _(critical for the finance buyer)_ | Reconciliation accuracy vs. provider invoice | within ± 2% |
| | Data freshness / dashboard latency (API sources) | < 15 minutes |
| **Adoption & activation** | Activation: first provider connected **and** first budget/policy set within 24h of signup | ≥ 70% of new orgs |
| | Providers connected per active account (depth) | ≥ 3 within 60 days |
| | Weekly active governance users per account | Trending up |
| **Retention & expansion** | Net revenue retention | ≥ 120% |
| | Annual logo retention | ≥ 90% |
| **Optimization impact** _(proves the "Optimize" pillar)_ | Realized savings from platform recommendations, as % of monitored spend | Trending up |
| | Recommendation acceptance rate | ≥ 40% |

The **Trust & accuracy** band is treated as a gating requirement, not a vanity metric: a finance buyer will not run chargeback on numbers that do not reconcile to the invoice, so reconciliation accuracy and data freshness are first-class product commitments rather than aspirations.

---

## 1.8 References & Data Sources

_Market and cost figures below are directional industry estimates current as of mid-2026 and should be re-validated before external publication._

1. FinOps Foundation — **State of FinOps 2026** (98% of teams manage AI spend, up from 31%; AI cost management the #1 desired skillset; mission change to "value of technology"; lean team sizes at $100M+ scale). data.finops.org; Linux Foundation press release, Feb 2026.
2. FinOps Foundation 2026 survey, reported by **Virtasant** — granular AI-spend monitoring (tokens, requests, GPU) is the top tooling request and "commercial tooling has not yet delivered at scale"; visibility is the #1 AI-cost challenge. virtasant.com/blog/state-of-finops-2026.
3. **Gartner** forecast of ~$2.59T global AI spending in 2026 (cited in FinOps X 2026 takeaways). usage.ai.
4. **IDC** (Jevin Jensen) and Flexera, reported by **CIO Dive** — 7.5% of enterprises embed FinOps into AI projects; ~41% waste >15% of AI spend; ~64% of teams use "value delivered" as a KPI; enterprise agent counts. ciodive.com, Apr 2026.
5. FinOps Foundation — **FinOps for AI Overview** / token-economics framing (token as the atomic unit; right-sizing model selection). finops.org/wg/finops-for-ai-overview.
6. FinOps Foundation — **FinOps X 2026 Day 1 Keynote** (intent to form the Tokenomics Foundation; supporter list; FOCUS billing standard). finops.org/insights/finops-x-2026-day-1-keynote.
7. LLM observability market sizing (~$2.69B in 2026 → ~$9.26B by 2030, ~36% CAGR), via **Confident AI**. confident-ai.com.
8. LLM observability competitive landscape; Helicone acquired by Mintlify (Mar 2026); Portkey ~1T tokens/day, via **buildmvpfast / particula**.
9. ~50% of AI product companies do not track LLM API costs (Mavvrik 2025); GitHub Copilot up to $80/user/month; Cursor ~$650M/year on Anthropic — via **buildmvpfast**.
10. AI FinOps tooling and optimization levers (Vantage native Anthropic/OpenAI visibility; Kubecost for Kubernetes; SLM downsizing for specialized tasks), via **linesNcircles**, Apr 2026.
11. _(reserved)_
12. Cost-spike diagnosis effort (~10+ engineering-days without unified observability), via **particula.tech**.
27. FinOps Foundation — **AI Value** topic (scope, attribution, and ROI as core AI-cost problems). finops.org/topic/finops-for-ai.
28. FinOps Foundation — **FinOps for AI** framework / technology category (AI spend transcends category boundaries; forecasting volatility). finops.org/framework/technology-categories/ai.
29. Linux Foundation — State of FinOps 2026 press release (1,192 respondents; $83B+ annual cloud spend represented; AI as the dominant agenda). linuxfoundation.org.
30. **Virtasant** — State of FinOps 2026 analysis (78% of practices report to CTO/CIO; top tooling request). virtasant.com.

---

_End of Chapter 1. Suggested next chapters: **2 — Goals, Non-Goals & Scope**; **3 — System Context & High-Level Architecture**; **4 — Data Model & Ingestion (provider-adapter framework, FOCUS-aligned schema)**._
