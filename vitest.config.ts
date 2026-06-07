import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      include: ["src/**"],
      exclude: [
        "**/*.test.{ts,tsx}",
        "**/test/**",
        "**/*.d.ts",
        "**/main.tsx",
      ],
    },
  },
});
