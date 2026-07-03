/**
 * @costorah/sdk/nest — NestJS integration (EP-18.6).
 *
 *     @Module({
 *       imports: [
 *         CostorahModule.forRoot({ apiKey: process.env.COSTORAH_API_KEY }),
 *       ],
 *     })
 *     export class AppModule {}
 *
 * Unlike every other integration in this SDK, `@costorah/sdk/nest`
 * requires `@nestjs/common`/`@nestjs/core`/`rxjs` to be installed —
 * these are declared as peerDependencies (see `package.json`), not
 * bundled, since real Nest decorators (`@Module`, `@Injectable`, ...)
 * must be genuine runtime imports for Nest's reflection-based DI to
 * recognize the resulting classes; there is no way to make a NestJS
 * integration structurally-typed the way `express.ts`/`node.ts` are.
 * This is the one deliberate, documented exception to this SDK's
 * zero-runtime-dependency guarantee, scoped entirely to this subpath —
 * `@costorah/sdk`'s main entry point still has none.
 */

export { COSTORAH_CLIENT, COSTORAH_MODULE_OPTIONS } from "./constants.js";
export { InjectCostorah } from "./decorators.js";
export { CostorahInterceptor } from "./interceptor.js";
export { CostorahMiddleware } from "./middleware.js";
export { CostorahModule } from "./module.js";
export type { CostorahModuleAsyncOptions, CostorahModuleOptions } from "./types.js";
