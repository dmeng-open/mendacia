import reactHooks from "eslint-plugin-react-hooks";
import { defineConfig } from "eslint/config";
import tseslint from "typescript-eslint";

const wire = {
  group: ["**/api-types", "**/api-types.ts", "openapi-fetch"],
  message:
    "Only src/api.ts speaks the wire format. Import domain types and verbs from '@/api' instead.",
};
const caseFiles = {
  group: ["**/cases/**", "**/*.json"],
  message:
    "Case files hold the solution. The UI learns a case only through the API, and e2e scripts live in e2e/walkthroughs.ts.",
};

export default defineConfig([
  { ignores: ["dist", "playwright-report", "test-results", "src/api-types.ts"] },
  tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
      "no-restricted-imports": ["error", { patterns: [wire, caseFiles] }],
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message:
            "Render text as React children. Search highlights arrive as parsed spans from '@/api'.",
        },
      ],
    },
  },
  {
    files: ["src/api.ts"],
    rules: { "no-restricted-imports": ["error", { patterns: [caseFiles] }] },
  },
  {
    files: ["src/**/*.tsx", "src/**/*.ts"],
    ...reactHooks.configs.flat.recommended,
  },
  {
    files: ["eslint.config.js"],
    extends: [tseslint.configs.disableTypeChecked],
  },
]);
