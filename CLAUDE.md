# AI Workflow Architect

Streamlit app (`app.py`, single file) that turns a raw task description into a
chained, copy-paste workflow routed to the best of the AI tools the user
actually has. Built from the PRD "AI Workflow Architect".

The user selects, via a multiselect (minimum one), which tools they have from
`TOOL_CATALOG`: Perplexity AI, Claude, ChatGPT, NotebookLM, Gemini (incl. Nano
Banana). Workflows are routed **only** to the selected tools — the JSON-schema
`app`/`recommended_environments` enums are built dynamically from that
selection (`build_generator_schema` / `build_review_schema`).

## Architecture

Pipeline in `app.py`: router → optional research → generator → final review.
All Anthropic calls use structured outputs (`output_config.format` with a
`json_schema`) — parse the first `text` block with `json.loads`, never regex.
Every schema object needs `additionalProperties: false` and a full `required`
list.

1. **Router** — `claude-haiku-4-5` classifies the task `simple`/`complex`
   and sets `needs_research` + `research_query` when live facts would improve
   the plan (`route_task`, `ROUTER_SCHEMA`).
2. **Research (optional)** — `run_research` calls the Perplexity chat
   completions API (`sonar-pro`, plain `requests`, 45s timeout) with the
   router's query. Best-effort: any failure returns `None` and planning
   continues without it. Requires `PERPLEXITY_API_KEY` (env, secrets, or the
   in-app expander shown only when unconfigured). This is pre-generation
   context gathering — it does NOT execute generated prompts, so it doesn't
   violate the no-execution constraint below.
3. **Generator** — simple → Haiku, complex → `claude-sonnet-5`
   (`generate_workflow`). System prompt is built per-request by
   `build_generator_system(selected_tools)` and bakes in
   `PROMPT_ENGINEERING_PRINCIPLES` + `CLAUDE_STEP_RULE`. Research findings,
   when present, are appended to the user message.
4. **Reviewer** — `claude-sonnet-5` does a best-effort final quality pass
   (`review_workflow`): goal alignment is the first and most important check
   (the plan must fully deliver the user's stated goal), then tool routing,
   Claude model/effort presence, prompt quality, transitions, and coherence.
   It returns the improved plan plus a `review_summary` that states the
   alignment verdict; research findings are passed through for consistency
   checking. If the review call fails (`anthropic.APIError` or a malformed
   response), the run does not fail — the unreviewed generator draft is
   returned as-is (no `review_summary`) and a `⚠️` note is added to
   `st.session_state["workflow_notes"]`. Research/availability status notes
   are also stored there and rendered as captions above the plan.

Workflow payload: `strategy_summary`, `recommended_environments`,
`effort_level` (Low/Medium/High), `steps[]` (each: `title`, `app` — one of the
selected tools, `model` — recommended mode/model or `""`, `effort` —
Low/Medium/High for Claude steps (the Claude Code `/effort` setting or
Extended Thinking in the Claude app; empty string for other tools),
`transition` — empty when the app doesn't change, `prompt`), plus
`review_summary` (reviewer only). Steps routed to "Claude" must always carry
both a model and an effort recommendation (`CLAUDE_STEP_RULE`, enforced by
generator and reviewer); `render_workflow` and the exports show model/effort
only when non-empty (`step_meta_text`).

## Exports & session

- Downloads: `build_markdown` / `build_docx` (python-docx) / `build_pdf`
  (reportlab, pure-Python — no system deps). All escape user text and wrap long
  lines; verified against Unicode, smart quotes, and `<`/`&`. Download buttons
  are guarded with `ModuleNotFoundError` fallbacks.
- "Start new session" (`start_new_session`) clears `workflow` / `workflow_task` /
  `workflow_notes` / `task_input` but keeps auth and the API key; "Sign out"
  clears everything.

## Result invalidation

A generated workflow is cached in `st.session_state["workflow"]`, keyed by
the task that produced it in `st.session_state["workflow_task"]`. On every
rerun, if the (stripped) task input no longer matches `workflow_task`, the
stale workflow is deleted from session state (along with `workflow_notes`)
so it is never shown next to a different task — the user re-runs the button
to regenerate. The comparison is whitespace-tolerant (`.strip()`).

## Hard PRD constraints — do not violate

- The app must NOT execute generated prompts via APIs. Strictly a
  copy-paste generator.
- No rate-limit warnings for heavy models anywhere in the UI or output.
- No Perplexity MCP server setup guides.
- No industry-vertical prioritization by default.
- Keep the UI clean and minimal.

## Auth

Login page with exactly **two passcodes**, read from `APP_PASSCODES`
(comma-separated pair) via env var or `.streamlit/secrets.toml`. Comparison
uses `hmac.compare_digest`; auth state lives in
`st.session_state["authenticated"]`. Never hardcode passcodes in source.

## Configuration

| Setting | Source | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | env, secrets, or in-app field | Backend model calls |
| `APP_PASSCODES` | env or secrets, `"code1,code2"` | The two login passcodes |
| `PERPLEXITY_API_KEY` | env, secrets, or in-app expander | Optional live research |

## Commands

```bash
pip install -r requirements.txt
streamlit run app.py                 # run locally
python3 -m py_compile app.py         # quick syntax check
```

## Testing

No test suite yet. Verify UI changes with `streamlit.testing.v1.AppTest`.
Note: AppTest executes the script in its own namespace, so
`unittest.mock.patch("app.…")` does NOT intercept calls inside the app run —
instead, point AppTest at a small wrapper script that imports `app` and
calls the target function (e.g. `render_workflow`) with fixture data.

## Conventions

- Current model IDs only: `claude-haiku-4-5`, `claude-sonnet-5` (the PRD's
  "Claude 3.5" names are retired). Model constants are at the top of
  `app.py`.
- Catch Anthropic SDK typed exceptions most-specific-first
  (`AuthenticationError` → `RateLimitError` → `APIStatusError` →
  `APIConnectionError`); never string-match error messages.
- The generator and reviewer (`claude-sonnet-5`) run adaptive thinking by
  default, so thinking tokens share `max_tokens` with the JSON plan. Both
  calls **stream** (`client.messages.stream(...).get_final_message()`) with
  `PLAN_MAX_TOKENS` headroom — a non-streaming 8K budget truncated the plan
  into invalid JSON, surfacing as "The planner returned an unexpected
  response." Keep these calls streamed; only the router (Haiku, tiny output)
  uses non-streaming `create`.
