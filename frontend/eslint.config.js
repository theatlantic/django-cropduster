import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import prettier from "eslint-config-prettier";

export default tseslint.config(
  {
    ignores: [
      "dist/",
      "node_modules/",
      "coverage/",
      "tests/golden/",
      "playwright-report/",
      "test-results/",
    ],
  },
  js.configs.recommended,
  tseslint.configs.recommended,
  reactHooks.configs.recommended,
  {
    // Downstream scripts and django-autosave update the server-rendered
    // formset directly, so React must not render another set of named inputs.
    files: ["src/**/*.tsx"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='name']",
          message:
            "The widget must not render named form inputs; write through FormsetBridge instead.",
        },
      ],
    },
  },
  prettier,
);
