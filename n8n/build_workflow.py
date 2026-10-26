"""Builds n8n/b2b-list-freshness-check.json. Run: python3 n8n/build_workflow.py

On the first of every month, the workflow reads your contact list from a Google Sheet, re-exports a sample
of its people from Sales Navigator through the Evaboot MCP, compares each person with the row in the sheet
like freshness.py compare (with the old emails verified today), and writes the status and the action next to each checked row.
"""
import json
import uuid
from pathlib import Path

MCP = "https://mcp.evaboot.com/mcp"
EVABOOT_CRED = {"httpBearerAuth": {"id": "", "name": "Evaboot MCP (Bearer)"}}
SHEETS_CRED = {"googleSheetsOAuth2Api": {"id": "", "name": "Google Sheets account"}}

nodes, connections = [], {}


def node(name, type_, version, params, pos, creds=None, **extra):
    n = {"parameters": params, "id": str(uuid.uuid4()), "name": name, "type": type_,
         "typeVersion": version, "position": pos, **extra}
    if creds:
        n["credentials"] = creds
    nodes.append(n)


def link(a, b, out=0):
    connections.setdefault(a, {}).setdefault("main", [])
    while len(connections[a]["main"]) <= out:
        connections[a]["main"].append([])
    connections[a]["main"][out].append({"node": b, "type": "main", "index": 0})


def code(name, js, pos, **extra):
    node(name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos, **extra)


def mcp_call(name, tool, json_expr, pos):
    node(name, "@n8n/n8n-nodes-langchain.mcpClient", 1.1, {
        "endpointUrl": MCP, "authentication": "bearerAuth",
        "tool": {"__rl": True, "mode": "list", "value": tool, "cachedResultName": tool},
        "inputMode": "json", "jsonInput": json_expr, "options": {"timeout": 120000},
    }, pos, EVABOOT_CRED)


PICK_JS = r"""
// The people to re-check: rows with a Sales Navigator lead id (ACw...), not checked this month,
// shuffled, up to the sample size. Public linkedin.com/in/ links cannot be re-exported.
const s = $('Your settings').first().json;
const size = Math.min(Number(s.sample_size) || 50, 2500);
const month = $now.toFormat('yyyy-MM');
const rows = $input.all().map(i => i.json);
const people = [];
let noId = 0;
for (const r of rows) {
  const m = String(r['Sales Navigator URL'] || r['Linkedin URL Unique ID'] || '').match(/(ACw[A-Za-z0-9_-]{20,})/);
  if (!m) { noId++; continue; }
  if (String(r['Checked on'] || '').startsWith(month)) continue;
  people.push({ id: m[1], row: r });
}
for (let i = people.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [people[i], people[j]] = [people[j], people[i]]; }
const picked = people.slice(0, size);
if (!picked.length) return [];
return [{ json: { ids: picked.map(p => p.id), rows: picked.map(p => p.row), skipped_without_id: noId } }];
"""

COMPARE_JS = r"""
// Same rules as freshness.py compare: same job, new title, left the company, not found; then the email,\n// where today's verification of the old address beats a comparison of two finder results.
const norm = s => String(s || '').toLowerCase().replace(/,/g, ' ').split(/\s+/).filter(Boolean).join(' ');
const idOf = p => (String(p['Linkedin URL Unique ID'] || p['Sales Navigator URL'] || '').match(/(ACw[A-Za-z0-9_-]{20,})/) || [])[1];
const fresh = Object.fromEntries(($('Check the export').last().json.structuredContent.result.prospects || []).map(p => [idOf(p), p]));
const ACTIONS = { 'same job': 'keep', 'new title': 'update the title',
                  'left the company': 'replace: find who holds the role now', 'not found': 'remove: the profile is gone or private' };
const checkedOn = $now.toFormat('yyyy-MM-dd');
const today = Object.fromEntries(($('Check the verification').last().json.structuredContent?.result?.prospects || [])
  .map(v => [String(v.email).toLowerCase(), String(v.email_validity || '').toLowerCase()]));
const picked = $('Pick people').first().json;
return picked.ids.map((id, k) => {
  const o = picked.rows[k], n = fresh[id];
  let status = 'not found';
  if (n) {
    // The first company field both sides have, like freshness.py.
    const f = ['Company Linkedin URL Unique ID', 'Company Domain', 'Company Name'].find(k => o[k] && n[k]);
    if (!f || norm(o[f]) !== norm(n[f])) status = 'left the company';
    else if (norm(o['Current Job']) !== norm(n['Current Job'])) status = 'new title';
    else status = 'same job';
  }
  const oldEmail = String(o['Email'] || '').toLowerCase(), newEmail = String(n && n['Email'] || '').toLowerCase();
  const newSafe = String(n && n['Email Status'] || '').toLowerCase() === 'safe';
  let email = 'unknown';
  if (n) email = !oldEmail ? (newEmail ? 'new email found' : 'still none')
    : (oldEmail !== newEmail ? (newEmail ? 'changed' : 'lost')
      : (String(o['Email Status'] || '').toLowerCase() === 'safe' && !newSafe ? 'no longer safe' : 'same'));
  const now = oldEmail ? (today[oldEmail] || '') : '';
  if (now) email = status === 'left the company' ? (now === 'safe' ? 'old email still accepts mail' : `old email ${now}`)
    : (now === 'safe' ? 'old email still verifies' : `old email ${now}`);
  let action = ACTIONS[status];
  if (['same job', 'new title'].includes(status)) {
    if (email === 'new email found' || (email.startsWith('old email ') && !email.endsWith('verifies')))
      action = status === 'same job' ? (newSafe ? 'update the email' : 'check the email') : action + ' and the email';
    else if (!now && ['changed', 'lost', 'no longer safe'].includes(email))
      action = status === 'same job' ? 'update the email' : action + ' and the email';
  }
  return { json: {
    'Sales Navigator URL': o['Sales Navigator URL'], 'Status': status, 'New title': n ? n['Current Job'] || '' : '',
    'New company': n ? n['Company Name'] || '' : '', 'New email': n ? n['Email'] || '' : '',
    'Email now': email + (n && n['Email Status'] && !email.startsWith('old email') ? ` (new: ${n['Email Status']})` : ''),
    'Action': action, 'Checked on': checkedOn,
  } };
});
"""

