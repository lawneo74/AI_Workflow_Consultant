# AI Workflow Architect

Streamlit app (`app.py`, single file) that turns a raw task description into a
chained, copy-paste workflow routed to the best execution environment(s):
Claude Desktop, Claude Code, or Perplexity Native. Built from the PRD
"AI Workflow Architect".

## Architecture

Two-tier Anthropic backend (see `app.py`):

1. **Router** — `claude-haiku-4-5` classifies the task as `simple` or
   `complex` (`route_task`).
2. **Generator** — simple tasks stay on Haiku; complex/multi-step/coding
   tasks go to `claude-sonnet-5` (`generate_workflow`).

Both calls use structured outputs (`output_config.format` with a
`json_schema`) so responses are guaranteed-valid JSON — parse the first
`text` block with `json.loads`, never regex. Schemas live in
`ROUTER_SCHEMA` / `GENERATOR_SCHEMA`; every object needs
`additionalProperties: false` and a full `required` list.

The generator payload: `strategy_summary`, `recommended_environments`,
`effort_level` (Low/Medium/High), and `steps[]` where each step has `title`,
`app` (one of the three environments), `model`, `transition` (empty string
when the app doesn't change), and `prompt` (the copy-paste text).

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
