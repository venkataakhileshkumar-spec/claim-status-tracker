"""
Claim Status Tracker
--------------------
A simple health-insurance claim tracker.
- Stores claims and their full status history in SQLite
- Enforces valid status transitions (e.g. you cannot go from DENIED to PAID)
- Command-line interface, standard library only (Python 3.8+)

Usage examples:
    python claim_tracker.py demo                       # load sample data
    python claim_tracker.py add --member M1001 --provider P2001 --amount 1500 --service 2026-09-15
    python claim_tracker.py update CLM-0001 IN_REVIEW --note "Sent to clinical review"
    python claim_tracker.py show CLM-0001
    python claim_tracker.py list --status PENDED
    python claim_tracker.py report
"""

import argparse
import sqlite3
import sys
from datetime import datetime

DB_FILE = "claims.db"

# ---------------------------------------------------------------------------
# Status workflow: current status -> statuses it is allowed to move to
# ---------------------------------------------------------------------------
TRANSITIONS = {
    "SUBMITTED": ["RECEIVED", "DENIED"],
    "RECEIVED": ["IN_REVIEW", "DENIED"],
    "IN_REVIEW": ["PENDED", "APPROVED", "DENIED"],
    "PENDED": ["IN_REVIEW", "DENIED"],      # pended = waiting for more info
    "APPROVED": ["PAID"],
    "DENIED": ["APPEALED", "CLOSED"],
    "APPEALED": ["IN_REVIEW", "CLOSED"],
    "PAID": ["CLOSED"],
    "CLOSED": [],
}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS claims (
                claim_id     TEXT PRIMARY KEY,
                member_id    TEXT NOT NULL,
                provider_id  TEXT NOT NULL,
                service_date TEXT NOT NULL,
                amount       REAL NOT NULL CHECK (amount > 0),
                status       TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS claim_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id    TEXT NOT NULL REFERENCES claims(claim_id),
                old_status  TEXT,
                new_status  TEXT NOT NULL,
                note        TEXT,
                changed_at  TEXT NOT NULL
            );
            """
        )


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def next_claim_id(conn):
    row = conn.execute("SELECT COUNT(*) AS c FROM claims").fetchone()
    return f"CLM-{row['c'] + 1:04d}"


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------
def add_claim(member, provider, amount, service_date):
    try:
        datetime.strptime(service_date, "%Y-%m-%d")
    except ValueError:
        sys.exit("Error: service date must be in YYYY-MM-DD format.")
    if amount <= 0:
        sys.exit("Error: amount must be greater than zero.")

    with get_conn() as conn:
        claim_id = next_claim_id(conn)
        ts = now()
        conn.execute(
            "INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (claim_id, member, provider, service_date, amount, "SUBMITTED", ts, ts),
        )
        conn.execute(
            "INSERT INTO claim_history (claim_id, old_status, new_status, note, changed_at) "
            "VALUES (?, NULL, 'SUBMITTED', 'Claim submitted', ?)",
            (claim_id, ts),
        )
    print(f"Claim {claim_id} created with status SUBMITTED.")
    return claim_id


def update_status(claim_id, new_status, note=""):
    new_status = new_status.upper()
    if new_status not in TRANSITIONS:
        sys.exit(f"Error: unknown status '{new_status}'. Valid: {', '.join(TRANSITIONS)}")

    with get_conn() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        if not claim:
            sys.exit(f"Error: claim {claim_id} not found.")

        current = claim["status"]
        allowed = TRANSITIONS[current]
        if new_status not in allowed:
            options = ", ".join(allowed) if allowed else "none (final status)"
            sys.exit(f"Error: cannot move {current} -> {new_status}. Allowed next: {options}")

        ts = now()
        conn.execute(
            "UPDATE claims SET status = ?, updated_at = ? WHERE claim_id = ?",
            (new_status, ts, claim_id),
        )
        conn.execute(
            "INSERT INTO claim_history (claim_id, old_status, new_status, note, changed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (claim_id, current, new_status, note, ts),
        )
    print(f"{claim_id}: {current} -> {new_status}")


def show_claim(claim_id):
    with get_conn() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        if not claim:
            sys.exit(f"Error: claim {claim_id} not found.")
        history = conn.execute(
            "SELECT * FROM claim_history WHERE claim_id = ? ORDER BY id", (claim_id,)
        ).fetchall()

    print(f"\nClaim ID     : {claim['claim_id']}")
    print(f"Member       : {claim['member_id']}")
    print(f"Provider     : {claim['provider_id']}")
    print(f"Service Date : {claim['service_date']}")
    print(f"Billed Amount: ${claim['amount']:,.2f}")
    print(f"Status       : {claim['status']}")
    print(f"Last Updated : {claim['updated_at']}")
    print("\nStatus History:")
    for h in history:
        old = h["old_status"] or "-"
        note = f"  ({h['note']})" if h["note"] else ""
        print(f"  {h['changed_at']}  {old:>10} -> {h['new_status']:<10}{note}")
    print()


def list_claims(status=None, member=None):
    query, params = "SELECT * FROM claims WHERE 1=1", []
    if status:
        query += " AND status = ?"
        params.append(status.upper())
    if member:
        query += " AND member_id = ?"
        params.append(member)
    query += " ORDER BY claim_id"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        print("No claims found.")
        return
    print(f"\n{'CLAIM':<10}{'MEMBER':<9}{'PROVIDER':<10}{'SERVICE DATE':<14}{'AMOUNT':>12}  STATUS")
    print("-" * 68)
    for r in rows:
        print(
            f"{r['claim_id']:<10}{r['member_id']:<9}{r['provider_id']:<10}"
            f"{r['service_date']:<14}{r['amount']:>12,.2f}  {r['status']}"
        )
    print(f"\nTotal: {len(rows)} claim(s)\n")


def report():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS cnt, SUM(amount) AS total "
            "FROM claims GROUP BY status ORDER BY cnt DESC"
        ).fetchall()
    if not rows:
        print("No claims in the system.")
        return
    print(f"\n{'STATUS':<12}{'COUNT':>6}{'TOTAL BILLED':>16}")
    print("-" * 34)
    for r in rows:
        print(f"{r['status']:<12}{r['cnt']:>6}{r['total']:>16,.2f}")
    print(f"{'ALL':<12}{sum(r['cnt'] for r in rows):>6}{sum(r['total'] for r in rows):>16,.2f}\n")


def load_demo():
    samples = [
        ("M1001", "P2001", 1500.00, "2026-09-10"),
        ("M1002", "P2002", 320.50, "2026-09-12"),
        ("M1003", "P2001", 8400.00, "2026-09-18"),
        ("M1001", "P2003", 95.00, "2026-09-25"),
    ]
    ids = [add_claim(*s) for s in samples]
    update_status(ids[0], "RECEIVED")
    update_status(ids[0], "IN_REVIEW")
    update_status(ids[0], "APPROVED", "Within plan limits")
    update_status(ids[0], "PAID", "Check #88421")
    update_status(ids[1], "RECEIVED")
    update_status(ids[1], "DENIED", "Service not covered")
    update_status(ids[2], "RECEIVED")
    update_status(ids[2], "IN_REVIEW")
    update_status(ids[2], "PENDED", "Awaiting medical records")
    print("\nDemo data loaded. Try: python claim_tracker.py list")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(description="Health Insurance Claim Status Tracker")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add", help="Submit a new claim")
    a.add_argument("--member", required=True)
    a.add_argument("--provider", required=True)
    a.add_argument("--amount", required=True, type=float)
    a.add_argument("--service", required=True, help="Service date YYYY-MM-DD")

    u = sub.add_parser("update", help="Change a claim's status")
    u.add_argument("claim_id")
    u.add_argument("status")
    u.add_argument("--note", default="")

    s = sub.add_parser("show", help="Show one claim with history")
    s.add_argument("claim_id")

    l = sub.add_parser("list", help="List claims")
    l.add_argument("--status")
    l.add_argument("--member")

    sub.add_parser("report", help="Summary by status")
    sub.add_parser("demo", help="Load sample data")
    return p


def main():
    init_db()
    args = build_parser().parse_args()
    if args.command == "add":
        add_claim(args.member, args.provider, args.amount, args.service)
    elif args.command == "update":
        update_status(args.claim_id, args.status, args.note)
    elif args.command == "show":
        show_claim(args.claim_id)
    elif args.command == "list":
        list_claims(args.status, args.member)
    elif args.command == "report":
        report()
    elif args.command == "demo":
        load_demo()


if __name__ == "__main__":
    main()
