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
3. **Generator** — simple → Haiku via `generate_workflow` (one minimal plan);
   complex → `claude-opus-4-8` via `generate_candidate_workflows`, which
   returns 2–3 genuinely different candidates plus a `selected_index` /
   `selection_rationale` (the simplest goal-complete candidate,
   `build_candidates_schema`). `pick_selected_candidate` validates the
   payload; any failure in the candidate pass falls back to the
   single-workflow `generate_workflow` path (best-effort, never fails the
   run). System prompts are built per-request by
   `build_generator_system(selected_tools)` /
   `build_candidates_system(selected_tools)` and bake in the maintained
   capabilities KB (`_capabilities_block`), `SIMPLICITY_RULE`,
   `PROMPT_ENGINEERING_PRINCIPLES` (senior-prompt-engineer bar) +
   `CLAUDE_STEP_RULE`. Research findings, when present, are appended to the
   user message. Opus calls pass `thinking={"type": "adaptive"}` via
   `thinking_kwargs` (Opus 4.8 doesn't think unless asked; Sonnet 5 is
   adaptive by default).
4. **Reviewer** — `claude-sonnet-5` does a best-effort final quality pass
   (`review_workflow`): goal alignment is the first and most important check
   (the plan must fully deliver the user's stated goal), then simplicity
   (simplest sufficient plan), tool routing per the capabilities KB, Claude
   model/effort presence, prompt craftsmanship (senior-prompt-engineer bar),
   transitions, and coherence. It receives the candidate `selection_note`
   when one exists and returns the improved plan plus a `review_summary`
   that states the alignment verdict; research findings are passed through
   for consistency checking. If the review call fails (`anthropic.APIError`
   or a malformed response), the run does not fail — the unreviewed
   generator draft is returned as-is (no `review_summary`) and a `⚠️` note
   is added to `st.session_state["workflow_notes"]`. Research/availability/
   attachment status notes are also stored there and rendered as captions
   above the plan.

## Tool-capabilities knowledge base

`tool_capabilities.md` (repo root) is the maintained capabilities write-up
(strengths/output-formats table + proven tool sequences). Loaded once per
script run by `load_tool_capabilities()` into `TOOL_CAPABILITIES` and
injected into the generator/candidates/reviewer system prompts via
`_capabilities_block()` inside `<tool_capabilities>` tags. Missing/unreadable
file → `None` → prompts fall back to the built-in `TOOL_CATALOG`
descriptions (never crash). It is prompt context, not parsed config —
maintainers edit it directly in the GitHub UI (pencil icon → commit) and the
app picks it up on next restart. Finer-grained modes it mentions (Claude
Code, Perplexity Deep Research, etc.) are expressed through a step's
`model` field, never as a routed `app` value.

## Context attachments

`st.file_uploader` (multi-file, `ATTACHMENT_TYPES` = md/docx/pptx) feeds
`build_attachment_context` → `extract_attachment_text` (python-docx /
python-pptx; best-effort, unreadable files warn and are skipped). Caps:
`MAX_ATTACHMENT_CHARS` per file, `MAX_CONTEXT_CHARS` total, truncation notes
in `workflow_notes`. `compose_task_context` appends the extracted text to
the task for planner calls (router gets only `ROUTER_CONTEXT_CHARS`).
Attachment filenames live in `st.session_state["workflow_attachments"]` and
are shown in exports ("Context files"); the exports/render functions take an
optional `attachments` list (default `None`, backward compatible).

Workflow payload: `strategy_summary`, `recommended_environments`,
`effort_level` (Low/Medium/High), `steps[]` (each: `title`, `app` — one of the
selected tools, `model` — recommended mode/model or `""`, `effort` —
Low/Medium/High for Claude steps (the Claude Code `/effort` setting or
Extended Thinking in the Claude app; empty string for other tools),
`transition` — empty when the app doesn't change, `prompt`), plus
`review_summary` (reviewer only). Steps routed to "Claude" must always carry
both a model and an effort recommendation (`CLAUDE_STEP_RULE`, enforced by
generator and reviewer); `render_workflow` and the exports show model/effort
only when non-empty (`step_meta_text`). `TRANSITION_RULE` (in the generator
and reviewer prompts) requires transitions to be concrete, app-specific
handoff guidance (what to carry across and how), and — for Claude Code steps
(app "Claude", model "Claude Code") — the one-time project setup (folder
structure, CLAUDE.md, Skills/reference files), allowed even on a first step.
The "no setup guides" rule is narrowed to account-signup/installation/
usage-limit caveats and Perplexity MCP guides; Claude Code *project* setup is
explicitly wanted.

## Exports & session

- Downloads: `build_markdown` / `build_docx` (python-docx) / `build_pdf`
  (reportlab, pure-Python — no system deps). All escape user text and wrap long
  lines; verified against Unicode, smart quotes, and `<`/`&`. Download buttons
  are guarded with `ModuleNotFoundError` fallbacks.
- "Start new session" (`start_new_session`) clears `workflow` / `workflow_task` /
  `workflow_notes` / `workflow_attachments` / `workflow_context_sig` /
  `task_input` but keeps auth and the API key; "Sign out" clears everything.

## Result invalidation

A generated workflow is cached in `st.session_state["workflow"]`, keyed by
the task that produced it in `st.session_state["workflow_task"]` plus the
attachment signature (`name:size` list) in
`st.session_state["workflow_context_sig"]`. On every rerun, if the
(stripped) task input or the attachment set no longer matches, the stale
workflow is deleted from session state (along with `workflow_notes` /
`workflow_attachments` / `workflow_context_sig`) so it is never shown next
to different inputs — the user re-runs the button to regenerate. The task
comparison is whitespace-tolerant (`.strip()`).

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

- Current model IDs only: `claude-haiku-4-5`, `claude-sonnet-5`,
  `claude-opus-4-8` (the PRD's "Claude 3.5" names are retired). Model
  constants are at the top of `app.py`. Every planner call clamps
  `max_tokens` via `plan_budget(model)` / `MODEL_MAX_OUTPUT_TOKENS`
  (Haiku 64K, Sonnet/Opus 128K — exceeding the cap is a 400), and gets its
  thinking config from `thinking_kwargs(model)` (Opus 4.8 needs explicit
  `{"type": "adaptive"}`).
- Catch Anthropic SDK typed exceptions most-specific-first
  (`AuthenticationError` → `RateLimitError` → `APIStatusError` →
  `APIConnectionError`); never string-match error messages.
- The generators (Haiku/Opus 4.8) and reviewer (`claude-sonnet-5`) run with
  thinking tokens sharing `max_tokens` with the JSON plan (Sonnet is
  adaptive by default; Opus gets adaptive via `thinking_kwargs`). All these
  calls **stream** (`client.messages.stream(...).get_final_message()`) with
  `plan_budget(model)` headroom — a non-streaming 8K budget truncated the
  plan into invalid JSON, surfacing as "The planner returned an unexpected
  response." Keep these calls streamed; only the router (Haiku, tiny output)
  uses non-streaming `create`.
