import { Inject } from "@nestjs/common";

import { COSTORAH_CLIENT } from "./constants.js";

/**
 * Parameter decorator injecting the `Costorah` client
 * `CostorahModule.forRoot()` constructed — a thin, better-named alias
 * for `@Inject(COSTORAH_CLIENT)`:
 *
 *     constructor(@InjectCostorah() private readonly costorah: Costorah) {}
 */
export const InjectCostorah = (): ParameterDecorator => Inject(COSTORAH_CLIENT);
