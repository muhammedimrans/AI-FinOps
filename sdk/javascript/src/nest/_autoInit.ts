import { Costorah } from "../client.js";
import { CostorahError } from "../errors.js";
import { createConsoleLogger } from "../logging.js";

const _log = createConsoleLogger();

export function autoInitCostorahClient(apiKey: string | undefined): Costorah | undefined {
  const resolvedKey = apiKey ?? process.env.COSTORAH_API_KEY;
  if (!resolvedKey) {
    _log.warn(
      "costorah_nest_no_api_key: set COSTORAH_API_KEY, or pass apiKey:/client: to " +
        "CostorahModule.forRoot() — instrumentation will still capture usage locally " +
        "(eventsCaptured) but nothing will be submitted",
    );
    return undefined;
  }
  try {
    const endpoint = process.env.COSTORAH_ENDPOINT ?? "https://api.costorah.com";
    return new Costorah({ apiKey: resolvedKey, endpoint });
  } catch (err) {
    if (err instanceof CostorahError) {
      _log.warn(`costorah_nest_init_failed: ${err.message}`);
      return undefined;
    }
    throw err;
  }
}
