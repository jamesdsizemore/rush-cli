# Tutorial: set up a JavaScript/TypeScript project

**Outcome:** use installed JS/TS quality tools through Rush.

**Prerequisites:** Rush, Node/npm, and a project with `package.json`.

1. Install the helpers your team adopts:
   ```bash
   npm install --save-dev eslint prettier vitest typescript knip jscpd
   ```
2. Ensure each helper has its normal project configuration.
3. Run:
   ```bash
   rush lint .
   rush format . --check
   rush typecheck .
   rush dead .
   rush complexity .
   rush test .
   rush security .
   ```
4. If an engine skips, run that engine directly to confirm `PATH` and configuration.

**Expected:** Rush aggregates canonical results. It does not generate ESLint, Prettier, Vitest, or TypeScript configuration.

**Next:** [Before a pull request](before-a-pull-request.md).
