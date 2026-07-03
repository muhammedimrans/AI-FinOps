/**
 * Next Middleware (Edge Runtime) — the same `costorahHandler` used for
 * App Router Route Handlers works here too, since both are
 * Request -> Response functions. This example just tags every request
 * with ambient context and lets it continue.
 */
import { NextResponse } from "next/server";

import { costorahHandler } from "@costorah/sdk/next";

export default costorahHandler(async () => {
  return NextResponse.next();
});
