# Resume Filtering Agent

AI-powered HR recruitment workflow using **LangGraph + Streamlit + MCP** integrations.

## Features
- Resume parsing and JD-based scoring
- Human-in-the-loop review flow with LangGraph interrupt/resume
- Gmail interview invite support via MCP
- Google Calendar free-slot check and meeting booking
- Interview token workflow and candidate tracking
- SQLite-backed candidate lifecycle updates

## Project Structure
- `test.py` — Streamlit dashboard (main app)
- `resume_filtering.py` — resume evaluation graph + HITL + tool orchestration
- `question_generation_and_analyzer.py` — interview analysis and scoring updates
- `interview_frontend.py` — interview-side UI flow
- `mcp_server2.py` — MCP server (Gmail + Calendar tools)
- `mcp_client.py` — MCP client wrappers
- `candidate_db.py` — SQLite helpers

## Quick Start
1. Create and activate virtual env
2. Install dependencies
3. Add local credentials and env values
4. Run dashboard:
   ```bash
   streamlit run test.py
   ```

## Security Notes
- Sensitive files are intentionally git-ignored:
  - `.env`
  - `credentials.json`
  - `token.json`
  - local DB files in `db/`
- Never commit API keys or OAuth tokens.

## Recommended Local Files (not committed)
- `.env`
- `credentials.json`
- `token.json`
