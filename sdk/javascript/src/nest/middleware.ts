import type { NestMiddleware } from "@nestjs/common";
import { Inject, Injectable, Optional } from "@nestjs/common";

import { costorahNodeMiddleware } from "../node.js";
import type { MinimalIncomingMessage, MinimalServerResponse } from "../node.js";
import { COSTORAH_MODULE_OPTIONS } from "./constants.js";
import type { CostorahModuleOptions } from "./types.js";

/**
 * CostorahMiddleware — an alternative to `CostorahInterceptor` for apps
 * that prefer Nest's `MiddlewareConsumer` API (e.g. to scope capture to
 * specific route patterns via `.forRoutes(...)`) over a global
 * interceptor. Delegates to `costorahNodeMiddleware` from `../node.js`
 * — no duplicate request-handling logic — built once per middleware
 * instance (Nest instantiates middleware once per module registration,
 * not per request) so client auto-init only runs once.
 *
 *     export class AppModule implements NestModule {
 *       configure(consumer: MiddlewareConsumer) {
 *         consumer.apply(CostorahMiddleware).forRoutes("*");
 *       }
 *     }
 */
@Injectable()
export class CostorahMiddleware implements NestMiddleware {
  private readonly wrapped: (
    req: MinimalIncomingMessage,
    res: MinimalServerResponse,
    next: () => void,
  ) => void;

  constructor(
    @Optional() @Inject(COSTORAH_MODULE_OPTIONS) options?: CostorahModuleOptions,
  ) {
    this.wrapped = costorahNodeMiddleware(options ?? {});
  }

  use(req: MinimalIncomingMessage, res: MinimalServerResponse, next: () => void): void {
    this.wrapped(req, res, next);
  }
}
