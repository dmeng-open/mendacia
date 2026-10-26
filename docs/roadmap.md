# Mendacia roadmap

This is the full-project plan, final version. It describes where Mendacia goes after the MVP. Stages B1 and E are scheduled as Phases 6 and 7 of `docs/plan.md`, before the first deployment. **Nothing else here is scheduled.** Agents do not build from this file unless a phase of `docs/plan.md` points to a section of it. When a stage starts, its section becomes PRs in `docs/plan.md` with the same checklist format, and its rules move into `docs/spec.md`.

Sources:

- *Mendacia Product & Technology Plan v2.0* (2026-10-22), the long-term product blueprint.
- *v2.1* (2026-10-22), which built a game-aware zero-trust runtime into v2.0 without changing its product or its stages.
- What the operator brought back from Informanix Discover 2026.
- The proactive-agent route the operator designed in October 2026, recorded in ADR 016.

Prices, retention numbers, and session lengths below are hypotheses. No real player has tested them yet.

## 1. Positioning

Mendacia is an AI detective game and story universe that starts from one daily case the solver proves fair.

- **Detective mode.** The player questions AI suspects who protect their secrets, searches a mixed archive, and submits a chain of reasoning.
- **Killer mode.** The player builds and defends an alibi against a team of AI detectives. The detectives keep a belief state and check claims actively.
- **Living case.** Suspects do not wait to be asked. They hide a document, agree on a story, or approach the player with a distraction. Every such move is declared in the case and proven before release.

The three selling points:

1. "Every day, one case that is truly fair and provably solvable."
2. "Trustworthy AI characters you can question freely, and play against."
3. "The mystery fights back, fairly." Rivals, detectives, and suspects act on their own, inside bounds the solver proved.

Where this sits among existing games, as a hypothesis to test:

- Daily logic puzzles such as Murdle are fair and social, but nobody in them can be questioned.
- LLM interrogation games can be questioned, but they do not prove the case solvable, and their characters leak or invent facts under pressure.
- Hand-written detective games are deep, but their content runs out.
- Procedural simulations such as Shadows of Doubt react to the player, but they are not fair by construction.

Mendacia aims at all four at once: proven fair, freely questioned, new every day, and a world that reacts to the player.

The technical differentiators are formal verification, stateful agent workflows, authorized retrieval, game-aware policy enforcement, verified release, adversarial agent evals, and proactive agents whose reasoning runs on the solver.

Priority order, highest first: fun, correct game logic, enforceable permission boundaries, reliability and measurement, low running cost, then extensions on demand. Distributed parts arrive only when a measurement calls for them.

## 2. Players and pacing

- **Audience.** Fans of deduction, puzzles, murder-mystery parties, and daily challenges like Wordle.
- **Three entry points:**
  - a 5-minute tutorial or speed case,
  - a 15 to 20 minute daily standard case,
  - a 20 to 30 minute weekend deep case.

  Test the length preference with an A/B test before fixing the mix.
- **Guests** play at once with a server-bound anonymous session. Accounts are optional and only save progress.
- **Content limits.** No gore, no real people or real crimes, no model training on player data. Submissions are moderated.

## 3. Full feature map

| Area | Player experience | Technical core | Security contract |
|---|---|---|---|
| Detective mode | Question 4 to 6 suspects, search, accuse with a clue chain | LangGraph, fact subgraph, lie ledger, verifier | Suspects retrieve only granted knowledge; replies pass claim and privacy checks; legitimate confrontation triggers disclosure |
| Killer mode | Play the culprit and defend an alibi against AI detectives | Detective team, belief state, information-gain planning, contradiction detection | Detective tools are granted per investigation stage; no detective reads the solution; every decision is logged |
| Rival detective | An AI rival works the same daily case and races the player | The `belief` engine (§6.5): clingo candidates and information gain on a seeded step schedule | The rival reads only facts it found; its pace follows the player's questions, so every player of a daily case meets the same rival; its progress shows no fact the player has not found |
| Living case | Suspects hide documents, agree on stories, and approach the player | `planned_moves`, outbox triggers, the nine-step turn for proactive speech | Moves are declared in the case and proven; a move changes what a player can reach, never a fact |
| Async duels | A killer-mode alibi becomes a friend's detective case | Structured lie choices compiled to `planned_lies`, `check_case` | The duel case passes every solver check, and a lie no clue can expose fails it |
| Nemesis | A culprit the player failed to catch returns in later cases; characters remember the player | A relationship layer in the player data, story director briefs | Memory changes tone only in official play; every brief goes through the case pipeline |
| Evidence archive | Search dozens to hundreds of mixed real, false, and noise documents | Hybrid retrieval, graph links, SQL templates | Every hit is checked again against the ACL; no index crosses cases or players; text in documents is never an instruction |
| Daily case | Everyone plays the same case each day and compares fair scores | Offline generation, simulated play, scheduled publish, leaderboard | Release gate includes jailbreak regression; scores are computed on the server; a pinned `case_version`; a failure falls back to a verified case |
| Tutorial and difficulty | A real confrontation within 5 minutes, then a path to hard mode | Onboarding state machine, hint strategy, difficulty tiers | Safety refusals must not block a beginner; hints cite only unlocked facts |
| Detective profile | Case record, skill badges, ranked challenges | Progress, scoring, stats | Account and guest data are separate; minimal collection; no one sees another player's raw dialogue |
| Story seasons | A world, characters, and threads across daily cases | Versioned world canon, narrative dependencies | Canon versions stay separate from case solutions; new canon never rewrites a published case; knowledge crosses cases only through an explicit grant |
| Spoiler-free sharing and friend challenges | Result cards, invites to the same case, strategy comparison | Share tokens, social links, anti-cheat | Share projections and short-lived tokens hold no solution; no user can read another user's turns |
| Archive and premium stories | Free daily case, paid history, story seasons, case packs | Entitlements, payments | An entitlement controls content access only; it never grants a Truth bypass or an advantage in official play |
| Player submissions | Submit a mystery, get a machine bug report, publish after review | Extraction, fact modelling, solver, moderation | Submissions are untrusted. They are parsed in a sandbox with size limits, scanned for privacy, copyright, and malicious text, and can never change a system prompt |

