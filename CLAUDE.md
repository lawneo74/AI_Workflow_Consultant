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

Three-tier Anthropic backend (see `app.py`), all using structured outputs
(`output_config.format` with a `json_schema`) — parse the first `text` block
with `json.loads`, never regex. Every schema object needs
`additionalProperties: false` and a full `required` list.

1. **Router** — `claude-haiku-4-5` classifies the task `simple`/`complex`
   (`route_task`, `ROUTER_SCHEMA`).
2. **Generator** — simple → Haiku, complex → `claude-sonnet-5`
   (`generate_workflow`). System prompt is built per-request by
   `build_generator_system(selected_tools)` and bakes in
   `PROMPT_ENGINEERING_PRINCIPLES`.
3. **Reviewer** — `claude-sonnet-5` does a mandatory final quality pass
   (`review_workflow`) that refines prompts/routing and adds `review_summary`.

Workflow payload: `strategy_summary`, `recommended_environments`,
`effort_level` (Low/Medium/High), `steps[]` (each: `title`, `app` — one of the
selected tools, `model` — recommended mode/model or `""`, `transition` — empty
when the app doesn't change, `prompt`), plus `review_summary` (reviewer only).

## Exports & session

- Downloads: `build_markdown` / `build_docx` (python-docx) / `build_pdf`
  (reportlab, pure-Python — no system deps). All escape user text and wrap long
  lines; verified against Unicode, smart quotes, and `<`/`&`. Download buttons
  are guarded with `ModuleNotFoundError` fallbacks.
- "Start new session" (`start_new_session`) clears `workflow` / `workflow_task` /
  `task_input` but keeps auth and the API key; "Sign out" clears everything.

## Result invalidation

A generated workflow is cached in `st.session_state["workflow"]`, keyed by
the task that produced it in `st.session_state["workflow_task"]`. On every
rerun, if the (stripped) task input no longer matches `workflow_task`, the
stale workflow is deleted from session state so it is never shown next to a
different task — the user re-runs the button to regenerate. The comparison
is whitespace-tolerant (`.strip()`).

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
