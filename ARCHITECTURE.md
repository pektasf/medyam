# Eski Usul AI Studio — Architecture v0.2

## Product decisions
- Local-first Windows app; FastAPI + static UI + SQLite + local filesystem.
- Hybrid model gateway: Gemini API or local Ollama. One model provider can serve multiple specialist agents with distinct instructions and deliverables.
- User approval required for script acceptance, media rights, final video and any future publishing action.

## Runtime
1. UI submits a content brief to `/api/workflows/run`.
2. FastAPI creates a workflow and 10 pending specialist execution records.
3. The lightweight orchestrator runs specialists sequentially and persists each handoff in SQLite.
4. Research specialist calls DDGS web search; returned source titles, URLs and snippets are passed to downstream agents.
5. Each specialist receives the brief plus completed upstream outputs and returns structured JSON.
6. Failure stops the workflow and marks remaining steps skipped; no fake success state.
7. Successful script draft is stored separately and workflow ends at `awaiting_human_review`.
8. Existing media and FFmpeg export remain separate from script approval.

## Specialist roster
Executive Producer -> Research & Trend Analyst -> Audience Strategist -> Creative Director -> Lead Scriptwriter -> Fact Checker -> Visual Producer -> Localization Editor -> Editorial & Rights Auditor -> Publishing Strategist.

## Persistence
- `workflows`: one record per content production run.
- `agent_executions`: one record per specialist per run, including status, provider, output and error.
- `scripts`, `assets`, `metrics`, `tasks`: existing product data and dashboard registry.

## Why a lightweight orchestrator first
The current workflow is intentionally implemented without a heavyweight agent framework so it stays easy to install on a Windows laptop with 16 GB RAM. Each specialist is a real, separate model invocation with a dedicated mission and structured handoff. LangGraph can be introduced later when resumable checkpoints, branching, parallel work, tool permissions and human interrupts are needed; it is not required to make the current specialist team real.

## Safety gates
- Research sources are evidence references, not permission to reuse copyrighted material.
- Visual Producer may propose search terms but does not claim that an asset was acquired or licensed.
- Publishing Strategist creates drafts only; no auto-publishing, likes, follows, comments or purchased engagement.
- A failed agent stops the run. A human reviews the script, rights and final video separately.

## Next milestones
1. Official Pexels/Pixabay API adapters with license/source capture and explicit asset review.
2. Scene-to-asset matching and visual quality checks.
3. Timeline-based FFmpeg editor with voiceover, subtitles and sound mixing.
4. Whisper transcription and subtitle alignment.
5. Optional LangGraph migration for retries, resumable checkpoints, branching and controlled parallel agents.
6. TikTok analytics import and official publishing adapter only where supported and explicitly approved.
