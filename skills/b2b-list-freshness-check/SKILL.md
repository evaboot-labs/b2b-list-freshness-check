---
name: b2b-list-freshness-check
description: Check how stale a B2B contact list is - re-export its people from LinkedIn Sales Navigator through Evaboot, verify the old emails, and report who still holds the same job, who changed title, who left the company and which emails would bounce, with one action per person. Use when the user asks how fresh or accurate a contact database, lead list or CRM segment is, about list decay, or which contacts to update or replace.
---

# B2B list freshness check

This skill runs inside a clone of https://github.com/evaboot-labs/b2b-list-freshness-check: it uses the repo's `freshness.py` and `docs/`. If `freshness.py` is not in the working directory, clone the repo and work from there.

You do the Sales Navigator and Evaboot work through the Evaboot MCP server (`https://mcp.evaboot.com/mcp`). Every tool named below is an Evaboot MCP tool. `freshness.py` picks the people, compares the two exports and writes the actions.

## Rules

- Confirm with the user before `export_profile_list` and `verify_email`. Say the count and the cost (1 Evaboot credit per re-exported person; email verification also uses credits), then wait for a yes.
- Never contact anyone, and never change the user's CRM yourself: hand over the actions file.
- Never ask for or paste an API key. The user writes `EVABOOT_API_KEY` into `.env` and exports it before starting the agent (`docs/connect-your-agent.md`).
- A "left the company" row can be a rebrand or a new company page. Read the old and new company before you call it a departure.

## Step 0: check the setup

1. If the Evaboot MCP tools are not in this session, walk the user through `docs/connect-your-agent.md`, then ask them to restart the agent from this folder.
2. Otherwise call `get_daily_export_quota`. If `has_valid_salesnav` is false, ask the user to sign in to Evaboot in Chrome, open any Sales Navigator search with the Evaboot extension, and click Export with Evaboot, then call it again.
3. Run `mkdir -p data queue`.

## Step 1: get the old list

The list needs **a Sales Navigator lead id per person** (`ACw...`, as in a Sales Navigator URL or an Evaboot export). A list with only public `linkedin.com/in/` links or only names cannot be re-checked this way: say so.

- An old Evaboot export: `get_export_list`, pick it, then `set -a; [ -n "$EVABOOT_API_KEY" ] || . ./.env; set +a; curl -s -H "Authorization: Bearer $EVABOOT_API_KEY" https://api.evaboot.com/v1/extractions/<id>/ > data/old.json`.
- A CSV from the CRM or another tool: save it as `data/old.csv`, with a column holding the Sales Navigator URL. Columns named `Title`, `Company` or `Email Address` are read as well; a company name is enough to compare.

In the commands below, use `data/old.csv` instead of `data/old.json` if you saved a CSV.

## Step 2: pick the people and re-export them

```bash
python3 freshness.py sample data/old.json --size 50 > queue/ids.json
```

50 people give a good estimate for the whole list; use `--size` up to the full list to clean every row. On a yes, call `export_profile_list` with the ids from `queue/ids.json` (bare `ACw...` ids: public profile URLs are refused) and a `search_name` such as "Freshness check <list name>". Poll `get_export` with `limit: 0` until `EXECUTED`, then save it with the same curl as step 1 to `data/new.json`.

## Step 3: verify the old emails

The re-export finds today's email; the question for the old list is whether **its** emails still work. On a yes, call `verify_email` with the old list's emails for the same people, poll `get_email_verification_job` until its status is `complete`, and save its `prospects` array (`[{"email", "email_validity"}]`) as `data/verified.json`.

## Step 4: compare and report

```bash
python3 freshness.py compare data/old.json data/new.json --ids queue/ids.json \
  --verified data/verified.json --csv data/actions.csv
```

Show the report. Then read the rows that are not `keep` in `data/actions.csv` and tell the user what you see: real departures, rebrands, promotions, and emails that would bounce.

## Step 5: replace the people who left

For each "left the company" row the user wants to replace, find who holds the role now:

1. `search_sn_accounts` with `https://www.linkedin.com/sales/search/company?query=(keywords%3A<old company>)`, and pick the matching account (its `entityUrn` ends in the company id).
2. `search_sn_leads` (`count: 25`, free) with `https://www.linkedin.com/sales/search/people?query=(filters%3AList((type%3ACURRENT_COMPANY%2Cvalues%3AList((id%3Aurn%253Ali%253Aorganization%253A<id>%2Ctext%3A<company>%2CselectionType%3AINCLUDED)))))`. Read the titles yourself and name the person in the same role. Never guess: if nobody fits, say so.

## Every month

Offer to run the check again each month on a new sample, or set up the n8n version (`docs/n8n.md`), which re-checks a Google Sheet on the first of the month and writes the status and action next to each row.
