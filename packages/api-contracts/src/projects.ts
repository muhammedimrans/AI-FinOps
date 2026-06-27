import type { OrganizationId, ProjectId, ISOTimestamp, Status } from "@ai-finops/shared-types";

/** Project resource — the cost attribution unit. */
export interface Project {
  readonly id: ProjectId;
  readonly organizationId: OrganizationId;
  readonly name: string;
  readonly slug: string;
  readonly description: string | null;
  readonly status: Status;
  readonly labels: Readonly<Record<string, string>>;
  readonly createdAt: ISOTimestamp;
  readonly updatedAt: ISOTimestamp;
}

/** POST /v1/organizations/:orgId/projects */
export interface CreateProjectRequest {
  readonly name: string;
  readonly slug: string;
  readonly description?: string;
  readonly labels?: Record<string, string>;
}

/** PATCH /v1/organizations/:orgId/projects/:projectId */
export interface UpdateProjectRequest {
  readonly name?: string;
  readonly description?: string;
  readonly labels?: Record<string, string>;
}
