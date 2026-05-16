import { defineConfig } from "vitest/config";

/**
 * EB-264: Standard vitest config (no Workers pool).
 *
 * Tests run in Node.js environment. The KV bindings are mocked in each test file.
 * This covers sanitize, rate-limit, and turnstile unit tests without needing
 * the Workers runtime.
 *
 * For full Workers integration testing (CORS preflight, request lifecycle),
 * use `wrangler dev` with curl test scripts (see README.md).
 *
 * Note: @cloudflare/vitest-pool-workers 0.8.x requires vitest ^2.x, but the
 * 0.8.71 release installed has an API incompatibility with vitest 2.1.9
 * (startCurrentRun not found). Using standard vitest for unit coverage.
 */
export default defineConfig({
  test: {
    environment: "node",
    globals: false,
  },
});