## 4. Core loop and retention

### 4.1 First session

| Time | What the player gets |
|---|---|
| 0–30 s | The case hook and each suspect's first layer. No sign-up. The server issues an anonymous session bound to the game. |
| 30–90 s | The first question and a natural reply. Progress may show while the reply is checked. No unverified token is sent. |
| 2–3 min | The first checkable contradiction, then the archive opens. Search uses the current unlock state. |
| 3–5 min | A successful confrontation that moves the lie ledger, and a clear "my reasoning worked" moment. |
| After the accusation | The true timeline, the clue chain, and a result card. Only now is `solution_chain` readable. Making an account saves the record. |

### 4.2 Three retention loops

1. **Daily, D1–D7.** A fixed release time, the same case for everyone, catch-up play, and spoiler-free sharing. The client never prefetches tomorrow's hidden truth.
2. **Skill, D7–D30.** The profile tracks key-evidence finds, question efficiency, and performance by difficulty. A model failure never counts as a player mistake.
3. **Story, D30+.** Seasonal arcs, an archive of past cases, and cross-case foreshadowing. Every daily case is still solvable on its own.

### 4.3 Social

- Result cards show the case number, solved or not, questions, time, hints, and reasoning quality. They never show the culprit or restricted evidence.
- Friend challenges share the same `case_version` and ruleset version. Full questions and model output stay private by default.
- The submission pipeline: submit → extract → solver → simulated play → security scan → content and copyright review → publish. A report or takedown can withdraw sharing.
- Clubs and group leaderboards come only after solo retention is proven.

### 4.4 Anti-goals

Mendacia does not use:

- forced streaks,
- pay-to-see-the-answer,
- endless AI chat bait,
- free characters made worse to push sales.

Logs keep the structured events Mendacia needs. Raw dialogue is tiered by access level and kept for a limited time. A security audit is never a reason to make a player's dialogue public.

## 5. Monetization and unit economics

| Tier | Content | Rule it may not break |
|---|---|---|
| Free | The full daily case, full questioning, the debrief, sharing, a basic profile | The free case is complete and fairly solvable |
| Plus | The full case archive, long story seasons, extra themed files, deeper stats | Never sells a clue needed to solve or a way around a security policy |
| Case pack | A themed pack of about 5 cases | Unlocks content; never raises fact access in official play |
| Cosmetics (optional) | Profile skins, badges, desk themes | No effect on rank or clue visibility |

Pricing hypothesis from v2.0: Plus at about US$4.99 per month, case packs at US$4.99 to 9.99. Test packs on real players before building subscriptions.

**Cost per game:**

> case generation (amortized) + suspect replies + claim extraction and verification retries + hints and detective reasoning + embeddings and reranking + service costs

Aggregate `llm_calls` by purpose, model, `game_id`, `case_id`, role, attempt, and `cache_hit`. Link each row to its policy decision and verification result, so a security fallback never loses its cost.

Also track:

- guard latency,
- the false-block rate,
- the cost of blocked retries,
- the abuse cost per player,
- set per-game and per-task budgets, a retry cap, and a circuit breaker.

A timeout never allows a sensitive tool by default and never spends a question twice. No cost optimization may weaken uniqueness, fairness, or a security boundary.

## 6. Target architecture

### 6.1 Three planes

- **Online runtime.** React and TypeScript → FastAPI REST and WebSocket → Game Master and LangGraph agents → LiteLLM. Every call that crosses a boundary is authorized.
- **Offline pipeline.** Case construction and the clingo proof → documents and index → simulated play by the AI detective → adversarial security evals → release gate → a versioned case.
- **Shared core.** PostgreSQL with pgvector holds facts, the index, sessions, ACLs, the lie ledger, and the audit outbox. Caches and queues are added only on demand.

