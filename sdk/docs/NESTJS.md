# NestJS Guide (EP-18.6)

## Install

```bash
npm install @costorah/sdk @nestjs/common @nestjs/core rxjs
export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
```

`@nestjs/common`/`@nestjs/core`/`rxjs` are **peerDependencies** of
`@costorah/sdk` — not bundled. This is the one deliberate exception to
this SDK's zero-runtime-dependency guarantee (see `SECURITY.md`): real
Nest decorators (`@Module`, `@Injectable`, ...) must be genuine runtime
imports for Nest's reflection-based DI to recognize the resulting
classes, so there's no way to make this integration structurally-typed
the way the Express/Node integrations are.

## Quick start

```typescript
import { CostorahModule } from "@costorah/sdk/nest";

@Module({
  imports: [
    CostorahModule.forRoot({ apiKey: process.env.COSTORAH_API_KEY }),
  ],
})
export class AppModule {}
```

That's the entire integration. `forRoot()`:

- Auto-initializes a `Costorah` client and wires it as the default
  client every instrumentor submits through.
- Provides the client via Nest's DI container (`@InjectCostorah()`).
- Registers `CostorahInterceptor` as a global `APP_INTERCEPTOR` by
  default — every request gets automatic request-context capture with
  zero additional wiring. Set `autoInterceptor: false` to opt out.

## Async configuration

```typescript
CostorahModule.forRootAsync({
  imports: [ConfigModule],
  inject: [ConfigService],
  useFactory: (config: ConfigService) => ({
    apiKey: config.get("COSTORAH_API_KEY"),
  }),
});
```

## What gets captured

Per request: request ID (`X-Request-Id` header, or generated), route,
method, optional organization ID — attached to
`metadata.requestContext` on every usage event captured during that
request, and echoed back via an `X-Costorah-Request-Id` response
header. Non-HTTP execution contexts (RPC, WebSockets) pass through the
interceptor unmodified.

## Interceptor vs. Middleware

Two ways to apply request-context capture, both included:

- **`CostorahInterceptor`** (the default, via `forRoot()`) — a global
  `APP_INTERCEPTOR`. Simplest; matches every other integration's
  "one line, zero additional wiring" behavior.
- **`CostorahMiddleware`** — for apps that prefer Nest's
  `MiddlewareConsumer` API, e.g. to scope capture to specific route
  patterns:

  ```typescript
  export class AppModule implements NestModule {
    configure(consumer: MiddlewareConsumer) {
      consumer.apply(CostorahMiddleware).forRoutes("api/*");
    }
  }
  ```

  Set `autoInterceptor: false` in `forRoot()` when using
  `CostorahMiddleware` instead, to avoid double-capturing.
  `CostorahMiddleware` delegates to `costorahNodeMiddleware` from
  `@costorah/sdk/node` internally — no duplicate request-handling logic.

## Decorator

`@InjectCostorah()` — a better-named alias for
`@Inject(COSTORAH_CLIENT)`:

```typescript
constructor(@InjectCostorah() private readonly costorah: Costorah) {}
```

## A note on implicit vs. explicit dependency injection

This integration's own classes (`CostorahInterceptor`,
`CostorahMiddleware`) use **explicit** `@Inject(COSTORAH_MODULE_OPTIONS)`
tokens rather than relying on Nest's implicit constructor-parameter-type
injection. This matters if your own build/test pipeline transforms
TypeScript with esbuild (e.g. Vitest's default transform) instead of
`tsc` or `@swc/core`'s decorator-metadata plugin: esbuild does not emit
the `design:paramtypes` reflect-metadata Nest's *implicit* DI depends
on, so implicit-type constructor injection silently fails under
esbuild-transformed tests (the injected value is `undefined`) even
though it works correctly with `tsc`/SWC and in a real running app.
Explicit `@Inject(Token)` tokens sidestep this entirely — recommended
for your own providers too if you test them under Vitest without an SWC
plugin.

## Version compatibility

Targets NestJS 10+ and 11+ (peerDependency range `^10.0.0 || ^11.0.0`).

## Troubleshooting

- **`@InjectCostorah()` resolves `undefined`** — confirm
  `CostorahModule.forRoot()` is imported somewhere reachable from the
  module requesting injection (it's a global module by default, unless
  `isGlobal: false` was passed).
- **No `X-Costorah-Request-Id` header** — confirm `autoInterceptor`
  wasn't set to `false` without an equivalent `CostorahMiddleware`
  registration.
