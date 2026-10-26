# Agent instructions

This repo is a B2B list freshness check. It takes a contact list the user already has (an old Evaboot export, or a CSV with Sales Navigator URLs), re-exports a sample of its people from LinkedIn Sales Navigator through Evaboot, verifies the old emails, and reports who still holds the same job, who changed title, who left the company and which emails to fix, with one action per person. When the user asks how fresh or accurate a contact list, database or CRM segment is, or about list decay:

1. Follow the skill in `skills/b2b-list-freshness-check/SKILL.md` step by step.
2. Use `freshness.py` to pick the people, compare the two exports and write the actions. The Evaboot MCP server does the Sales Navigator work (`.mcp.json`).
3. If the user is not connected yet, follow `docs/connect-your-agent.md` with them.
4. If the user wants n8n instead, follow `docs/n8n.md` with them one step at a time: you cannot click inside n8n, so say exactly what to do and wait for their confirmation.

Re-exporting costs 1 Evaboot credit per person, and email verification uses credits too: confirm the count and the cost before each. Never contact anyone and never edit the user's CRM yourself. Never ask for or handle an API key: the user writes it into `.env`. Never commit `.env`, `data/` or `queue/`: they hold real people's data.
