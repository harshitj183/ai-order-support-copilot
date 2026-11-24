from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

AUDIT_HEADERS = [
    "email_id",
    "received_at",
    "from_email",
    "intent",
    "secondary_intent",
    "order_id",
    "language",
    "sentiment",
    "confidence",
    "order_found",
    "action_taken",
    "needs_human",
    "ticket_id",
    "reply_draft",
    "prompt_version",
    "processed_at",
    "error",
    "notes",
]

TICKET_HEADERS = [
    "ticket_id",
    "created_at",
    "updated_at",
    "order_id",
    "customer_email",
    "email_ids",
    "intent",
    "priority",
    "status",
    "summary",
    "notes",
]


def ensure_csv(path: Path, headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()


def reset_csv(path: Path, headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()


def read_csv_rows(path: Path, headers: list[str]) -> list[dict[str, str]]:
    ensure_csv(path, headers)
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv_rows(path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in headers})


def append_audit_row(path: Path, row: dict[str, Any]) -> None:
    rows = read_csv_rows(path, AUDIT_HEADERS)
    # Replace existing row if same email_id + prompt_version, else append
    updated = False
    for idx, existing in enumerate(rows):
        if existing.get("email_id") == row.get("email_id") and existing.get("prompt_version") == row.get("prompt_version"):
            rows[idx] = {h: str(row.get(h, "")) if row.get(h) is not None else "" for h in AUDIT_HEADERS}
            updated = True
            break
    if not updated:
        rows.append({h: str(row.get(h, "")) if row.get(h) is not None else "" for h in AUDIT_HEADERS})
    write_csv_rows(path, AUDIT_HEADERS, rows)
