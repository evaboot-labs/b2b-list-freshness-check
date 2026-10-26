# Run it in n8n

[`n8n/b2b-list-freshness-check.json`](../n8n/b2b-list-freshness-check.json) is the same check for n8n. On the first of every month it re-checks a sample of your contact list in a Google Sheet and writes the status and the action next to each row.

## What runs

1. **Your list** (Google Sheets): every row of your list.
2. **Pick people** (Code): rows with a Sales Navigator lead id, not checked this month, shuffled, up to `sample_size`.
3. **Verify the old emails** (MCP Client, `verify_email`): the emails your list holds today.
4. **Re-export with Evaboot** (MCP Client, `export_profile_list`), then **Wait 60 s**, **Check the export** and **Done?** until the export is finished.
5. **Check the verification** and **Verified?** until the email check is finished.
6. **Compare** (Code): the same rules as `freshness.py compare`: same job, new title, left the company or not found, then the email, where today's check of the old address comes first.
7. **Update your list**: Status, New title, New company, New email, Email now, Action and Checked on, on each checked row.

## Set it up

1. **Prepare the sheet:** your list needs a `Sales Navigator URL` column (an Evaboot export has it), and these empty columns:
   `Status, New title, New company, New email, Email now, Action, Checked on`
   The check also reads `Current Job`, `Company Name` and `Email`.
2. **Import** the JSON in n8n: *Workflows > Import from file*.
3. **Add two credentials:**
   - **Bearer Auth** named `Evaboot MCP (Bearer)`: your key from [dash.evaboot.com/dash/api/](https://dash.evaboot.com/dash/api/). Select it on the four MCP Client nodes.
   - **Google Sheets** on **Your list** and **Update your list**.
4. **Fill in Your settings:** `list_tab_url` (with its `gid`) and `sample_size` (50 gives a good estimate; up to 2,500 per run).
5. **Publish** the workflow.
6. **Test:** click **Execute workflow** on **First of the month** and read the new columns.

## Good to know

- Each run costs 1 Evaboot credit per person re-checked, plus the email verification.
- Rows checked this month are skipped, so a second run in the same month checks other people.
- A "left the company" row can be a rebrand or a new company page: read the new company before you replace anyone.
- The replacement search (who holds the role now) is in the agent version.

Back to the [README](../README.md).
