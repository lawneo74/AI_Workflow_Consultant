"""AI Workflow Architect — intelligent Prompt & Workflow Generator.

A Streamlit app that routes a raw user task through a two-tier Anthropic
backend: Haiku categorizes task complexity, then Haiku (simple tasks) or
Sonnet (complex tasks) generates a chained, copy-paste workflow. Each step
is labeled with the app to paste it into (Claude Desktop, Claude Code, or
Perplexity Native), with transition notes when the workflow spans apps.

When the router flags that live information would improve the plan (and a
Perplexity API key is configured), the app runs one Perplexity search and
feeds the findings to the generator as research context. A final alignment
review then checks the workflow against the user's goal and triggers one
automatic revision if it falls short.

The app never executes the generated prompts — it is strictly a
copy-paste generator.
"""

import hmac
import json
import os

import anthropic
import requests
import streamlit as st

ROUTER_MODEL = "claude-haiku-4-5"
SIMPLE_GENERATOR_MODEL = "claude-haiku-4-5"
COMPLEX_GENERATOR_MODEL = "claude-sonnet-5"
PERPLEXITY_RESEARCH_MODEL = "sonar-pro"
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

ENVIRONMENTS = ["Claude Desktop", "Claude Code", "Perplexity Native"]

APP_BADGE_COLORS = {
    "Claude Desktop": "#C15F3C",
    "Claude Code": "#2D6A4F",
    "Perplexity Native": "#1F6F8B",
}

ROUTER_SYSTEM = """\
You are a task-complexity router for an AI workflow planner. Classify the
user's task so the right generator model can be selected.

Classify as "complex" when the task involves any of: multi-step workflows,
software engineering or coding, research combined with synthesis, work that
spans more than one tool, or open-ended deliverables (reports, whitepapers,
applications). Classify as "simple" for single-shot tasks: a lookup, a quick
rewrite, a summary of provided text, a single well-scoped prompt.

Also decide whether a live web search would materially improve the workflow
plan — set "needs_research" true when the task depends on current facts,
recent tools/versions, market conditions, or anything likely to have changed
since your training data. When true, write a focused "research_query" (one
search query capturing what the planner needs to know). When false, use an
empty string for "research_query".
"""

ROUTER_SCHEMA = {
    "type": "object",
    "properties": {
        "complexity": {"type": "string", "enum": ["simple", "complex"]},
        "reasoning": {
            "type": "string",
            "description": "One-sentence justification for the classification.",
        },
        "needs_research": {
            "type": "boolean",
            "description": "True when live web research would improve the plan.",
        },
        "research_query": {
            "type": "string",
            "description": "Search query for the research step; empty if not needed.",
        },
    },
    "required": ["complexity", "reasoning", "needs_research", "research_query"],
    "additionalProperties": False,
}

GENERATOR_SYSTEM = """\
You are an AI workflow architect for users who have Claude Pro and
Perplexity Pro subscriptions. Given a task, design the optimal chained
workflow across these execution environments:

- "Perplexity Native" — best for live web research, current events, market
  and competitive scans, sourcing citations. Models: sonar-pro,
  sonar-reasoning-pro.
- "Claude Desktop" — best for writing, analysis, synthesis, document
  drafting, brainstorming, and working with attached files. Models:
  claude-sonnet-5, claude-fable-5 (hardest reasoning/writing).
- "Claude Code" — best for software engineering: building apps, editing
  repositories, running tests, terminal work, multi-file refactors.
  Models: claude-sonnet-5, claude-opus-4-8.

Rules:
- Choose the fewest environments that genuinely fit the task; use a hybrid
  chain only when different phases clearly belong in different apps.
- Each step's "prompt" must be a complete, self-contained, copy-paste-ready
  prompt written for the target app — specific, detailed, and referencing
  any artifacts produced by earlier steps.
- For every step that runs in Claude Desktop or Claude Code you MUST
  recommend both the Claude model AND the "effort" to use ("Low", "Medium",
  or "High"). Effort is the reasoning depth the user should set in the app:
  in Claude Code it maps to the /effort setting; in Claude Desktop, "High"
  means enable Extended Thinking. Reserve "High" for the hardest reasoning,
  design, or debugging steps. For Perplexity Native steps use an empty
  string for "effort".
- If research findings are provided with the task, treat them as current,
  authoritative context: ground the strategy and step prompts in them
  (correct tool names, versions, and facts) instead of stale knowledge.
- When a step runs in a different app than the previous step, fill
  "transition" with a brief practical note on how to carry the output
  across (e.g. "Export the Perplexity thread as a PDF or paste the answer
  into a research.md file, then attach it in Claude Desktop."). Use an
  empty string for the first step or when the app does not change.
- "effort_level" reflects the user's expected hands-on effort: "Low",
  "Medium", or "High".
- Do not include tool setup instructions or usage-limit caveats anywhere.
"""

GENERATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "strategy_summary": {
            "type": "string",
            "description": "Two or three sentences explaining the overall plan.",
        },
        "recommended_environments": {
            "type": "array",
            "items": {"type": "string", "enum": ENVIRONMENTS},
        },
        "effort_level": {"type": "string", "enum": ["Low", "Medium", "High"]},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "app": {"type": "string", "enum": ENVIRONMENTS},
                    "model": {
                        "type": "string",
                        "description": "Recommended model for this step.",
                    },
                    "effort": {
                        "type": "string",
                        "enum": ["Low", "Medium", "High", ""],
                        "description": (
                            "Reasoning effort for Claude steps (Claude Code "
                            "/effort setting; High = Extended Thinking in "
                            "Claude Desktop). Empty string for Perplexity."
                        ),
                    },
                    "transition": {
                        "type": "string",
                        "description": (
                            "How to move context from the previous step into "
                            "this app. Empty string if not needed."
                        ),
                    },
                    "prompt": {
                        "type": "string",
                        "description": "The copy-paste prompt for this step.",
                    },
                },
                "required": ["title", "app", "model", "effort", "transition", "prompt"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "strategy_summary",
        "recommended_environments",
        "effort_level",
        "steps",
    ],
    "additionalProperties": False,
}

REVIEW_SYSTEM = """\
You are the final quality reviewer for an AI workflow planner. You receive
the user's original goal and the generated workflow. Judge one thing only:
does executing this workflow, step by step, fully deliver the user's goal?

Mark "aligned" false when the workflow misses part of the goal, adds steps
the user did not ask for, targets the wrong deliverable, or has step prompts
too vague to produce the intended output. Also verify every Claude Desktop /
Claude Code step recommends a model and an effort level. When misaligned,
write concrete, actionable "feedback" the planner can apply in one revision.
When aligned, "feedback" is an empty string.
"""

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "aligned": {
            "type": "boolean",
            "description": "True when the workflow fully delivers the goal.",
        },
        "feedback": {
            "type": "string",
            "description": "Revision instructions when misaligned; else empty.",
        },
    },
    "required": ["aligned", "feedback"],
    "additionalProperties": False,
}


def get_passcodes() -> list[str]:
    """Return the two configured login passcodes.

    Read from the APP_PASSCODES env var or Streamlit secrets as a
    comma-separated pair, e.g. APP_PASSCODES="alpha-1234,bravo-5678".
    """
    raw = os.environ.get("APP_PASSCODES")
    if not raw:
        try:
            raw = st.secrets.get("APP_PASSCODES", None)
        except Exception:
            raw = None
    if not raw:
        return []
    return [p.strip() for p in str(raw).split(",") if p.strip()][:2]


def check_login() -> bool:
    """Render the login page until a valid passcode is entered."""
    if st.session_state.get("authenticated"):
        return True

    st.title("🧭 AI Workflow Architect")
    st.subheader("Sign in")

    passcodes = get_passcodes()
    if not passcodes:
        st.warning("No passcodes configured. Set `APP_PASSCODES` to enable login.")
        return False

    with st.form("login_form"):
        entered = st.text_input("Passcode", type="password")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

    if submitted:
        if any(hmac.compare_digest(entered, code) for code in passcodes):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect passcode.")
    return False


def get_client() -> anthropic.Anthropic | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets.get("ANTHROPIC_API_KEY", None)
        except Exception:
            api_key = None
    if not api_key:
        api_key = st.session_state.get("api_key_input") or None
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def get_perplexity_key() -> str | None:
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets.get("PERPLEXITY_API_KEY", None)
        except Exception:
            api_key = None
    if not api_key:
        api_key = st.session_state.get("perplexity_key_input") or None
    return api_key


