# AI FinOps — Software Design Document (SDD)
## Chapter 4 (Part 2): Standards, Catalogs, Contracts & Data Dictionary

| Field | Value |
|---|---|
| **Document title** | AI FinOps — Software Design Document |
| **Chapter** | 4 (Part 2) — Standards, Catalogs, Contracts & Data Dictionary |
| **Version** | 0.2 (Draft — additions to Chapter 4) |
| **Status** | Draft for Review |
| **Author** | Khan — Founder |
| **Last updated** | June 26, 2026 |
| **Extends** | Chapter 4 (Part 1) §4.1–§4.18 |

> **Purpose.** Part 1 defined the data principles, the canonical event, the entity model, storage, partitioning, lifecycle, retention, recovery, security, and governance. Part 2 adds the standards and catalogs that keep those things consistent as the system grows: **naming and identifier standards, the common event envelope, the event and topic catalogs, data lineage, service-level objectives, a data-quality score, and the change-control policy that freezes the canonical event.** It closes with **Appendix A — the Data Dictionary**, the single field-level reference for every engineer, SDK author, and API consumer. Each section notes where it slots into a merged Chapter 4. New decisions are recorded as **ADR-024 through ADR-030**.

---

## 4.19 Naming & Identifier Standards
*Placement: belongs immediately after §4.1. These rules are global and binding.*

| Element | Standard | Example |
|---|---|---|
| Field & identifier names | `snake_case` | `org_id`, `prompt_tokens` |
| Internal identifiers | **UUIDv7** (time-ordered, index-friendly) | — |
| External identifiers | **Type-prefixed** string over the UUIDv7 | `org_01HQ…`, `proj_01HR…` |
| Event identifiers | **Deterministic** hash (idempotency), prefixed | `evt_…` |
| Timestamps | **UTC, ISO 8601**; store/transmit UTC, localize only in UI | `2026-06-26T12:00:00Z` |
| Monetary amounts | **Arbitrary-precision decimal — never floating point** | `0.2300` |
| Currency | **ISO 4217** | `USD`, `EUR` |
| Regions | Cloud-region identifiers (canonical, deployment-mapped) | `us-east-1`, `eu-west-1` |
| Enums | lowercase; dot- or underscore-delimited | `provisional`, `push_sdk` |
| Event types & topics | dot-namespaced lowercase | `usage.costed`, `budget.exceeded` |
| Versions | integers internally; semantic for external API | `schema_version: 3` |

**Identifier strategy (refines §4.5).** §4.5 listed primary keys as "uuid"; this is the precise rule: the **canonical internal key is UUIDv7** — time-ordered so it sorts naturally and avoids index hotspotting at insert scale — and the **external representation is a type-prefixed string** (Stripe-style: `org_`, `proj_`, `usr_`, `conn_`, `bgt_`, `pol_`, `alr_`, `rpt_`, `ntf_`, `prc_`). The prefix makes identifiers self-describing in logs and API responses, which materially helps debugging (§PP-8). **Usage Events are the one exception**: their `event_id` is a *deterministic* hash, not a UUIDv7, because idempotency requires the same logical event to always produce the same id (§4.3.1).

**Money rule (critical for a FinOps platform).** Every monetary value — costs, budgets, prices — is stored and computed as **arbitrary-precision decimal**. Floating-point representation of money accumulates rounding error that silently corrupts a financial ledger and is extremely painful to retrofit once historical data exists. This is non-negotiable for a cost platform.

*Recorded as ADR-024 (naming & identifier standards).*

---

## 4.20 Common Event Envelope
*Placement: belongs inside §4.3, before §4.3.1. It reorganizes — does not replace — the canonical event fields.*

Every message on the event log shares a common **envelope**; the event-type-specific data lives in `payload`. This separation makes the event system extensible: new event types reuse the envelope and only define a new payload.