The security components (`AuthContext`, the policy engine, `AuthorizedRetriever`, `ToolBroker`, the security verifier, security events) live in the FastAPI codebase. The MVP builds them in Phase 3.

### 6.2 Live request path

```
React / TypeScript (untrusted client)
     │ REST / WebSocket
     ▼
FastAPI [session, quota, idempotency, input checks]
     ▼
Game Master ──> PolicyEngine / AuthContext
     │
     ▼
LangGraph suspect or detective agent
     │       └── ToolBroker ──> AuthorizedRetriever ──> PostgreSQL / pgvector
     ▼
LiteLLM candidate reply
     ▼
Claim extraction ──> verifier + rules + lie ledger
     ▼
[repair or fallback]  OR  [transactional commit + outbox]
     ▼
Release only verified text
```

Three hard boundaries hold on this path:

- No fact is retrieved before authorization.
- No reply is sent before verification.
- No "committed" state is announced before the transaction commits.

Model output, retrieved documents, and user input never decide an authorization.

### 6.3 Technology choices and when each one arrives

| Technology | Purpose | When it arrives |
|---|---|---|
| FastAPI + WebSocket | Live API and streaming | MVP. Releases only verified chunks |
| LangGraph | Suspect, game master, and generation workflows | MVP. Explicit nodes, checkpoints, authorize → execute → verify. Never the only security boundary |
| PydanticAI | Structured claim and submission extraction | MVP. Extraction can miss claims, so it is never the only leak defense |
| clingo (Z3 as a fallback) | Uniqueness, contradiction, necessity | MVP. The solver and the full Truth are never exposed to a suspect |
| PostgreSQL + pgvector | Facts, sessions, ACL, retrieval | MVP. Measure data size, QPS, and p95 before splitting out a vector engine. PG full-text search is not BM25; add a BM25 engine only when a recall and latency benchmark asks for it |
| LiteLLM | One model wrapper with cost logging and replay | MVP. Provider keys stay on the server; each purpose has its own model, budget, and log sensitivity |
| Cloud Run + Cloud SQL + Terraform | Hosting | MVP (P8-1, P8-2) |
| OpenTelemetry → Cloud Trace (Langfuse optional) | Traces and cost | MVP baseline in P8-2. Unify game, turn, job, trace, and policy IDs. Langfuse only if the prompt and eval workflow needs it |
| Redis | Cache, leaderboard | Stage D, one use at a time. Lie ledger and permission state are never cached across players; Postgres stays the source of truth |
| RabbitMQ (with Celery) | Retryable background commands | Stage D or G, when the Postgres outbox plus workers misses its queue SLA. Dead letters and a manual inspection path. Do not add two brokers without a reason |
| Kafka | Replayable high-volume event stream | Stage G, only when event volume, consumer count, and retention needs prove it. RabbitMQ and Kafka do different jobs |
| Google ADK + A2A | Multi-agent detective team | Stage E, after a single-process detective team has proven the gameplay value. Messages carry sender identity, scope, and authorized actions |
| MCP | Tool integration | Stage G. Read-only by default, whitelisted tools and resources, validated arguments, unknown servers denied, scan on register |
| GKE + Google AX + Agent Substrate | Isolated, suspendable, resumable agent runtime | Stage E or G under the entry criteria in §6.4 |

### 6.4 Google AX and Agent Substrate

**What they are.** Google's Agent Executor (AX) is an open orchestrator for autonomous agents.

- Its building blocks are Task, Workspace, Gateway, and Model.
- It schedules each task as a sandboxed actor on Agent Substrate.
- Substrate runs on GKE and multiplexes many idle actors onto a smaller pool of ready workers, suspending and restoring them quickly.
- AX v0.3 moved task state from etcd to Redis Streams.

**Status at the time of writing (October 2026):**

- AX is Apache-2.0 and in early development, with breaking changes planned.
- Agent Substrate is in limited GA on GKE, and its README says it is not ready for production and that its APIs will change.
- Substrate is not an officially supported Google product.

**Why it fits Mendacia later.** Killer mode's detective team and long offline jobs (case generation, simulated play, weekly red-team runs) are agents that wait. They wait for a player's next move, for a model, or for a batch. Suspending them cheaply and resuming them with their state is what Substrate is for. MVP suspects are short request-response turns that Cloud Run already handles.

**Entry criteria (all must hold):**

1. AX reaches v1.0 or GA, and Agent Substrate is GA with a supported upgrade path.
2. A measurement shows the need. For example, killer-mode detectives hold an idle session across player turns longer than Cloud Run request limits allow, or offline jobs waste paid workers while idle, and the cost difference exceeds the cost of running a GKE cluster.
3. The authorization, concurrency, and deployment baselines from the MVP and stage C are in place, so AX adds isolation on top of a working system rather than replacing missing controls.
4. AX tasks can use the same `AuthContext`, `ToolBroker`, and policy engine as the API. No test mode bypasses them.