def run_research(api_key: str, query: str) -> str | None:
    """Run one Perplexity search to gather live context for the planner.

    Returns the research findings (with source URLs when available), or None
    if the search fails — research is best-effort and never blocks planning.
    """
    try:
        response = requests.post(
            PERPLEXITY_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": PERPLEXITY_RESEARCH_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a research assistant. Answer concisely "
                            "with current, factual information the requester "
                            "can plan against. Include key names, versions, "
                            "and dates."
                        ),
                    },
                    {"role": "user", "content": query},
                ],
            },
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()
        findings = data["choices"][0]["message"]["content"]
        sources = data.get("citations") or data.get("search_results") or []
        urls = [s["url"] if isinstance(s, dict) else s for s in sources][:5]
        if urls:
            findings += "\n\nSources:\n" + "\n".join(f"- {u}" for u in urls)
        return findings
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return None


def extract_json(response) -> dict:
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def route_task(client: anthropic.Anthropic, task: str) -> dict:
    """Layer 1 — Haiku classifies task complexity."""
    response = client.messages.create(
        model=ROUTER_MODEL,
        max_tokens=300,
        system=ROUTER_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": ROUTER_SCHEMA}},
        messages=[{"role": "user", "content": f"Task: {task}"}],
    )
    return extract_json(response)


def generate_workflow(
    client: anthropic.Anthropic,
    task: str,
    complexity: str,
    research: str | None = None,
    prior_workflow: dict | None = None,
    feedback: str | None = None,
) -> tuple[dict, str]:
    """Layer 2 — Haiku (simple) or Sonnet (complex) generates the workflow.

    Pass `research` to ground the plan in live findings. Pass both
    `prior_workflow` and `feedback` to run a revision instead of a fresh
    generation.
    """
    model = (
        COMPLEX_GENERATOR_MODEL if complexity == "complex" else SIMPLE_GENERATOR_MODEL
    )
    parts = [f"Design the workflow for this task:\n\n{task}"]
    if research:
        parts.append(f"Research findings (from a live web search):\n\n{research}")
    if prior_workflow and feedback:
        parts.append(
            "Your previous workflow draft did not pass the alignment review.\n\n"
            f"Previous draft:\n{json.dumps(prior_workflow, indent=2)}\n\n"
            f"Reviewer feedback:\n{feedback}\n\n"
            "Produce a revised workflow that fully addresses the feedback."
        )
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        system=GENERATOR_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": GENERATOR_SCHEMA}},
        messages=[{"role": "user", "content": "\n\n---\n\n".join(parts)}],
    )
    return extract_json(response), model


def review_workflow(
    client: anthropic.Anthropic, task: str, workflow: dict, model: str
) -> dict:
    """Final review — verify the workflow is aligned with the user's goal."""
    response = client.messages.create(
        model=model,
        max_tokens=1000,
        system=REVIEW_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": (
                    f"User's goal:\n{task}\n\n"
                    f"Generated workflow:\n{json.dumps(workflow, indent=2)}"
                ),
            }
        ],
    )
    return extract_json(response)


def app_badge(app_name: str) -> str:
    color = APP_BADGE_COLORS.get(app_name, "#555555")
    return (
        f'<span style="background-color:{color}; color:white; padding:3px 12px; '
        f'border-radius:12px; font-size:0.85em; font-weight:600; '
        f'white-space:nowrap;">{app_name}</span>'
    )


