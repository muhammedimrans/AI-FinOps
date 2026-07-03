import type { DynamicModule, Provider } from "@nestjs/common";
import { Module } from "@nestjs/common";
import { APP_INTERCEPTOR } from "@nestjs/core";

import { setDefaultClient } from "../instrumentation/submission.js";
import { autoInitCostorahClient } from "./_autoInit.js";
import { COSTORAH_CLIENT, COSTORAH_MODULE_OPTIONS } from "./constants.js";
import { CostorahInterceptor } from "./interceptor.js";
import type { CostorahModuleAsyncOptions, CostorahModuleOptions } from "./types.js";

/**
 * CostorahModule — NestJS integration (EP-18.6).
 *
 *     @Module({
 *       imports: [
 *         CostorahModule.forRoot({ apiKey: process.env.COSTORAH_API_KEY }),
 *       ],
 *     })
 *     export class AppModule {}
 *
 * With `COSTORAH_API_KEY` set (in `forRoot({ apiKey })` or the
 * environment), this is the entire integration — no other setup.
 * `forRoot` auto-initializes a `Costorah` client, wires it as the
 * default client every instrumentor submits through, provides it via
 * Nest's DI container (`@InjectCostorah()`), and — by default —
 * registers `CostorahInterceptor` as a global `APP_INTERCEPTOR`, so
 * every request through the app gets automatic request-context capture
 * with zero additional wiring. Set `autoInterceptor: false` to opt out
 * and apply `CostorahInterceptor`/`CostorahMiddleware` selectively
 * instead (see their own docstrings).
 */
@Module({})
export class CostorahModule {
  static forRoot(options: CostorahModuleOptions = {}): DynamicModule {
    const client = options.client ?? autoInitCostorahClient(options.apiKey);
    if (client) setDefaultClient(client);

    const optionsProvider: Provider = { provide: COSTORAH_MODULE_OPTIONS, useValue: options };
    const clientProvider: Provider = { provide: COSTORAH_CLIENT, useValue: client };

    return {
      module: CostorahModule,
      global: options.isGlobal ?? true,
      providers: [
        optionsProvider,
        clientProvider,
        ...interceptorProviders(options.autoInterceptor ?? true),
      ],
      exports: [optionsProvider, clientProvider],
    };
  }

  static forRootAsync(options: CostorahModuleAsyncOptions): DynamicModule {
    const optionsProvider: Provider = {
      provide: COSTORAH_MODULE_OPTIONS,
      useFactory: options.useFactory,
      inject: options.inject ?? [],
    };
    const clientProvider: Provider = {
      provide: COSTORAH_CLIENT,
      useFactory: (resolved: CostorahModuleOptions) => {
        const client = resolved.client ?? autoInitCostorahClient(resolved.apiKey);
        if (client) setDefaultClient(client);
        return client;
      },
      inject: [COSTORAH_MODULE_OPTIONS],
    };

    return {
      module: CostorahModule,
      global: options.isGlobal ?? true,
      imports: options.imports ?? [],
      providers: [
        optionsProvider,
        clientProvider,
        ...interceptorProviders(options.autoInterceptor ?? true),
      ],
      exports: [optionsProvider, clientProvider],
    };
  }
}

function interceptorProviders(autoInterceptor: boolean): Provider[] {
  if (!autoInterceptor) return [];
  return [{ provide: APP_INTERCEPTOR, useClass: CostorahInterceptor }];
}
