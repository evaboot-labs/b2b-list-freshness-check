"""Helpers for the B2B list freshness check. Your agent re-exports the people of an old list from Sales
Navigator with the Evaboot MCP; these commands pick the people to re-check, compare the two exports and
tell you who to keep, update or replace. Nothing here touches the network.

    python3 freshness.py sample data/old.json --size 50 [--seed 1] > queue/ids.json    lead ids to re-export
    python3 freshness.py compare data/old.json data/new.json --ids queue/ids.json [--csv data/actions.csv]\n                                                                    what changed, per person
"""
import argparse
import collections
import csv
import json
import random
import re
import sys

LEAD_ID = re.compile(r"(ACw[A-Za-z0-9_-]{20,})")
ACTIONS = {
    "same job": "keep",
    "new title": "update the title",
    "left the company": "replace: find who holds the role now",
    "not found": "remove: the profile is gone or private",
}


def lead_id(p):
    for key in ("Linkedin URL Unique ID", "Sales Navigator URL", "Linkedin URL", "LinkedIn"):
        m = LEAD_ID.search(str(p.get(key) or ""))
        if m:
            return m.group(1)
    return None


def load(path):
    """An Evaboot export (JSON with prospects) or a CSV with a Sales Navigator URL or lead id per row."""
    if path.endswith(".csv"):
        rows = list(csv.DictReader(open(path, newline="", encoding="utf-8-sig")))
    else:
        data = json.load(open(path))
        rows = data.get("prospects", data) if isinstance(data, dict) else data
    out, missing = {}, 0
    for p in rows:
        for field, names in ALIASES.items():
            if not p.get(field):
                p[field] = next((p[a] for a in names if p.get(a)), p.get(field, ""))
        lid = lead_id(p)
        if lid:
            out[lid] = p
        else:
            missing += 1
    if missing:
        print(f"{missing} rows have no Sales Navigator lead id (ACw...) and are left out", file=sys.stderr)
    return out


def norm(s):
    return " ".join(str(s or "").lower().replace(",", " ").split())


COMPANY_FIELDS = ("Company Linkedin URL Unique ID", "Company Domain", "Company Name")
ALIASES = {"Current Job": ("Title", "Job Title", "Job title", "Position"), "Company Name": ("Company", "Account Name"),
           "Email": ("Email Address", "Work Email", "E-mail"), "First Name": ("First name",), "Last Name": ("Last name",)}


def same_company(o, n):
    """Compares on the first company field both sides have, so a CSV with only a company name still works."""
    for f in COMPANY_FIELDS:
        if o.get(f) and n.get(f):
            return norm(o[f]) == norm(n[f])
    return False


def verified(path):
    """email -> status today, from a verify_email job result (a list, or a dict holding one)."""
    if not path:
        return {}
    data = json.load(open(path))
    if isinstance(data, dict):
        data = data.get("prospects") or data.get("result", {}).get("prospects") or []
    out = {}
    for r in data:
        email = r.get("email") or r.get("Email")
        status = r.get("email_validity") or r.get("email_status") or r.get("Email Status")
        if email:
            out[email.lower()] = str(status or "").lower()
    return out