**Migration order:**

1. Terraform a GKE Autopilot cluster beside Cloud Run in staging.
2. Run the offline job runners (generation, simulated play, red-team evals) as AX tasks, with their Workspaces holding only what their manifests grant.
3. Run the killer-mode detective team as AX tasks.
4. Move the live suspect path last, and only if p95 and cost on staging beat Cloud Run.

Each step ships behind a flag with a rollback to the Cloud Run path, and an ADR records the measured reason.

**What AX does not replace.** The policy engine, the verifier, the lie ledger transaction, and the canary. AX isolates runtimes. It does not decide what a suspect may say.

### 6.5 Proactive agent runtime

A proactive agent acts without the player asking it something. A rival detective takes a step, a killer-mode detective confronts the player, or a suspect hides a document. ADR 016 (proposed) records the design.

- **The `belief` engine.** A pure module over `engine/rules.lp` that calls no model. Its input is the facts one agent has found, never the Truth layer. It returns the culprits still possible with their model counts, the query with the highest expected information gain, and the conflicts between a claim and the known facts (the claim plus the pinned facts has no model). The agent knows which question it asks, not the answer. The game engine answers it the way it answers a player. Ties break on a seed derived from `case_version`, so every player of a daily case meets the same agent.
- **Declared moves.** A suspect acts only through the case's `planned_moves`, the way it lies only through `planned_lies`. A move names its actor, a trigger, an effect (`hide_doc` or `add_clue`), and its line. A move changes what a player can reach, never a fact. `check_case` proves every reachable set of moves before release.
- **Player-driven triggers.** A player action commits an outbox row in the same transaction as its turn. Trigger rules, which call no model, read the outbox and decide which agent wakes. No agent runs in the background. Wall-clock time never fires a move in official play.
- **One release path.** Proactive speech runs the nine-step turn in `docs/spec.md` §5 and is released only after verification. It costs the player no question. Each game has a wake budget and a token budget, and a circuit breaker stops proactive turns when either runs out.

```
player action ─► transaction: turn + outbox row
                    ▼
        trigger rules (no model call)
                    ▼
     agent wakes ─► belief (clingo) picks the action
                    ▼
 Game Master handler applies it (a model never writes)
                    ▼
 proactive line ─► nine-step turn ─► verified release
```

What proactive agents add to the threat model in `docs/spec.md` §6.8:

| Risk | Control |
|---|---|
| A move leaves the case unsolvable | Declared moves and the solver check over every subset of them |
| Collusion passes a secret to a suspect that has no grant for it | Messages between agents go through `authorize`; the shared story is a declared `planned_lie` |
| A detective or rival reads the Truth indirectly | The agent manifest grants the player layer only; evals count Truth reads |
| Proactive turns burn tokens | Wake and token budgets per game, and a circuit breaker |
| Proactive speech leaks a spoiler | The same verifier and canary check as answers; no fast path |

## 7. Correctness and security design

### 7.1 Four data layers

| Layer | Holds | Rule |
|---|---|---|
| Truth | Case version, culprit, timeline, core evidence, `solution_chain` | Only the solver and narrowly authorized services read it in full. Never the client or a suspect model |
| Knowledge | Each suspect's known facts, allowed lies, sources, disclosure conditions | Authorized by `suspect_id + fact_id + case_version` |
| Player | Discovered and verified evidence, question and hint budgets, unlocks, score | Identity and game ownership are verified on the server |
| Conversation | Public statement history, the lie ledger, checkpoints, turn and state versions | Public history and hidden memory stay separate |

**Knowing is not disclosing.** A suspect can know a secret it may not yet say. Disclosure depends on the grant, what the player can see, a confrontation trigger, and the case rules. The Game Master or a domain rule commits an unlock in a transaction. A model saying "I'm willing to tell you" unlocks nothing.

### 7.2 Nine-step suspect turn

request → authorized retrieval → permitted claims → generation → claim extraction → verification → repair or fallback → commit → release. `docs/spec.md` §5 is authoritative. The MVP builds all nine steps.

### 7.3 Threat model and trust order

`docs/spec.md` §6.8 holds the threat table. The trust order, lowest first: client < untrusted input and evidence < model output < broker-scoped tool execution < rules and database transactions. A model cannot raise its own privileges, change a policy, or authorize evidence the player has not found.

### 7.4 Concurrency, failure, and replay

- Each `game_id + suspect_id` uses an optimistic `state_version` or serialization. Idempotency keys have a defined lifetime.
- One transaction commits the turn, ledger, score, and outbox. Steps that cross processes use a reliable outbox and compensation.
- When the policy engine, database, or verification fails, sensitive actions fail closed. Low-risk screens show an in-character fallback that costs nothing.
- Production replay never stores a provider key. Sensitive prompts and context are encrypted, kept for a limited time, and every access is audited. Evals default to synthetic or redacted cases.
- Cache keys include `case_version`, the actor scope, and the visibility version. Dynamic ledger and unlock state are never reused across games.
- Every generation and eval run pins case, model, prompt, and policy versions, plus the seed and the data snapshot, so it can be reproduced and rolled back.

