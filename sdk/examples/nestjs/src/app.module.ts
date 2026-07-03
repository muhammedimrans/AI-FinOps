import { Module } from "@nestjs/common";
import { CostorahModule } from "@costorah/sdk/nest";

import { AppController } from "./app.controller.js";

/**
 * Minimal NestJS app instrumented with COSTORAH — demonstrating the
 * integration named in EP-18.6's Success Criteria:
 * `CostorahModule.forRoot({ apiKey })`.
 *
 * With COSTORAH_API_KEY set in the environment, this one import is the
 * entire integration — CostorahModule.forRoot() auto-registers
 * CostorahInterceptor as a global APP_INTERCEPTOR (see
 * sdk/docs/NESTJS.md), so every request gets automatic request-context
 * capture with no further wiring.
 */
@Module({
  imports: [CostorahModule.forRoot({ apiKey: process.env.COSTORAH_API_KEY })],
  controllers: [AppController],
})
export class AppModule {}