node("First of the month", "n8n-nodes-base.scheduleTrigger", 1.2, {"rule": {"interval": [
    {"field": "cronExpression", "expression": "0 8 1 * *"}]}}, [0, 0])
node("Your settings", "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": [
    {"id": str(uuid.uuid4()), "name": k, "type": "string", "value": v} for k, v in [
        ("list_tab_url", "PASTE_YOUR_LIST_TAB_URL_WITH_GID"),
        ("sample_size", "50"),
    ]]}, "includeOtherFields": True, "options": {}}, [220, 0])
node("Your list", "n8n-nodes-base.googleSheets", 4.7, {
    "operation": "read",
    "documentId": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.list_tab_url }}"},
    "sheetName": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.list_tab_url }}"},
    "options": {}}, [440, 0], SHEETS_CRED, alwaysOutputData=True)
code("Pick people", PICK_JS, [660, 0])
mcp_call("Verify the old emails", "verify_email",
         "={{ JSON.stringify({ job_name: 'Freshness check ' + $now.toFormat('yyyy-MM-dd'), prospects: "
         "$('Pick people').first().json.rows.filter(r => r.Email).map(r => ({ email: r.Email })) }) }}", [880, 0])
nodes[-1]["onError"] = "continueRegularOutput"   # a list without emails has nothing to verify
mcp_call("Re-export with Evaboot", "export_profile_list",
         "={{ JSON.stringify({ profile_ids: $('Pick people').first().json.ids, search_name: 'Freshness check ' + $now.toFormat('yyyy-MM-dd') }) }}",
         [1100, 0])
node("Wait 60 s", "n8n-nodes-base.wait", 1.1, {"amount": 60}, [1320, 0])
mcp_call("Check the export", "get_export",
         "={{ JSON.stringify({ extraction_id: $('Re-export with Evaboot').first().json.structuredContent.result.extraction_id }) }}",
         [1540, 0])
node("Done?", "n8n-nodes-base.if", 2.2, {"conditions": {
    "options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
    "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $json.structuredContent.result.status }}",
                    "rightValue": "EXECUTED", "operator": {"type": "string", "operation": "equals"}}],
    "combinator": "and"}, "options": {}}, [1760, 0])
code("Still running?", r"""
// Stop instead of waiting forever when the export failed.
const r = $json.structuredContent.result;
if (r.failure_reason || /FAIL|ERROR|CANCEL/i.test(r.status || '')) throw new Error(`The export stopped: ${r.status} ${r.failure_reason || ''}`);
return [$input.first()];
""", [1760, -200])
mcp_call("Check the verification", "get_email_verification_job",
         "={{ JSON.stringify({ job_id: $('Verify the old emails').first().json.structuredContent.result.job_id }) }}", [880, 300])
nodes[-1]["onError"] = "continueRegularOutput"
node("Verified?", "n8n-nodes-base.if", 2.2, {"conditions": {
    "options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
    "conditions": [{"id": str(uuid.uuid4()),
                    "leftValue": "={{ $json.structuredContent?.result?.status === 'complete' || "
                                 "!$('Verify the old emails').first().json.structuredContent?.result?.job_id }}",
                    "rightValue": "", "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
    "combinator": "and"}, "options": {}}, [1100, 300])
code("Verification failed?", r"""
// Stop instead of waiting forever when the email check failed.
const r = $json.structuredContent?.result || {};
if (r.error_message || /fail|error|cancel/i.test(r.status || '')) throw new Error(`The email check stopped: ${r.status} ${r.error_message || ''}`);
return [$input.first()];
""", [1100, 480])
node("Wait 30 s", "n8n-nodes-base.wait", 1.1, {"amount": 30}, [880, 480])
code("Compare", COMPARE_JS, [1320, 300])
node("Update your list", "n8n-nodes-base.googleSheets", 4.7, {
    "operation": "update",
    "documentId": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.list_tab_url }}"},
    "sheetName": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.list_tab_url }}"},
    "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": ["Sales Navigator URL"], "schema": []},
    "options": {}}, [1540, 300], SHEETS_CRED)

for a, b in [("First of the month", "Your settings"), ("Your settings", "Your list"), ("Your list", "Pick people"),
             ("Pick people", "Verify the old emails"), ("Verify the old emails", "Re-export with Evaboot"),
             ("Re-export with Evaboot", "Wait 60 s"),
             ("Wait 60 s", "Check the export"), ("Check the export", "Done?"), ("Compare", "Update your list"),
             ("Still running?", "Wait 60 s"), ("Check the verification", "Verified?"), ("Wait 30 s", "Check the verification")]:
    link(a, b)
link("Done?", "Check the verification", out=0)
link("Verified?", "Compare", out=0)
link("Verified?", "Verification failed?", out=1)
link("Verification failed?", "Wait 30 s")
link("Done?", "Still running?", out=1)

wf = {"name": "B2B list freshness check (Evaboot)", "nodes": nodes, "connections": connections,
      "settings": {"executionOrder": "v1"}, "pinData": {}, "active": False}
out = Path(__file__).with_name("b2b-list-freshness-check.json")
out.write_text(json.dumps(wf, indent=2) + "\n")
print(out, len(nodes), "nodes")