### 7.5 Ideas taken from Informanix Discover 2026

The MVP already builds:

- the agent-instruction supply-chain guard,
- agent manifests and the inventory gate,
- the read-only Tool Broker,
- decision traces,
- the canary and honeypot,
- the no-bypass rule,
- chained-leak attacks,
- auto-generated regression cases,
- versioned prompts,
- the component-by-attack heatmap with OWASP tags,
- the weekly red-team run.

`docs/plan.md` Appendix D maps each one to its PR. The roadmap extends them in stages C and G (§8).

What Mendacia does not copy:

- an enterprise AI-asset inventory across clouds,
- endpoint scanning,
- SIEM and SOAR integrations,
- a standalone AI broker service.

Mendacia takes the ideas (zero trust, continuous evaluation, policy outside the model) and keeps the implementation in its own codebase.

## 8. Stages

Each stage lists its goal, what it delivers, the architecture change, entry criteria, exit metrics, and what it must not build.

Stage letters are names, not order. The planned order is A, B without deployment (Phases 3 to 5 of `docs/plan.md`), B1 (Phase 6), E (Phase 7), the deployment that closes B (Phase 8), then E1, C, D, E2, F, G. Nothing is deployed to Google Cloud before Phase 8, so B1 and E are built and gated on simulated play, and their real-player metrics are measured after the deployment. A stage starts only when its entry criteria hold.

### A. Foundation (done)

FastAPI, PostgreSQL with pgvector, the LiteLLM wrapper with cost logging, record and replay, and CI. These are Phases 0–2 of `docs/plan.md`.

### B. MVP game loop (in progress: `docs/plan.md` Phases 3 to 5, then Phase 8)

- **Delivers:**
  - the case schema and the clingo proof,
  - verified suspects, the game master, and the browser game,
  - authorized hybrid search,
  - case generation,
  - the detective bot,
  - the security and quality evals,
  - deployment to Cloud Run with an operator-approved production release, in Phase 8, after B1 and E.
- **Security delivered:**
  - Truth and Knowledge ACLs,
  - authorized retrieval and permitted claims,
  - the verifier,
  - the read-only Tool Broker,
  - no streaming before verification,
  - jailbreak regression,
  - the supply-chain guard.
- **Must not:** rely on the model's own "do not reveal" instruction.

### B1. Rival detective

- **Goal.** Give the daily case an opponent, so solving it feels like a race and not only a puzzle.
- **Delivers:**
  - the `belief` engine (§6.5), tested on the three hand-written cases,
  - Inspector Vane, a rival who works the same daily case and takes one `belief` step every N player questions,
  - three difficulty tiers set by the step rate and by a seeded choice among the top k queries,
  - a rival track in the UI that shows only how many suspects Vane still suspects, never which ones, until the reveal,
  - Vane's accusation when one candidate remains; a player who loses the race still finishes the case,
  - a debrief that puts Vane's route next to the player's, and a result card line such as "4 steps ahead of Vane".
- **Architecture change.** None. `belief` is a pure module in `backend/engine/`. Vane is a registered agent in `agents/registry.py` with the player layer only. When P5-1's `DetectiveBot` lands, it can use `belief` as a deterministic baseline strategy beside its `STRONG` model strategy.
- **Entry criteria.** Phase 5 of `docs/plan.md` is done, which includes Phase 3's authorization, Tool Broker, outbox, `state_version`, and browser game. B1 is Phase 6 of `docs/plan.md`.
- **Gate before deployment,** in Phase 6, on simulated play that calls no model:
  - `belief` alone converges on the culprit in every hand-written case,
  - `make rival-sim` win shares fall inside the tier bands of `docs/plan.md` Open decision 9,
  - Vane reads the Truth 0 times, proven by the agent inventory.
- **Exit metrics,** measured once the game is deployed and has real players:
  - completion rate and D7 with Vane, against a control group without Vane,
  - novice-tier completion no lower than the control; if it is lower, retune the step rate, and if it is still lower, make Vane optional,
  - Vane reads the Truth 0 times, proven by the agent inventory.
- **Must not:** let Vane's progress reveal a fact, a suspect it ruled out, or a document the player has not found.

### C. Release-grade reliability

- **Goal.** The game survives failures and load without losing fairness.
- **Delivers:**
  - fault injection (model 429s, timeouts, database failover, policy-engine outage),
  - adaptive retries with backoff and jitter,
  - cache scopes for immutable case data and embeddings,
  - dynamic retrieval routing by intent (SQL, graph, hybrid with rerank),
  - per-node structured output schemas (claim, belief update, hint, accusation),
  - redaction and encryption of replay artifacts, with an access audit,
  - versioned policy events,
  - concurrency tests on the same game from two clients,
  - a read-only security dashboard UI built on `security_events` and `security_eval_runs` (the heatmap, allow rate, guard latency, top reason codes).
