import js from "@eslint/js";
import globals from "globals";

export default [
  { ignores: ["**/vendor/**", "node_modules/**"] },
  js.configs.recommended,
  {
    files: ["custom_components/**/www/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: globals.browser,
    },
    rules: {
      // Правила из javascript-guidelines.md §7, которые ловятся статически.
      "no-console": "error",
      eqeqeq: ["error", "always", { null: "ignore" }],
      "no-var": "error",
      "prefer-const": "error",
      "no-param-reassign": "error",
      "no-empty": ["error", { allowEmptyCatch: false }],
      "require-await": "error",
      "no-return-await": "error",
    },
  },
];
