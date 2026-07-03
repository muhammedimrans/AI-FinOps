# AWS Lambda + COSTORAH example

A minimal Lambda function demonstrating the integration named in
EP-18.6's Success Criteria: `export const handler = costorahLambda(...)`
plus automatic OpenAI instrumentation. Written to work behind a Lambda
Function URL or an API Gateway HTTP API (v2) — both use the same
`requestContext.http.method`/`rawPath` event shape `costorahLambda`
recognizes; see `sdk/docs/AWS_LAMBDA.md` for the full list of supported
event shapes (API Gateway v1, ALB, EventBridge/SQS/SNS).

## Setup

```bash
cd sdk/examples/aws-lambda
npm install
```

Set `COSTORAH_API_KEY` (and `OPENAI_API_KEY` for `/chat`) as environment
variables on the deployed function — see `.env.example` for the names.

## Test locally (no deployment needed)

```bash
node -e "
import('./handler.mjs').then(async ({ handler }) => {
  const result = await handler(
    { rawPath: '/', requestContext: { http: { method: 'GET' } } },
    { awsRequestId: 'local-test-1' },
  );
  console.log(result);
});
"
# { statusCode: 200, body: '{"status":"ok"}' }
```

## Deploy

Package and deploy with your preferred tool (SAM, CDK, Serverless
Framework, or the AWS console) — `handler.mjs`'s `handler` export is a
standard Lambda handler, no special build step required beyond bundling
`node_modules`.

## What to expect

- Responses include an `X-Costorah-Request-Id` header (via the returned
  proxy-integration response object's `headers`).
- The client is reused across warm invocations — see
  `sdk/docs/AWS_LAMBDA.md`'s "Context reuse" section.
- The `/chat` route triggers `OpenAIInstrumentor`, which captures the
  response's token usage and cost and submits it to COSTORAH
  automatically — no manual `client.track()` call anywhere in
  `handler.mjs`.
