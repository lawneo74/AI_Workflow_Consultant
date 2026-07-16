# AI Workflow Architect

A Streamlit app that turns a raw task description into a chained, copy-paste
workflow routed to the best execution environment(s): **Claude Desktop**,
**Claude Code**, or **Perplexity Native**.

## How it works

Two-tier Anthropic backend:

1. **Router (Claude Haiku)** — classifies the task as *simple* or *complex*,
   and flags whether live web research would improve the plan.
2. **Research (Perplexity, optional)** — when the router asks for it and a
   Perplexity API key is configured, the app runs one `sonar-pro` search and
   grounds the plan in the findings (current tools, versions, facts).
3. **Generator (Haiku or Sonnet)** — simple tasks stay on Haiku; complex,
   multi-step, or coding tasks are handed to Sonnet. The generator returns a
   structured workflow: recommended environments, an effort estimate, and a
   sequence of steps. Each step is badged with the app to paste it into;
   Claude steps also carry a recommended **model and effort level** (the
   `/effort` setting in Claude Code, Extended Thinking in Claude Desktop),
   and transitions between apps include a note on how to carry the context
   across.
4. **Alignment review** — a final pass checks the workflow against your goal
   and automatically revises it once if it falls short. The verdict is shown
   above the result.

The app never executes the generated prompts — it is strictly a copy-paste
generator. (The optional Perplexity call gathers planning context *before*
generation; it never runs the generated prompts.)

## Run

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # or enter it in the app
export APP_PASSCODES="code-one,code-two"   # the two login passcodes
export PERPLEXITY_API_KEY=pplx-...         # optional: enables live research
streamlit run app.py
```

All values can also be set in `.streamlit/secrets.toml` instead of the
environment:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
APP_PASSCODES = "code-one,code-two"
PERPLEXITY_API_KEY = "pplx-..."
```

The app shows a login page first; either of the two passcodes signs you in.
