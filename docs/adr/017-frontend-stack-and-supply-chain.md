# 017. Frontend stack and its supply chain

## Status

Accepted. This is P3-6.

## Context

P3-6 adds the browser game in `frontend/`. It is the first JavaScript in the repository, so it brings a second package ecosystem into CI, into every lane, and into the operator's laptop. npm packages can run code at install time, can be republished by a compromised maintainer, and arrive as a tree of hundreds of transitive dependencies. The game itself has hard requirements that constrain the stack: the API is same-origin only (the session cookie is scoped to `/games/{id}`), the suspect turn is a WebSocket stream that OpenAPI does not describe, and no response, page, or browser storage may hold a spoiler before the reveal.

## Decision

**Stack.** Vite 8.3.4 and React 19.3.0 on TypeScript 6.0.3 in strict mode. React Router 8.4.0 for three routes, TanStack Query 5.104.1 as the only cache of server state, openapi-fetch 0.17.0 over types that openapi-typescript 7.13.0 generates from the backend's `/openapi.json` into `src/api-types.ts`. Tailwind CSS 4.3.3, a few shadcn/ui components copied into `src/components/ui/` and adapted to Base UI 1.9.0, lucide-react icons, and sonner toasts. Vitest 5.0.3 for units and Playwright 1.64.0 for end-to-end tests. ESLint 10 with typescript-eslint `strictTypeChecked` and the React hooks rules, and Prettier.

**One wire module.** `src/api.ts` is the only file that may import `api-types.ts` or `openapi-fetch`. It mints idempotency keys, stamps `state_version`, retries `stale_state` once with the same key, parses Problems, decodes the hand-written WebSocket frames, and drops `score` from search hits. An ESLint `no-restricted-imports` rule enforces the boundary and names `@/api` in its message. The same rule bans importing anything under `cases/` or any JSON, and `no-restricted-syntax` bans `dangerouslySetInnerHTML`. `make api-types` regenerates the types without starting a server, and CI fails when the committed file differs.

**Versions.** Every dependency is pinned exactly in `package.json` and locked in `package-lock.json`. `frontend/.npmrc` sets:

| Setting | Effect |
|---|---|
| `save-exact=true` | `npm install <pkg>` writes an exact version, never a range |
| `min-release-age=14` | npm refuses any version published in the last 14 days, so a hijacked release has two weeks to be caught before it can land here |
| `ignore-scripts=true` | no package runs `preinstall`, `install`, or `postinstall` code; none of ours needs to |
| `engine-strict=true` | an install on the wrong Node fails instead of half-working |
| `audit-level=high` | `npm audit` fails on high or critical advisories |

`make audit` runs `npm audit` and `npm audit signatures` next to the Python audit. `npm audit signatures` checks the registry signatures and provenance attestations of every installed package. Dependabot proposes npm bumps with a 14-day cooldown, so its pull requests respect the same age rule.

**Node.** Node 24.21.0, the active LTS line, pinned in `frontend/.nvmrc` and `engines`. `scripts/install_pkgs.sh` installs exactly that version from nodejs.org when `node -v` differs, after checking the tarball against the release's `SHASUMS256.txt`, and the Makefile puts it first on `PATH`. CI reads the same file through `actions/setup-node`. Node 22 is not enough: npm 10 on Node 22 crashes resolving the Vitest 5 peer graph.

**Base UI over Radix.** Base UI comes from the people behind Radix and Material UI, ships one package instead of one per primitive, and shadcn/ui supports it as an alternative to Radix. The game needs only a dialog and tabs, so the smaller tree wins.

**TypeScript 6, not 7.** typescript-eslint 8.71 supports TypeScript below 6.1, and TypeScript 7 (the native compiler) has no typed-linting API yet. openapi-typescript 7.13.0 still declares a `typescript ^5` peer, so `package.json` has an `overrides` entry that gives it 6.0.3. The generated file is identical in shape under 6.0.3; `make api-types` and the CI drift check prove it on every run.

**Testing Library and jsdom are not installed.** The behavior worth testing at unit level (the turn reducer, retries, frame parsing, highlights) is pure TypeScript, and Playwright drives the real components. Two fewer packages and their trees stay out.

## Consequences

- A new dependency costs a review of its tree, an exact pin, and 14 days of age. That slows urgent upgrades on purpose. An emergency security fix younger than 14 days needs a one-time `--min-release-age=0` and a line in the PR description.
- With `ignore-scripts`, a package that needs a build step at install time (native addons, esbuild's binary download) does not work. Vite 8 bundles Rolldown as prebuilt platform packages and needs none.
- Playwright browsers are installed outside npm: `npx playwright install --with-deps chromium` in CI. A machine whose preinstalled Chromium has another revision sets `PW_CHROMIUM_PATH`.
- Watch list. `clsx`, `class-variance-authority`, and `sonner` each have a single maintainer and publish without npm provenance, so `npm audit signatures` can verify their registry signature but not their build. They are small and stable. If any of them changes owner or ships an unexpected release, vendor the few lines we use instead of upgrading.
