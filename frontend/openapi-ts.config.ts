import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "http://localhost:8000/openapi.json",
  output: "src/client/",
  plugins: [
    "@hey-api/typescript",
    {
      name: "@hey-api/client-axios",
      runtimeConfigPath: "./src/api/runtime-config.ts",
    },
    "@hey-api/schemas",
    {
      name: "@hey-api/transformers",
      dates: true,
    },
    {
      name: "@hey-api/sdk",
      transformer: true,
    },
  ],
});
