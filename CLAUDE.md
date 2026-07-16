# AI Workflow Architect

Streamlit app (`app.py`, single file) that turns a raw task description into a
chained, copy-paste workflow routed to the best execution environment(s):
Claude Desktop, Claude Code, or Perplexity Native. Built from the PRD
"AI Workflow Architect".

## Architecture

Pipeline in `app.py`: router → optional research → generator → alignment
review (with one automatic revision).

1. **Router** — `claude-haiku-4-5` classifies the task as `simple` or
   `complex`, and sets `needs_research` + `research_query` when live facts
   would improve the plan (`route_task`).
2. **Research (optional)** — `run_research` calls the Perplexity chat
   completions API (`sonar-pro`, plain `requests`, 45s timeout) with the
   router's query. Best-effort: any failure returns `None` and planning
   continues without it. Requires `PERPLEXITY_API_KEY` (env, secrets, or the
   in-app expander shown only when unconfigured). This is pre-generation
   context gathering — it does NOT execute generated prompts, so it doesn't
   violate the no-execution constraint below.
3. **Generator** — simple tasks stay on Haiku; complex/multi-step/coding
   tasks go to `claude-sonnet-5` (`generate_workflow`). Research findings,
   when present, are appended to the user message. The same function also
   handles revisions (pass `prior_workflow` + `feedback`).
4. **Alignment review** — `review_workflow` (same model as the generator)
   returns `{aligned, feedback}`. If misaligned, `main` regenerates once
   with the feedback, re-reviews, and surfaces the final verdict as a
   caption note above the rendered workflow (stored in
   `st.session_state["workflow_notes"]`).

All Anthropic calls use structured outputs (`output_config.format` with a
`json_schema`) so responses are guaranteed-valid JSON — parse the first
`text` block with `json.loads`, never regex. Schemas live in
`ROUTER_SCHEMA` / `GENERATOR_SCHEMA` / `REVIEW_SCHEMA`; every object needs
`additionalProperties: false` and a full `required` list.

The generator payload: `strategy_summary`, `recommended_environments`,
`effort_level` (Low/Medium/High), and `steps[]` where each step has `title`,
`app` (one of the three environments), `model`, `effort` (Low/Medium/High
for Claude steps — the Claude Code `/effort` setting or Extended Thinking in
Claude Desktop; empty string for Perplexity steps), `transition` (empty
string when the app doesn't change), and `prompt` (the copy-paste text).
Claude steps must always carry both a model and an effort recommendation;
`render_workflow` shows effort only when non-empty.

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
