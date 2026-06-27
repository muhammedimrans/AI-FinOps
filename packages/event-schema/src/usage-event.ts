import type {
  ISOTimestamp,
  OrganizationId,
  ProjectId,
  UsageEventId,
  IdempotencyKey,
  TokenUsage,
  TokenCost,
} from "@ai-finops/shared-types";
import { Provider, Modality, ReconciliationState } from "@ai-finops/shared-types";
import type { EventSchemaVersion } from "./schema-version.js";

/**
 * Core usage event — the atomic unit of AI cost tracking.
 *
 * Push events (from SDK) arrive as UsageEventInput and are stored as
 * UsageEvent. Adapter workers produce the same shape from provider billing data.
 * The reconciliation engine upgrades provisional events to reconciled ones.
 */
export interface UsageEvent {
  readonly id: UsageEventId;
  readonly schemaVersion: EventSchemaVersion;

  /** Owning organization. */
  readonly organizationId: OrganizationId;

  /** Owning project — the attribution unit for cost allocation. */
  readonly projectId: ProjectId;

  /** Provider that served the request. */
  readonly provider: Provider;

  /** Provider's canonical model identifier, e.g. "gpt-4o-2024-08-06". */
  readonly model: string;

  readonly modality: Modality;

  /** When the request was sent to the provider. */
  readonly requestedAt: ISOTimestamp;

  /** When the provider returned a response. Null for streaming where end time is tracked separately. */
  readonly completedAt: ISOTimestamp | null;

  /** Latency in milliseconds. */
  readonly latencyMs: number | null;

  readonly tokenUsage: TokenUsage;
  readonly tokenCost: TokenCost;

  /** Arbitrary key-value labels for custom attribution (team, env, feature, etc.). */
  readonly labels: Readonly<Record<string, string>>;

  /** Provider's own request ID for cross-referencing in reconciliation. */
  readonly providerRequestId: string | null;

  readonly reconciliationState: ReconciliationState;

  /** The idempotency key supplied by the caller. Null for adapter-pull events. */
  readonly idempotencyKey: IdempotencyKey | null;

  readonly createdAt: ISOTimestamp;
  readonly updatedAt: ISOTimestamp;
}

/**
 * Input shape for SDK push events.
 * cost fields are omitted — the platform calculates cost server-side.
 */
export interface UsageEventInput {
  readonly schemaVersion: EventSchemaVersion;
  readonly organizationId: OrganizationId;
  readonly projectId: ProjectId;
  readonly provider: Provider;
  readonly model: string;
  readonly modality?: Modality;
  readonly requestedAt: ISOTimestamp;
  readonly completedAt?: ISOTimestamp;
  readonly latencyMs?: number;
  readonly tokenUsage: TokenUsage;
  readonly labels?: Record<string, string>;
  readonly providerRequestId?: string;
  readonly idempotencyKey?: IdempotencyKey;
}

export { Provider, Modality, ReconciliationState };
