# AI Tool Capabilities

> **How to update this file:** edit it directly on GitHub — open
> `tool_capabilities.md` in the repository, click the pencil (✏️ *Edit this
> file*) icon, make your changes, and commit to `main`. The app reads this
> file at startup and feeds it to the workflow planner, so the next app
> restart picks up your edits automatically — no code changes needed.
> Keep the same overall shape (a comparison table plus combination
> sequences); the content is used as planning knowledge, not parsed as
> config, so plain readable Markdown is all that's required.

## Quick-reference comparison: strengths and output formats

| Tool | Core strength | Primary output formats | Not well-suited for |
|---|---|---|---|
| Claude (chat/Projects/Cowork) | Long-context reasoning, high-quality structured writing, polished office deliverables, autonomous local file work | PPTX, XLSX, DOCX, PDF, MD, HTML/CSS/JS artifacts, code/scripts | Live web discovery of current facts; source-grounded citation to a fixed corpus |
| Claude Code | Real code execution, software engineering, git-native agentic coding | Source code/repos, CSV, JSON, XLSX (via code), PNG/SVG charts, PRs/commits | Narrative writing/design polish; open-web research |
| Perplexity (chat/Deep Research/Computer/Comet/Spaces) | Live, cited web research; multi-step research-to-deliverable; live browsing/publishing | MD reports, PDF, DOCX (on demand), XLSX, PPTX, dashboards, published websites/web apps, images | Deep reasoning over a large private/offline corpus already in hand; bespoke complex document design |
| NotebookLM (Gemini Notebook) | Source-grounded Q&A and artifact generation from a defined corpus; teaching/study aids | PPTX, PDF, DOCX, MD, CSV, JSON, XLSX, PNG/SVG charts, images (via Nano Banana), audio/video overviews | Open-ended web research beyond your corpus; software engineering |
| Gemini / Nano Banana (Pro) | State-of-the-art image generation and editing; visual consistency; text-in-image | PNG, JPG (images only) | Text documents, data analysis, code, spreadsheets |

## Combinations and sequences by task type

**Current-events / landscape / competitive research → written deliverable**
Sequence: Perplexity (Deep Research, cited findings) → Claude (structure into report/brief, export DOCX or PDF) → Nano Banana (optional cover graphic/infographic).
Use when: the topic requires up-to-date facts not in your own files, and the final output is a formal document.

**Existing corpus (papers, policy docs, past course materials) → teaching or study artifacts**
Sequence: NotebookLM (upload sources, generate slides/PDF/quizzes/flashcards directly) → optionally Claude (refine narrative/rubric alignment) → Nano Banana (polish visuals).
Use when: grounded citation to specific source passages matters (academic integrity, evidence-based curriculum decisions).

**Recurring project / course / grant knowledge base**
Sequence: Claude Projects (persistent instructions + files as the working knowledge base) ↔ NotebookLM (mirror finalized sources for student/collaborator-facing grounded Q&A and slide generation).
Use when: the same context is reused across many sessions over weeks/months.

**Data analysis with quantitative rigor**
Sequence: Claude Code (clean, analyze, chart a dataset via real code execution) → Claude chat (weave results into a report or slide narrative, export PPTX/XLSX). Alternative: NotebookLM's built-in code layer if the data is part of a grounded source set already in a notebook.
Use when: statistics, formulas, or reproducible computation are required, not just narrative summary.

**Software/app/tool building**
Sequence: Claude Code (build, test, iterate, commit/PR) → Claude in Chrome or browser testing to validate the running app.
Use when: the deliverable is working code or an application, not a document.

**Publishing a live website, dashboard, or shareable web artifact**
Sequence: Perplexity Computer (research → build → publish to a URL) or Claude (Artifacts for a self-contained web app, shared as a file/link).
Use when: the end deliverable should be browsable online rather than downloaded.

**Visual asset creation or polish (posters, infographics, diagrams, comics)**
Sequence: Draft content/structure in Claude or NotebookLM → generate/edit final visuals in Nano Banana (Pro) for resolution, consistency, and embedded text.
Use when: visual quality and text-in-image accuracy are the priority, or a consistent character/brand must appear across multiple images.

**Team-shared, ongoing research repository**
Sequence: Perplexity Spaces (shared files, reusable Skills, persistent Brain memory) or Claude Projects, depending on whether live web research (Spaces) or structured document production (Projects) is the more frequent need.
