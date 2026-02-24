module.exports = {
  root: true,
  parser: "@typescript-eslint/parser",
  plugins: ["@typescript-eslint"],
  extends: ["eslint:recommended", "plugin:@typescript-eslint/recommended", "prettier"],
  env: {
    es2022: true,
    node: true,
    browser: true
  },
  ignorePatterns: [
    "node_modules/",
    ".next/",
    "dist/",
    "coverage/",
    "apps/api/.venv/",
    "**/*.d.ts"
  ]
};
