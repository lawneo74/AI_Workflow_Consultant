# AI Workflow Architect

A Streamlit app that turns a raw task description into a chained, copy-paste
workflow routed to the best of the AI tools you actually have. Pick your tools
from **Perplexity AI**, **Claude**, **ChatGPT**, **NotebookLM**, and **Gemini
(incl. Nano Banana)** (at least one), and every step is routed only to a tool
you selected.

## How it works

Three-tier Anthropic backend, with an optional live-research step:

1. **Router (Claude Haiku)** — classifies the task as *simple* or *complex*,
   and flags whether live web research would improve the plan.
2. **Research (Perplexity, optional)** — when the router asks for it and a
   Perplexity API key is configured, the app runs one `sonar-pro` search and
   grounds the plan in the findings (current tools, versions, facts).
3. **Generator (Haiku or Opus 4.8)** — simple tasks get the *simplest*
   workflow that fully delivers the goal, generated on Haiku. Complex tasks
   are handed to **Claude Opus 4.8**, which drafts **2–3 genuinely different
   candidate workflows and selects the simplest one that gets the job done**
   (goal completeness first; then fewest steps and tool switches). Prompts
   are written to a senior-prompt-engineer standard. Each step is badged
   with the app to paste it into; steps routed to **Claude** also carry a
   recommended **model and effort level** (the `/effort` setting in Claude
   Code, Extended Thinking in the Claude app), and transitions between apps
   include a note on how to carry the context across.
4. **Reviewer (Claude Sonnet)** — a final quality pass that verifies the plan
   is **aligned with your goal** and is the simplest sufficient plan, then
   refines the prompts and tool routing before the plan is shown, with a
   short review summary stating the verdict.

Planning is grounded in a maintained **tool-capabilities knowledge base**
(`tool_capabilities.md` — strengths, output formats, and proven tool
sequences). To update it, edit the file directly on GitHub (open it → click
the ✏️ pencil icon → commit); the app picks up the change on the next
restart, no code changes needed.

You can also **attach Markdown, Word (.docx), or PowerPoint (.pptx) files**
as context — their content is extracted and used to ground the plan, and the
filenames are recorded in the exports.

Finished plans can be downloaded as **Markdown**, **Word (.docx)**, or **PDF**.
"Start new session" clears the current plan so you can begin fresh.

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