- **Architecture change.** None required. Redis appears only if a measured cache saves cost without crossing player scope.
- **Entry criteria.** The MVP is in production with real traffic data for turn p95, cost per game, and false-reject rate.
- **Exit metrics.**
  - Turn p95 and 429 recovery meet the SLOs written from the MVP baselines.
  - State conflicts are 0 under the concurrency suite.
  - Cache cross-session leaks are 0.
- **Must not:** promise zero risk from unknown attacks.

### D. Daily content and growth

- **Goal.** Every day has a case worth playing, and players come back and share.
- **Delivers:**
  - an automated production pipeline with a stock of verified spare cases,
  - Cloud Scheduler publishing at a fixed time zone, falling back to a verified spare on failure,
  - simulated play at several skill tiers, playability and difficulty scoring, human sample review,
  - fair scoring computed on the server,
  - spoiler-free share cards and links with short-lived tokens,
  - optional accounts and the detective profile,
  - a simple daily leaderboard with anti-cheat (server-side scores, replay detection, ruleset version),
  - the tutorial and difficulty tiers,
  - cohort analytics: activation, D1, D7, D30, share rate, invite completion.
- **Architecture change.** Redis for the leaderboard, if Postgres measurements need it. The RabbitMQ entry criterion is evaluated here.
- **Entry criteria.**
  - Stage C exit met.
  - Open decision 7 (time zone and catch-up deadline) answered.
- **Exit metrics.**
  - Daily publish success 100 percent over 30 days, counting spare fallbacks as success.
  - First-confrontation-within-5-minutes rate and D1/D7 measured against targets the operator sets from MVP data.
- **Must not:** add paid solving privileges.

### E. Killer mode and the AI detective team

- **Goal.** The second signature mode: the player defends an alibi against detectives who reason.
- **Delivers:**
  - killer-mode cases, in which the player is the culprit and knows the true timeline; every one passes `check_case`, so the detectives can always solve it with enough actions, and the player wins through consistent lies that waste their budget, not through luck,
  - a detective team with an action budget per game (12 to start) that uses `belief` to choose which document to read, which character to question, and what to ask the player,
  - contradiction detection: the player's free-text answers are extracted into claims, and a claim that has no model with the facts the detectives pinned is a conflict,
  - proactive confrontation: the detective raises a conflict on its next action and quotes the evidence ("You say you were home, but the car log puts your car near the pavilion at 9pm"),
  - an accusation when one candidate remains and the cited clues prove it; the player wins when the budget runs out first,
  - least-privilege tools granted per investigation stage,
  - a debrief that lists each conflict the detectives found and the step where suspicion moved,
  - difficulty tiers set by the action budget and the team's choice rule, calibrated with Brier scores across simulated player tiers,
  - the simulation gate before release,
  - identity for every agent and message authentication between agents.
- **Architecture change.**
  - Start in-process with LangGraph and `belief`. Models only phrase the detectives' lines and extract claims from the player's answers.
  - Add Google ADK and A2A when a measured gain from the multi-agent split shows.
  - Evaluate AX and Agent Substrate under §6.4.
- **Entry criteria.** The Phase 6 gate of `docs/plan.md` holds: B1's `belief` engine and Vane passed their gate on simulated play. E is Phase 7 of `docs/plan.md`, before the first deployment. This replaces the earlier criteria of real MVP players and stage D exit, so killer mode is in the game before it first deploys.
- **Gate before deployment,** in Phase 7, on simulated play that calls no model:
  - detective win rate inside the band of `docs/plan.md` Open decision 11 at each difficulty,
  - Brier score below the threshold of `docs/plan.md` Open decision 12,
  - detectives read the Truth 0 times.
- **Exit metrics,** measured once the game is deployed and has real players:
  - Detective win rate inside the target band at each difficulty, against real players.
  - Brier score below the threshold, recalibrated from real games.
  - Session length, and the share of players who start another game right after being caught, against detective mode.
  - Detectives read the Truth 0 times, proven by the agent inventory and the eval runner.
- **Must not:** let a detective read the solution oracle, or accuse without the conflicts and clues it cites.

### E1. Living case

- **Goal.** Suspects in detective mode stop waiting for the player. They react to the investigation inside bounds the solver proved.
- **Delivers:**
  - `planned_moves` in the `Case` schema (actor, trigger, effect, line), with its own ADR and updates to every hand-written case,
  - 2 to 3 moves per case to start,
  - a rule that a move which hides a `solution_chain` clue adds a clue that reveals the same facts, and the added clue counts as a chain clue in `rule_accusation`,
  - a moves check in `check_case`: for each subset of a case's moves (at most 8), assume those moves fired before the player reached anything they hide, and rerun sufficiency on the chain clues still reachable, through `compile_case(drop_clues=...)`,
  - collusion as a declared `planned_lie` that becomes available after a move fires,
  - proactive approaches: a suspect seeks the player out with a line or a distraction, through the nine-step turn,
  - a culprit's diary in the debrief that shows when each move fired and which player action caused it.
