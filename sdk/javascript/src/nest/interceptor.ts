import type { CallHandler, ExecutionContext, NestInterceptor } from "@nestjs/common";
import { Inject, Injectable, Optional } from "@nestjs/common";
import type { Observable } from "rxjs";

import { runWithRequestContext } from "../context.js";
import type { MinimalIncomingMessage, MinimalServerResponse } from "../node.js";
import { COSTORAH_MODULE_OPTIONS } from "./constants.js";
import type { CostorahModuleOptions } from "./types.js";

function generateId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID().replace(/-/g, "")
    : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
}

/**
 * CostorahInterceptor — captures request context (request ID, path,
 * method, optional organization ID) around a route handler's
 * execution, and echoes the request ID back via an
 * `X-Costorah-Request-Id` response header. Registered automatically by
 * `CostorahModule.forRoot()` (unless `autoInterceptor: false`) as a
 * global `APP_INTERCEPTOR`; can also be applied selectively with
 * `@UseInterceptors(CostorahInterceptor)` on a specific controller or
 * route.
 *
 * Non-HTTP execution contexts (RPC, WebSockets) pass through
 * unmodified — there's no HTTP request/response to capture context
 * from or attach a header to.
 */
@Injectable()
export class CostorahInterceptor implements NestInterceptor {
  constructor(
    @Optional() @Inject(COSTORAH_MODULE_OPTIONS) private readonly options?: CostorahModuleOptions,
  ) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    if (context.getType() !== "http") {
      return next.handle();
    }

    const httpContext = context.switchToHttp();
    const req = httpContext.getRequest<MinimalIncomingMessage>();
    const res = httpContext.getResponse<MinimalServerResponse>();

    const headerRequestId = req.headers["x-request-id"];
    const requestId =
      (Array.isArray(headerRequestId) ? headerRequestId[0] : headerRequestId) ?? `req_${generateId()}`;

    const contextFields: Record<string, unknown> = {
      requestId,
      path: req.url ?? "",
      method: req.method ?? "",
    };
    if (this.options?.organizationId) contextFields.organizationId = this.options.organizationId;

    res.setHeader("X-Costorah-Request-Id", requestId);

    return runWithRequestContext(contextFields, () => next.handle());
  }
}