def compare(old, new, today=None):
    """One row per person of the old list: status, what changed, the email then and now, and whether
    the old email still passes verification today."""
    today = today or {}
    rows = []
    for lid, o in old.items():
        n = new.get(lid)
        row = {"id": lid, "name": f"{o.get('First Name', '')} {o.get('Last Name', '')}".strip(),
               "old_title": o.get("Current Job") or "", "old_company": o.get("Company Name") or "",
               "old_email": o.get("Email") or "", "old_email_status": o.get("Email Status") or "not found"}
        if not n:
            row.update(status="not found", new_title="", new_company="", new_email="", new_email_status="")
        else:
            row.update(new_title=n.get("Current Job") or "", new_company=n.get("Company Name") or "",
                       new_email=n.get("Email") or "", new_email_status=n.get("Email Status") or "not found")
            if not same_company(o, n):
                row["status"] = "left the company"
            elif norm(o.get("Current Job")) != norm(n.get("Current Job")):
                row["status"] = "new title"
            else:
                row["status"] = "same job"
        old_ok = row["old_email_status"].lower() == "safe"
        new_ok = row["new_email_status"].lower() == "safe"
        if row["status"] == "not found":
            row["email"] = "unknown"
        elif not row["old_email"]:
            row["email"] = "new email found" if row["new_email"] else "still none"
        elif row["old_email"].lower() != row["new_email"].lower():
            row["email"] = "changed" if row["new_email"] else "lost"
        elif old_ok and not new_ok:
            row["email"] = "no longer safe"
        else:
            row["email"] = "same"
        row["old_email_today"] = now = today.get(row["old_email"].lower(), "") if row["old_email"] else ""
        if now:
            # Today's verification of the old address beats a comparison of two finder results.
            if row["status"] == "left the company":
                row["email"] = "old email still accepts mail" if now == "safe" else f"old email {now}"
            elif now == "safe":
                row["email"] = "old email still verifies"
            else:
                row["email"] = f"old email {now}"
        row["action"] = ACTIONS[row["status"]]
        if row["status"] in ("same job", "new title"):
            if row["email"] == "new email found" or (row["email"].startswith("old email ") and not row["email"].endswith("verifies")):
                row["action"] = ("update the email" if row["new_email_status"].lower() == "safe" else "check the email") \
                    if row["status"] == "same job" else row["action"] + " and the email"
            elif not now and row["email"] in ("changed", "lost", "no longer safe"):
                row["action"] = "update the email" if row["status"] == "same job" else row["action"] + " and the email"
        rows.append(row)
    return rows


def report(rows):
    n = len(rows)
    status = collections.Counter(r["status"] for r in rows)
    email = collections.Counter(r["email"] for r in rows if r["status"] != "not found")
    action = collections.Counter(r["action"] for r in rows)
    print(f"{n} people re-checked")
    for s in ACTIONS:
        print(f"  {s:<30}{status.get(s, 0):>4}  ({status.get(s, 0) / n:.0%})")
    print("email, for the people found:")
    for s, c in email.most_common():
        print(f"  {s:<30}{c:>4}")
    today = collections.Counter(r["old_email_today"] for r in rows if r["old_email_today"])
    if today:
        k = sum(today.values())
        print(f"the old list's emails, verified today ({k}):")
        for s, c in today.most_common():
            print(f"  {s:<30}{c:>4}  ({c / k:.0%})")
    stale = n - action.get("keep", 0)
    print(f"{stale} of {n} rows ({stale / n:.0%}) need an update, a replacement or a removal")
    for a, c in action.most_common():
        print(f"  {a}: {c}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("sample")
    a.add_argument("old")
    a.add_argument("--size", type=int, default=50)
    a.add_argument("--seed", type=int, default=1)
    a = sub.add_parser("compare")
    a.add_argument("old")
    a.add_argument("new")
    a.add_argument("--ids", help="the lead ids you re-exported (the output of sample)")
    a.add_argument("--verified", help="the verify_email results for the old emails")
    a.add_argument("--csv")
    args = ap.parse_args()
    old = load(args.old)
    if args.cmd == "sample":
        ids = sorted(old)
        random.Random(args.seed).shuffle(ids)
        print(json.dumps(ids[:args.size]))
        print(f"{min(args.size, len(ids))} of {len(ids)} people picked", file=sys.stderr)
        return
    new = load(args.new)
    if not set(new) & set(old):
        sys.exit("no person in common: is this the re-export of the same people?")
    if args.ids:
        asked = json.load(open(args.ids))
    else:
        asked = list(new)
        print("no --ids: only the people in the new export are compared, so nobody can show as not found",
              file=sys.stderr)
    rows = compare({k: old[k] for k in asked if k in old}, new, verified(args.verified))
    if not rows:
        sys.exit("none of the --ids is in the old list: pass the ids that sample printed for this list")
    report(rows)
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {args.csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