| Envelope field | Description | Required |
|---|---|---|
| `event_id` | Unique id of this message (deterministic for `usage.*`; UUIDv7 otherwise) | Yes |
| `event_type` | Dot-namespaced type (e.g., `usage.costed`) | Yes |
| `schema_version` | **Contract version of this event type** | Yes |
| `occurred_at` | When the domain fact occurred (UTC ISO 8601) | Yes |
| `produced_at` | When the envelope was emitted | Yes |
| `producer` | Emitting service / bounded context (e.g., `normalization`) | Yes |
| `org_id` | Tenancy, for routing/partitioning/filtering | Yes |
| `correlation_id` | Trace linkage across related events | No |
| `partition_key` | Partitioning key (normally `org_id`, §3.7.3) | Yes |
| `payload` | The event-type-specific body | Yes |

### Reconciliation with §4.3 (the two "version" concepts)

This envelope reorganizes the flat field list in §4.3.1 into **envelope + payload**. No field is removed. The mapping:

- **Envelope** carries: `event_id`, `event_type`, `schema_version`, `occurred_at` (= the event's `event_time`), `produced_at`, `producer`, `org_id`, `correlation_id`, `partition_key`.
- **Payload** (for a `usage.*` event) carries the rest of §4.3.1: `project_id`, `provider`, `model`, token measures, `cost_*`, `pricing_version`, `source`, `raw_ref`, `ingest_time`, `processing_time`, `status`, **`event_version`** (record revision), `adjustment_of`, `tags`, `processing_metadata`.

The naming collision is now resolved unambiguously:

| Name | Where | Meaning |
|---|---|---|
| `schema_version` | **Envelope** | Version of the event *type's contract* (evolves per §4.3.4). |
| `event_version` | **Payload** | Revision number of a specific *record* (drives latest-wins reconciliation, §4.3.2). |

*Recorded as ADR-025 (common event envelope).*

---

## 4.21 Event Catalog
*Placement: canonicalizes the informal event names introduced in §3.7.2.*

Every event type the platform produces, with canonical (dot-namespaced) names. State-transition events correspond to the state machines in §3.21.

| Event type | Domain | Produced by | Consumed by | Topic |
|---|---|---|---|---|
| `usage.received` | Usage | Collector | Normalization | `usage.raw` |
| `usage.pulled` | Usage | Adapter Workers | Reconciliation, Normalization | `usage.pulled` |
| `usage.rejected` | Usage | Normalization | Operators, Audit | `dlq.*`, `audit.events` |
| `usage.costed` | Usage | Normalization | Governance, Analytics | `usage.costed` |
| `usage.reconciled` | Usage | Reconciliation | Analytics, Audit | `usage.reconciled` |
| `budget.created` | Governance | Governance | Audit | `budget.events` |
| `budget.updated` | Governance | Governance | Audit | `budget.events` |
| `budget.threshold_crossed` | Governance | Governance | Notification | `budget.events` |
| `budget.exceeded` | Governance | Governance | Notification | `budget.events` |
| `alert.raised` | Alert | Governance | Notification | `alert.events` |
| `alert.acknowledged` | Alert | Governance / User | Audit | `alert.events` |
| `alert.resolved` | Alert | Governance | Audit | `alert.events` |
| `provider.connected` | Provider | Identity / Provider | Audit, Dashboard | `provider.events` |
| `provider.disconnected` | Provider | Identity / Provider | Audit | `provider.events` |
| `provider.sync_started` | Provider | Adapter Workers | Dashboard | `provider.events` |
| `provider.sync_completed` | Provider | Adapter Workers | Dashboard | `provider.events` |
| `provider.sync_failed` | Provider | Adapter Workers | Dashboard, Audit | `provider.events` |
| `attribution.mapping.changed` | Identity | Identity | Normalization | `attribution.mappings` (compacted) |
| `pricing.updated` | Pricing | Pricing | Normalization | `pricing.updates` (compacted) |
| `report.requested` | Reporting | Public API | Reporting | `report.events` |
| `report.generated` | Reporting | Reporting | Public API | `report.events` |
| `report.failed` | Reporting | Reporting | Public API, Audit | `report.events` |
| `audit.recorded` | Audit | All services | Audit sink | `audit.events` |

`usage.received → usage.costed → usage.reconciled` mirror the Usage Event lifecycle (§3.21.3); `provider.*` events mirror the Provider Connection machine (§3.21.1); `budget.*` events mirror the Budget machine (§3.21.2). *Recorded as ADR-026 (event taxonomy & catalog).*

---

## 4.22 Topic Catalog
*Placement: refines and supersedes the topic list in §3.7.3.*

**Topic-granularity rule:** the high-volume usage pipeline gets **one topic per processing stage** (different consumers attach at different stages, and volume justifies separation); lower-volume domain events get **one topic per domain**, with the specific event distinguished by `event_type` in the envelope. This avoids both topic explosion and ad-hoc topic creation.

| Topic | Carries | Partition key | Retention | Compacted | Primary consumers |
|---|---|---|---|---|---|
| `usage.raw` | `usage.received` | `org_id` | Bounded (days) | No | Normalization |
| `usage.pulled` | `usage.pulled` | `org_id` | Bounded (days) | No | Reconciliation, Normalization |
| `usage.costed` | `usage.costed` | `org_id` | Medium | No | Governance, Analytics, Audit |
| `usage.reconciled` | `usage.reconciled` | `org_id` | Medium | No | Analytics, Audit |
| `budget.events` | `budget.*` | `org_id` | Medium | No | Notification, Audit |
| `alert.events` | `alert.*` | `org_id` | Medium | No | Notification, Audit |
| `provider.events` | `provider.*` | `org_id` | Medium | No | Dashboard, Audit |
| `audit.events` | `audit.recorded` | `org_id` | Long | No | Audit sink |
| `attribution.mappings` | `attribution.mapping.changed` | mapping key | Infinite | **Yes** | Normalization |
| `pricing.updates` | `pricing.updated` | pricing key | Infinite | **Yes** | Normalization |
| `report.events` | `report.*` | `org_id` | Short | No | Reporting, Public API |
| `dlq.<source-topic>` | poison messages | source key | Long | No | Operators |

Changes from §3.7.3: `cost.adjustments` is folded into `usage.reconciled`; `governance.alerts` is renamed `alert.events`; `budget.events`, `provider.events`, and `audit.events` are added as per-domain topics. *Recorded as ADR-027 (topic taxonomy & catalog).*

---

## 4.23 Data Lineage
*Placement: complements §4.9 (lifecycle); this is the origin-to-destination view used for debugging.*

```mermaid
flowchart LR
    SRC[AI Provider / SDK / Gateway] --> COL[Collector]
    COL --> ARC[(Object Archive<br/>raw payload — source of truth)]
    COL --> K1[usage.raw]
    ADP[Adapter Workers] --> K2[usage.pulled]
    PRC[Pricing] -. pricing.updates .-> NRM
    IDN[Identity] -. attribution.mappings .-> NRM
    K1 --> NRM[Normalizer]
    NRM --> K3[usage.costed]
    K2 --> RCN[Reconciliation]
    K3 --> RCN
    NRM --> CH[(ClickHouse<br/>costed events + rollups)]
    RCN --> CH
    CH --> QRY[Query Service]
    QRY --> DASH[Dashboard]
    QRY --> REP[Reports]
    ARC -. replay .-> NRM
```

| Datum | Origin | Transformations | Authoritative store | Consumed by |
|---|---|---|---|---|
| Raw usage | Provider / SDK | archived as-is | Object archive | Reconciliation, replay |
| Costed event | `usage.raw` / `usage.pulled` | validate → enrich → cost | ClickHouse (latest version) | Dashboards, reports, governance |
| Reconciled cost | costed + authoritative pull | compare → adjust | ClickHouse | Reports, audit |
| Rollups | costed events | aggregate | ClickHouse (derived) | Dashboards |
| Cost figure (external truth) | Provider billing | reconcile | Provider (external SoT) | Reconciliation |

Lineage answers the debugging question "where did this number come from?" by tracing any figure back through its transformations to the immutable archive.

---

## 4.24 Service Level Objectives
*Placement: new section; quantifies the acceptance criteria SC-2, SC-3, SC-7 from Chapter 2.*

Draft SLO targets, to be validated with design partners. These are engineering goals, monitored continuously (§3.11).

| Metric | Target | Measurement | Ties to |
|---|---|---|---|
| Ingestion acknowledgement | p95 < 200 ms | Collector receipt → `202` | — |
| Ingest-to-costed (push) | p95 < 5 s | receipt → visible costed event | SC-7 |
| Dashboard freshness (push) | < 30 s | usage occurrence → queryable | SC-7 |
| Dashboard query latency | p95 < 2 s | API request → response | SC-2 |
| Daily reconciliation | completes < 1 h | scheduled run → done | SC-3 |
| Reconciliation accuracy | within ±2% | reconciled vs provider billing | SC-3 |
| Alert latency | < 60 s | breach → notification dispatched | C3 |
| Report generation (typical) | < 2 min | request → artifact ready | P3 |
| Read-path availability | ≥ 99.9% | uptime of serving plane | — |

*Recorded as ADR-028 (platform SLOs).*

---

## 4.25 Data Quality Score
*Placement: extends the data-quality dimensions in §4.16.*

§4.16 defined four quality dimensions; this section extends them to six and introduces a composite score surfaced to operators.

| Dimension | Definition | Measurement | Target |
|---|---|---|---|
| **Completeness** | Events fully attributed and costed | costed+attributed / total | ≥ 99% |
| **Accuracy** | Reconciled cost vs provider billing | drift vs billing | within ±2% |
| **Freshness** | Data within the freshness SLA | events within SLA / total | ≥ 99% |
| **Uniqueness** | Absence of double-counting | 1 − duplicate rate | ≈ 100% |
| **Consistency** | Read models agree with source events | rollup vs detail variance | ≈ 0 drift |
| **Validity** | Events pass schema/range validation first-pass | valid / received | ≥ 99% |

**Composite Data Quality Score.** A single 0–100 score is computed as a weighted aggregate of the six dimensions and displayed on an internal operations dashboard with a per-dimension breakdown, so operators can see platform health at a glance and drill into any failing dimension. Accuracy and Completeness carry the highest weights (they directly affect customer-facing numbers); a score below a defined threshold raises an internal alert. The score is an *internal operational metric*, never customer-facing. *Recorded as ADR-029 (data-quality score).*

---

## 4.26 Canonical Event Change Control (Freeze)
*Placement: elevates the additive-only policy in §4.3.4 into a governed process. This is the single most important discipline in the data layer.*

Once implementation begins, the **canonical event (§4.3) is a frozen contract, treated exactly like a public API.** It is consumed by every service, the SDK, and external integrators; a careless change breaks all of them. No field may be added, removed, renamed, or repurposed informally.

Every proposed change to the canonical event must satisfy **all** of the following before merge:

| # | Requirement | Why |
|---|---|---|
| 1 | An **ADR** documenting the change and alternatives | Decision is recorded, not silently made |
| 2 | An **SDD update** (this chapter + Data Dictionary) | The blueprint stays the source of truth |
| 3 | A **schema version bump** (additive minor / breaking major) | Consumers can negotiate versions (§4.10) |
| 4 | A **migration / replay plan** | History stays consistent (§4.12, §4.13) |
| 5 | A passing **CI compatibility gate** on the shared contract | Incompatible changes cannot ship |
| 6 | A **deprecation window** for any breaking change | No hard cutovers (§4.10) |

Additive changes (new optional fields) flow through this process quickly; breaking changes require the full transition machinery. The cost of this discipline is a small amount of process friction; the cost of *not* having it is breaking every downstream consumer at once. *Recorded as ADR-030 (canonical event change control / freeze).*

---

# Appendix A — Data Dictionary

The single field-level reference for the platform. Identifiers in examples use the external prefixed form (§4.19); the internal key is UUIDv7 (except `event_id`, which is deterministic). Model and provider values are illustrative.

### A.1 Usage Event fields

| Field | Description | Example | Type | Required | Mutability | Owner |
|---|---|---|---|---|---|---|
| `event_id` | Deterministic event identity (idempotency key) | `evt_01HQ…` | string | Yes | Immutable | Event |
| `schema_version` | Event-type contract version | `3` | integer | Yes | Immutable | Event |
| `event_version` | Record revision (latest wins) | `1` | integer | Yes | Derived | Event |
| `org_id` | Organization identifier | `org_123` | id | Yes | Immutable | Identity |
| `region` | Residency region | `us-east-1` | string | Yes | Immutable | Identity |
| `project_id` | Attribution target | `proj_456` | id | Yes (post-enrich) | Derived | Organization |
| `provider` | AI provider | `openai` | string | Yes | Immutable | Provider |
| `model` | AI model | `gpt-5.x` | string | Yes | Immutable | Provider |
| `prompt_tokens` | Input token count | `1234` | integer | Yes | Immutable | Event |
| `completion_tokens` | Output token count | `567` | integer | Yes | Immutable | Event |
| `cached_tokens` | Prompt-cache tokens | `200` | integer | No | Immutable | Event |
| `reasoning_tokens` | Reasoning/thinking tokens | `89` | integer | No | Immutable | Event |
| `total_tokens` | Sum of token components | `1890` | integer | Yes | Derived | Event |
| `requests` | API calls represented | `1` | integer | Yes | Immutable | Event |
| `latency_ms` | Request latency | `842` | number | No | Immutable | Event |
| `cost_amount` | Calculated cost (decimal) | `0.2300` | decimal | Yes | Derived | Analytics |
| `currency` | ISO 4217 currency | `USD` | string | Yes | Derived | Analytics |
| `pricing_version` | Pricing record used | `prc_789` | id | Yes | Derived | Pricing |
| `request_id` | Provider request id | `req_abc` | string | No | Immutable | Provider |
| `correlation_id` | Caller trace id | `corr_xyz` | string | No | Immutable | Event |
| `source` | Provenance | `push_sdk` | enum | Yes | Immutable | Event |
| `raw_ref` | Archive pointer | `s3://…/evt_01HQ` | string | Yes | Immutable | Event |
| `event_time` | When usage occurred (UTC) | `2026-06-26T12:00:00Z` | timestamp | Yes | Immutable | Provider |
| `ingest_time` | When received (UTC) | `2026-06-26T12:00:01Z` | timestamp | Yes | Immutable | Event |
| `processing_time` | When costed (UTC) | `2026-06-26T12:00:03Z` | timestamp | Yes | Derived | Event |
| `status` | Lifecycle status | `provisional` | enum | Yes | Lifecycle | Event |
| `adjustment_of` | Event this corrects | `evt_01HP…` | id | No | Immutable | Event |
| `tags` | Attribution dimensions | `{team: data}` | map | No | Derived | Organization |
| `processing_metadata` | Pipeline diagnostics | `{retries: 0}` | object | Yes | Derived | Event |

### A.2 Entity fields (key columns)

| Entity | Field | Description | Example | Required | Owner |
|---|---|---|---|---|---|
| Organization | `org_id` | Organization id | `org_123` | Yes | Identity |
| | `name` | Display name | `Acme Inc` | Yes | Identity |
| | `plan` | Subscription plan | `growth` | Yes | Organization |
| | `region` | Residency region | `eu-west-1` | Yes | Identity |
| | `status` | Account status | `active` | Yes | Identity |
| | `deleted_at` | Soft-delete marker | `null` | No | Identity |
| User | `user_id` | User id | `usr_234` | Yes | Identity |
| | `org_id` | Owning org | `org_123` | Yes | Identity |
| | `email` | Email (PII) | `a@acme.com` | Yes | Identity |
| | `role` | RBAC role | `admin` | Yes | Identity |
| Project | `project_id` | Project id | `proj_456` | Yes | Organization |
| | `org_id` | Owning org | `org_123` | Yes | Organization |
| | `name` | Display name | `checkout-svc` | Yes | Organization |
| | `attribution_tags` | Default tags | `{team: pay}` | No | Organization |
| Provider Connection | `connection_id` | Connection id | `conn_567` | Yes | Provider |
| | `provider` | Provider | `anthropic` | Yes | Provider |
| | `status` | Connection state | `healthy` | Yes | Provider |
| | `credential_ref` | Secret reference | `sec_…` | Yes | Identity |
| | `last_synced_at` | Last successful pull | `2026-06-26T…Z` | No | Provider |
| Pricing Record | `pricing_id` | Pricing id | `prc_789` | Yes | Pricing |
| | `provider` / `model` | Scope | `openai` / `gpt-5.x` | Yes | Pricing |
| | `input_price` | Per-unit input price (decimal) | `0.0000025` | Yes | Pricing |
| | `output_price` | Per-unit output price (decimal) | `0.000010` | Yes | Pricing |
| | `currency` | ISO 4217 | `USD` | Yes | Pricing |
| | `effective_from` / `effective_to` | Validity window | `2026-06-01T…Z` | Yes / No | Pricing |
| Budget | `budget_id` | Budget id | `bgt_678` | Yes | Governance |
| | `scope_type` / `scope_id` | Org or project scope | `project` / `proj_456` | Yes | Governance |
| | `limit` | Limit (decimal) | `5000.00` | Yes | Governance |
| | `period` | Reset period | `monthly` | Yes | Governance |
| | `thresholds` | Warning/critical levels | `{warn: 80, crit: 95}` | Yes | Governance |
| | `state` | Budget state | `warning` | Yes | Governance |
| Policy | `policy_id` | Policy id | `pol_789` | Yes | Governance |
| | `type` / `rules` | Rule definition | `model_cap` | Yes | Governance |
| Alert | `alert_id` | Alert id | `alr_890` | Yes | Alert |
| | `source_type` / `source_id` | Origin | `budget` / `bgt_678` | Yes | Alert |
| | `severity` / `status` | Level / state | `critical` / `raised` | Yes | Alert |
| Report | `report_id` | Report id | `rpt_901` | Yes | Reporting |
| | `type` / `status` | Kind / state | `monthly` / `ready` | Yes | Reporting |
| | `artifact_ref` | Object-store key | `s3://…/rpt_901` | Yes | Reporting |
| | `expires_at` | Expiry | `2026-09-26T…Z` | No | Reporting |
| Notification | `notification_id` | Delivery id | `ntf_012` | Yes | Alert |
| | `alert_id` / `channel` | Source / channel | `alr_890` / `email` | Yes | Alert |
| | `status` / `attempts` | Delivery state | `sent` / `1` | Yes | Alert |
| Audit Log | `audit_id` | Audit id | `aud_123` | Yes | Platform |
| | `actor_id` / `action` | Who / what | `usr_234` / `budget.updated` | Yes | Platform |
| | `entity_type` / `entity_id` | Target | `budget` / `bgt_678` | Yes | Platform |
| | `occurred_at` | When (UTC) | `2026-06-26T…Z` | Yes | Platform |

---

_End of Chapter 4, Part 2. The Data Dictionary (Appendix A) is the field-level contract referenced by Chapter 5 (API request/response shapes) and the SDK. New decisions are recorded as ADR-024 through ADR-030 in the register (§3.24)._
