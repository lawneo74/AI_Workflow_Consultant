"""AI Workflow Architect — intelligent Prompt & Workflow Generator.

A Streamlit app that routes a raw user task through a two-tier Anthropic
backend: Haiku categorizes task complexity, then Haiku (simple tasks) or
Sonnet (complex tasks) generates a chained, copy-paste workflow. Each step
is labeled with the app to paste it into (Claude Desktop, Claude Code, or
Perplexity Native), with transition notes when the workflow spans apps.

The app never executes the generated prompts — it is strictly a
copy-paste generator.
"""

import json
import os

import anthropic
import streamlit as st

ROUTER_MODEL = "claude-haiku-4-5"
SIMPLE_GENERATOR_MODEL = "claude-haiku-4-5"
COMPLEX_GENERATOR_MODEL = "claude-sonnet-5"

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
"""

ROUTER_SCHEMA = {
    "type": "object",
    "properties": {
        "complexity": {"type": "string", "enum": ["simple", "complex"]},
        "reasoning": {
            "type": "string",
            "description": "One-sentence justification for the classification.",
        },
    },
    "required": ["complexity", "reasoning"],
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
                "required": ["title", "app", "model", "transition", "prompt"],
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
    client: anthropic.Anthropic, task: str, complexity: str
) -> tuple[dict, str]:
    """Layer 2 — Haiku (simple) or Sonnet (complex) generates the workflow."""
    model = (
        COMPLEX_GENERATOR_MODEL if complexity == "complex" else SIMPLE_GENERATOR_MODEL
    )
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        system=GENERATOR_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": GENERATOR_SCHEMA}},
        messages=[{"role": "user", "content": f"Design the workflow for this task:\n\n{task}"}],
    )
    return extract_json(response), model


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
            st.caption(f"Paste in: **{step['app']}** · Model: `{step['model']}`")
            st.code(step["prompt"], language=None, wrap_lines=True)


def main() -> None:
    st.set_page_config(page_title="AI Workflow Architect", page_icon="🧭", layout="centered")
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

    task = st.text_area(
        "Describe your task or goal.",
        height=140,
        placeholder="e.g. Research AI agent frameworks in 2026 and write a whitepaper.",
    )

    if st.button("Architect My Workflow", type="primary", use_container_width=True):
        if client is None:
            st.error("Enter your Anthropic API key above to continue.")
            st.stop()
        if not task.strip():
            st.warning("Describe your task first.")
            st.stop()

        try:
            with st.spinner("Analyzing task complexity…"):
                route = route_task(client, task.strip())
            with st.spinner("Designing your workflow…"):
                workflow, model_used = generate_workflow(
                    client, task.strip(), route["complexity"]
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

    if "workflow" in st.session_state:
        st.divider()
        render_workflow(st.session_state["workflow"])


if __name__ == "__main__":
    main()