def render_workflow(workflow: dict) -> None:
    st.subheader("Strategy")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(
            "**Recommended Environments:** "
            + " ".join(app_badge(env) for env in workflow["recommended_environments"]),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(f"**Effort Level:** {workflow['effort_level']}")
    st.write(workflow["strategy_summary"])

    st.subheader("Chained Workflow")
    for i, step in enumerate(workflow["steps"], start=1):
        if step["transition"].strip():
            st.info(f"**Transition:** {step['transition']}")
        with st.container(border=True):
            header_col, badge_col = st.columns([3, 1])
            with header_col:
                st.markdown(f"#### Step {i}: {step['title']}")
            with badge_col:
                st.markdown(
                    f'<div style="text-align:right; padding-top:14px;">'
                    f'{app_badge(step["app"])}</div>',
                    unsafe_allow_html=True,
                )
            caption = f"Paste in: **{step['app']}** · Model: `{step['model']}`"
            if step.get("effort", "").strip():
                caption += f" · Effort: **{step['effort']}**"
            st.caption(caption)
            st.code(step["prompt"], language=None, wrap_lines=True)


def main() -> None:
    st.set_page_config(page_title="AI Workflow Architect", page_icon="🧭", layout="centered")

    if not check_login():
        return

    with st.sidebar:
        if st.button("Sign out", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    st.title("🧭 AI Workflow Architect")
    st.caption(
        "Describe your goal and get a chained, copy-paste workflow routed to the "
        "best apps: Claude Desktop, Claude Code, or Perplexity."
    )

    client = get_client()
    if client is None:
        st.text_input(
            "Anthropic API key",
            type="password",
            key="api_key_input",
            help="Used only to plan your workflow. Never stored.",
        )
        client = get_client()

    perplexity_key = get_perplexity_key()
    if perplexity_key is None:
        with st.expander("Live research (optional)"):
            st.text_input(
                "Perplexity API key",
                type="password",
                key="perplexity_key_input",
                help=(
                    "When set, the planner searches the web for current facts "
                    "before designing your workflow. Never stored."
                ),
            )
        perplexity_key = get_perplexity_key()

    task = st.text_area(
        "Describe your task or goal.",
        height=140,
        placeholder="e.g. Research AI agent frameworks in 2026 and write a whitepaper.",
        key="task_input",
    )

    # Editing the input invalidates the previous result: clear it from memory
    # so a stale workflow is never shown alongside a different task.
    if "workflow" in st.session_state and task.strip() != st.session_state.get(
        "workflow_task"
    ):
        del st.session_state["workflow"]
        st.session_state.pop("workflow_task", None)
        st.session_state.pop("workflow_notes", None)

    if st.button("Architect My Workflow", type="primary", use_container_width=True):
        if client is None:
            st.error("Enter your Anthropic API key above to continue.")
            st.stop()
        if not task.strip():
            st.warning("Describe your task first.")
            st.stop()

        notes = []
        try:
            with st.spinner("Analyzing task complexity…"):
                route = route_task(client, task.strip())

            research = None
            if route.get("needs_research") and route.get("research_query", "").strip():
                if perplexity_key:
                    with st.spinner("Researching current information…"):
                        research = run_research(
                            perplexity_key, route["research_query"].strip()
                        )
                    if research:
                        notes.append("🔎 Grounded in live Perplexity research.")
                    else:
                        notes.append(
                            "🔎 Live research was unavailable — planned from "
                            "built-in knowledge."
                        )
                else:
                    notes.append(
                        "🔎 This task would benefit from live research — add a "
                        "Perplexity API key to enable it."
                    )

            with st.spinner("Designing your workflow…"):
                workflow, model_used = generate_workflow(
                    client, task.strip(), route["complexity"], research=research
                )

            with st.spinner("Reviewing alignment with your goal…"):
                review = review_workflow(client, task.strip(), workflow, model_used)
                if not review["aligned"] and review["feedback"].strip():
                    workflow, _ = generate_workflow(
                        client,
                        task.strip(),
                        route["complexity"],
                        research=research,
                        prior_workflow=workflow,
                        feedback=review["feedback"],
                    )
                    review = review_workflow(
                        client, task.strip(), workflow, model_used
                    )
            if review["aligned"]:
                notes.append("✅ Final review: workflow is aligned with your goal.")
            else:
                notes.append(
                    "⚠️ Final review: the workflow may not fully cover your goal — "
                    + review["feedback"]
                )
        except anthropic.AuthenticationError:
            st.error("Invalid Anthropic API key.")
            st.stop()
        except anthropic.RateLimitError:
            st.error("The planner is busy right now — please try again in a moment.")
            st.stop()
        except anthropic.APIStatusError as e:
            st.error(f"The planner request failed ({e.status_code}). Please try again.")
            st.stop()
        except anthropic.APIConnectionError:
            st.error("Could not reach the planning service. Check your connection.")
            st.stop()
        except (json.JSONDecodeError, StopIteration, KeyError):
            st.error("The planner returned an unexpected response. Please try again.")
            st.stop()

        st.session_state["workflow"] = workflow
        st.session_state["workflow_task"] = task.strip()
        st.session_state["workflow_notes"] = notes

    if "workflow" in st.session_state:
        st.divider()
        for note in st.session_state.get("workflow_notes", []):
            st.caption(note)
        render_workflow(st.session_state["workflow"])


if __name__ == "__main__":
    main()
