# Runtime State, Vertical Coherence, and Agent Memory in Rush

## 1. The Core Problem: Why Chat Memory & Static AST Memory Fail

Traditional coding agent "memory" systems fail because they only store **static text transcripts** or **static code summaries**. 

When a coding agent works on a software repository, the real point of failure is that the agent lacks memory of the **living application state**:
1. **The Agent has No Runtime Memory**: It does not remember what happened when the code actually ran (runtime errors, database states, API responses, console logs).
2. **The Agent has No Stack-Coherence Memory**: When it modifies a database schema in Turn 2, it forgets that it created an unfulfilled obligation to update the backend serializer in Turn 5, the frontend TypeScript interface in Turn 8, and the UI component in Turn 10.
3. **The Agent has No Environment Memory**: It does not remember which database migrations are applied locally, which environment variables are loaded in the running process, or which ports are listening.

---

## 2. Transforming Runtime & Stack Reality into Agent Memory

### A. Living Runtime & Execution Memory (`src/rush/memory/runtime_state.py`)
Instead of storing chat logs, Rush stores the **dynamic execution state** of the application:
* **Test & Server Execution Trace Memory**: Records the exact runtime arguments, database queries, and return values observed when the app runs.
* **Dirty State Memory**: Tracks unapplied database migrations, missing environment variables in `.env`, and out-of-sync package installations.
* **Failure & Regression Memory**: Stores the exact runtime stack trace and environment state when a feature broke, so subsequent turns know the exact conditions that triggered the crash.

### B. Vertical Stack Coherence & Obligation Ledger (`src/rush/memory/vertical_obligations.py`)
When an agent touches one layer of the application, Rush creates an active **Obligation Memory Ledger**:
* *Trigger*: Agent modifies `models/user.py` (adds `avatar_url`).
* *Active Memory Injected into Agent Context*:
  * `[PENDING]` Database migration created & applied?
  * `[PENDING]` API serializer updated (`schemas/user.py`)?
  * `[PENDING]` Frontend TypeScript type updated (`types/user.ts`)?
  * `[PENDING]` UI component wired (`components/UserAvatar.tsx`)?
* *Enforcement*: The agent cannot mark the task complete or close the session until all vertical obligations in memory are checked off with proof.

### C. State-Aware Checkpoint & Time-Machine Memory (`src/rush/memory/state_snapshots.py`)
* Captures a unified snapshot of:
  1. Git working directory diffs.
  2. Local SQLite/Postgres database state (table dumps/seeds).
  3. Environment variables (`.env`).
* If an agent breaks the app, Rush’s rollback restores **both the code and the live database state**, preventing the agent from trying to fix code against a corrupted local database.

---

## 3. MCP Layer: Coding Agent Skills, Commands & Live Hooks

The MCP layer provides the active interface through which the coding agent reads runtime memory, executes full-stack actions, and respects live guardrails.

### A. FastMCP Pre-Execution & Post-Execution Hooks (`src/rush/mcp/hooks.py`)
* **Pre-Execution Hook (Environment State Check)**: Before an agent runs a tool or modifies a file, the hook checks if the local dev server is running and if the database is in sync. If out-of-sync, it intercepts the call and prompts the agent to apply migrations first.
* **Post-Execution Hook (Obligation & Runtime Verification)**: After an agent modifies a file, the hook inspects the change, updates the Vertical Obligation Ledger in memory, and returns the next pending stack obligation in the tool result.

### B. Coding Agent Skills (`src/rush/tools/agent_skills/`)
1. `rush_agent_verify_runtime`: Triggers a background end-to-end execution of the modified endpoint against the local dev environment, capturing live HTTP status codes, database queries, and console logs directly into the agent's memory.
2. `rush_agent_check_obligations`: Returns the active list of unfinished vertical stack layers (DB -> Backend -> Types -> Frontend -> Env) for the current task.
3. `rush_agent_rollback_state`: Rolls back both the code and the local database seed to a clean snapshot when an approach fails.
4. `rush_agent_inspect_env`: Reads the active environment state (running processes, applied migrations, listening ports) so the agent never makes ungrounded assumptions about the local system.

---

## 4. How This Transforms the Developer & Vibecoder Experience

1. **Zero Babysitting**: The agent verifies its own code against the live running app, catching runtime crashes before the user ever looks at the screen.
2. **No Partial Features**: The agent never leaves a task half-done with a broken UI or missing migration because the Obligation Memory forces full-stack completion.
3. **Safe, Effortless Rollbacks**: Failed agent experiments don't leave the local database in a broken state; state-aware snapshots make experimentation 100% reversible.
