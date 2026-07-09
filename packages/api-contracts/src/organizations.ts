import type { OrganizationId, ISOTimestamp, Status } from "@costorah/shared-types";

/** Organization resource. */
export interface Organization {
  readonly id: OrganizationId;
  readonly name: string;
  readonly slug: string;
  readonly status: Status;
  readonly createdAt: ISOTimestamp;
  readonly updatedAt: ISOTimestamp;
}

/** POST /v1/organizations */
export interface CreateOrganizationRequest {
  readonly name: string;
  readonly slug: string;
}

/** PATCH /v1/organizations/:id */
export interface UpdateOrganizationRequest {
  readonly name?: string;
}