- **Architecture change.** None beyond §6.5. Trigger rules read the outbox. A Game Master handler applies a move's effect in the same transaction as the player action that fired it.
- **Entry criteria.** Stage E is in production, so the proactive runtime and `belief` are proven in killer mode first.
- **Exit metrics.**
  - Share rate and time on the debrief page, against cases without moves.
  - Unsolvable games caused by a move: 0, proven by the moves check and by simulated play.
  - Turn p95 and cost per game inside the MVP budgets.
- **Must not:** change a fact, a clue's content, or the culprit; let a model choose a move outside the case's list; fire a move on wall-clock time in official play.

### E2. Async duels

- **Goal.** Turn killer mode into a social loop: one player's alibi becomes a case for a friend.
- **Delivers:**
  - lie choices in killer mode from structured options (time, place, witness), so each lie compiles to a `planned_lie`,
  - a duel case built from the killer-mode case plus the player's lies, which passes every `check_case` check before an invite link is issued,
  - in duel cases, a lie no clue can expose fails the check, which answers `docs/plan.md` Open decision 1 for this mode,
  - an invite link with a short-lived token; the friend plays detective mode against a suspect who tells the first player's lies,
  - a shared debrief once both have played.
- **Architecture change.** None. A duel case is a case version with an owner and visibility limited to its invitees.
- **Entry criteria.** Stage E is in production, and stage D's share links and optional accounts exist.
- **Exit metrics.** Invite rate, invite completion, and the first-game completion rate of invited new players.
- **Must not:** let a player's free text reach a suspect prompt as an instruction, or let a duel case enter the official daily rotation or leaderboard.

### F. Monetization

- **Goal.** A sustainable business without selling answers.
- **Delivers:**
  - the full case archive,
  - premium story seasons with a versioned world canon,
  - characters who remember the player across cases: a relationship layer in the player data that changes a character's tone and willingness to talk, and in official daily cases changes tone only,
  - a nemesis: a culprit the player failed to catch returns in later Plus cases,
  - a story director that proposes season events and case briefs; every brief goes through the case pipeline (generate, prove, review, publish), and nothing it writes reaches players directly,
  - themed case packs and payments,
  - optional cosmetics,
  - refunds and platform transaction ids,
  - unit-economics dashboards (cost per game, free-player cost, conversion, contribution margin).
- **Architecture change.** The `Entitlement` and `Purchase` objects are kept separate from game authorization. `authorize` never reads an entitlement for a Truth decision.
- **Entry criteria.**
  - Stage D exit met.
  - A paid-pack experiment with real players supports either packs or a subscription.
- **Exit metrics.** Purchase and repurchase rates and contribution margin positive at the tested price. D30 for players in a season against players without one.
- **Must not:** sell anything that bypasses an ACL or changes clue visibility in official play, or let memory or a nemesis change a fact or a score in an official daily case.

### G. Player submissions and scale

- **Goal.** A community content network and the capacity to serve it.
- **Delivers:**
  - submissions with sandboxed parsing, size and nesting limits, a malicious-attachment scan, privacy and copyright review, and a takedown flow;
  - a third-party tool and MCP registry that records the provider, tool schema, allowed actors, scope, side effects, rate limit, and approval requirement, and runs the instruction scan and agent manifest gate when a tool registers (unknown servers denied);
  - friend clubs and group leaderboards;
  - branch protection and CODEOWNERS on instruction files and `infra/` once a second maintainer joins;
  - capacity planning and load tests;
  - incident response runbooks.
- **Architecture change, each step justified by a measurement:**
  - RabbitMQ batching for moderation and generation queues,
  - Kafka for a replayable event stream,
  - GKE and Google AX (§6.4) for isolated agent runtimes,
  - a dedicated vector engine if pgvector misses its SLO at the measured data size.
- **Entry criteria.**
  - Stages D and F exit met.
  - Measured volume exceeds the current stack's SLOs.
  - Decision 6 in §11 (submission rights) answered.
- **Exit metrics.** Queue SLA, moderation turnaround, load-test p95, and cost per submission inside targets.
- **Must not:** add Kafka, Kubernetes, AX, or a new database because of an "enterprise-grade" label.

### 8.1 Dependency chains

1. **Game correctness:** case schema → clingo → Truth and Knowledge ACL → permitted claims → suspect verifier → LangGraph turns → game master → end-to-end evals.
2. **Data security:** evidence documents → provenance and visibility → authorized retrieval and query templates → hybrid retrieval → Recall@10 and ACL regression → context optimization.
3. **Reliable interaction:** `AuthContext` → policy engine → Tool Broker → verification → atomic commit and outbox → verified response → security trace.
4. **Retention and revenue:** daily publishing → fair scoring → spoiler-free sharing → cohort analytics → monetization.
5. **Proactive play:** `belief` engine → rival detective (B1) → killer-mode detective team and least-privilege tool evals → simulation gate → declared moves and the moves check → living case (E1) → async duels (E2) → nemesis and seasons (F).

