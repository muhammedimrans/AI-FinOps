import type { InjectionToken, ModuleMetadata, OptionalFactoryDependency } from "@nestjs/common";

import type { Costorah } from "../client.js";

export interface CostorahModuleOptions {
  apiKey?: string | undefined;
  client?: Costorah;
  organizationId?: string | undefined;
  /** Registered as a Nest global module by default (so every feature
   * module can `@InjectCostorah()` without re-importing
   * `CostorahModule`) — set `false` to scope it to the importing
   * module instead. */
  isGlobal?: boolean;
  /** Automatically registers `CostorahInterceptor` as a global
   * `APP_INTERCEPTOR` — true by default, matching every other
   * integration's "one line, zero additional wiring" behavior. Set
   * `false` to apply `CostorahInterceptor`/`CostorahMiddleware`
   * selectively yourself instead. */
  autoInterceptor?: boolean;
}

export interface CostorahModuleAsyncOptions extends Pick<ModuleMetadata, "imports"> {
  useFactory: (...args: unknown[]) => Promise<CostorahModuleOptions> | CostorahModuleOptions;
  inject?: Array<InjectionToken | OptionalFactoryDependency>;
  isGlobal?: boolean;
  autoInterceptor?: boolean;
}
