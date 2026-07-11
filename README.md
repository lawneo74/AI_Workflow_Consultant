# AI Workflow Architect

A Streamlit app that turns a raw task description into a chained, copy-paste
workflow routed to the best execution environment(s): **Claude Desktop**,
**Claude Code**, or **Perplexity Native**.

## How it works

Two-tier Anthropic backend:

1. **Router (Claude Haiku)** — classifies the task as *simple* or *complex*.
2. **Generator (Haiku or Sonnet)** — simple tasks stay on Haiku; complex,
   multi-step, or coding tasks are handed to Sonnet. The generator returns a
   structured workflow: recommended environments, an effort estimate, and a
   sequence of steps. Each step is badged with the app to paste it into, and
   transitions between apps include a note on how to carry the context across.

The app never executes the generated prompts — it is strictly a copy-paste
generator.

## Run

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # or enter it in the app
export APP_PASSCODES="code-one,code-two"   # the two login passcodes
streamlit run app.py
```

Both values can also be set in `.streamlit/secrets.toml` instead of the
environment:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
APP_PASSCODES = "code-one,code-two"
```

The app shows a login page first; either of the two passcodes signs you in.
