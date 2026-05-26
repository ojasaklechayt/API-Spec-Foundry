import type { CreateClientConfig } from "../client/client.gen";

// Production builds serve the frontend from the same origin as the backend —
// empty baseURL makes axios use relative URLs. Dev (`pnpm dev`) hits the
// standalone backend on :8000.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.PROD ? "" : "http://localhost:8000");

export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  baseURL: API_BASE_URL,
  throwOnError: true,
});