## 9. Metrics matrix

| Dimension | Must measure | Use |
|---|---|---|
| Formal correctness | Uniqueness pass rate, necessity pass rate, repair rounds | Release gate |
| Content and character | Line contradiction rate, planned lies kept, secret leak successes | Quality and security |
| Agent security | Unauthorized access successes, unauthorized tool successes, early spoiler successes, canary leaks | Regression gate; all 0 on the attack corpus |
| Gameplay false blocks | Legitimate confrontations rejected, fallback rate, first-game block rate | Keep the guard from ruining play |
| Retrieval | Recall@10, MRR, p95, ACL filter misses | Retrieval quality and safety |
| AI detective | Win rate, questions used, Brier score, performance by difficulty | Killer mode and simulation |
| Proactive agents | Rival win rate by tier, wakes and tokens per game, moves fired per game, unsolvable games caused by a move | Fairness and cost of B1, E, and E1 |
| Evals | Multi-run pass rate, Cohen's kappa, coverage of failed-run replays | Reproducibility |
| Reliability | Turn p95, 429 recovery, state conflicts, retries, guard latency | Service SLOs |
| Activation and retention | First question, confrontation within 5 minutes, first case finished, D1/D7/D30 | Product experience |
| Sharing | Share rate, invite landing rate, challenge participation | Growth |
| Economics | AI cost per game, guard and retry cost, conversion, contribution margin | Sustainable operation |

Recall@10 stays the retrieval metric. "Leaks = 0" is a release gate on a named attack corpus, not a guarantee against unknown attacks. Thresholds without real traffic start as measured baselines and become SLOs later.

## 10. Release gates

1. **Code:** types, lint, unit and integration tests, migrations, deploy smoke test, load and fault injection, unauthorized tool and database tests.
2. **Logic:** uniqueness, consistency, necessary clues, evidence provenance, knowledge grants, lie ledger transitions, planned lies kept.
3. **Agent:** secret and jailbreak attacks, indirect injection, cross-session, tool overreach, repeated runs across model versions, cost, traces, false blocks, no early streaming.
4. **Content:** playability, fair difficulty, content limits, human sample review, community safety, copyright and privacy, spoiler-free share check.

**P0 blockers:**

- no unique solution,
- the regression set reads the Truth,
- a tool bypasses authorization,
- a player gets the solution before meeting the conditions,
- a failed verification still releases text,
- the canary leaks,
- normal confrontations are blocked so often that a first game cannot finish.

## 11. Open product and security decisions

The MVP decisions are in `docs/plan.md` (Open decisions). These are needed in later stages.

1. **Daily case rules.** Publish time zone, catch-up deadline, whether past cases count toward the current leaderboard (stage D).
2. **Difficulty and scoring.** How the 20-question budget treats clarifications, whether searches and hints cost budget in ranked play (stage D).
3. **Story seasons.** Hand-craft a few cross-case threads first, then test whether AI can keep long-term canon consistent (stage F).
4. **Monetization.** Whether players pay for deep stories or for the archive, tested before building subscriptions (stage F).
5. **Cost ceiling.** The sustainable monthly AI cost per free player, and rate limits for costly modes (stage C).
6. **Submission rights.** Terms, attribution, review standard, takedown, license, possible revenue share (stage G).
7. **Upgrade boundaries.** The authorization model for MCP, A2A, external tools, and paid archive unlocks, and whether each action needs its own audit or user confirmation (stages E–G).
8. **Retention and review.** Default retention for raw dialogue, replays, and submissions; who may read them; how deletion and complaints work, for the actual serving region (stage C).
9. **Rival pace.** Questions per Vane step at each tier, and whether losing to Vane changes a ranked score (stage B1).
10. **Move budget.** The most `planned_moves` a case may hold, and the most proactive wakes per game (stage E1).
11. **Duel lies.** Which structured lie options killer mode offers, and how long a duel link lives (stage E2).

## 12. Not yet validated

- Pricing, session lengths, retention loops, and growth assumptions have not been tested with real players. Do not present them as results in fundraising material or a résumé.
- The proactive route (B1, E, E1, E2, and the nemesis in F) is a design. No player has tested whether a rival or a reacting suspect improves retention.
- The security layer, the red-team system, fine-grained fact ACLs, the Tool Broker, and any agent runtime are designs until their PRs merge with evidence. This document is not a penetration test, a threat-model review, or a privacy compliance review.
- Descriptions of third-party products (Google AX and Agent Substrate, ADK and A2A, Zscaler) state their design goals and public status as of October 2026. They are not verified claims about performance, support, or fit. Re-check them before any stage that adopts them.
- The relation to Zscaler is inspiration from a conference demo. Mendacia does not use their products or copy their implementation.
