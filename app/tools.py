from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.storage import TICKET_HEADERS, read_csv_rows, write_csv_rows

BASE_DIR = Path(__file__).resolve().parent.parent
ORDERS_PATH = BASE_DIR / "data" / "orders.json"
FAQ_PATH = BASE_DIR / "data" / "faq.md"


def load_orders() -> list[dict[str, Any]]:
    with ORDERS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("orders", [])


def get_order(order_id: str | None, sender_email: str, enforce_privacy: bool = True) -> dict[str, Any]:
    """Tool 1: Look up order by order_id first, then fall back to sender_email.
    Enforces privacy: never expose order details if sender_email != order.customer_email.
    """
    orders = load_orders()
    matched: dict[str, Any] | None = None
    lookup_method = "none"

    if order_id:
        norm_id = order_id.strip().upper()
        for o in orders:
            if o["order_id"].upper() == norm_id:
                matched = o
                lookup_method = "order_id"
                break

    if matched is None and sender_email:
        norm_email = sender_email.strip().lower()
        for o in orders:
            if o["customer_email"].strip().lower() == norm_email:
                matched = o
                lookup_method = "email_fallback"
                break

    if matched is None:
        return {
            "found": False,
            "privacy_blocked": False,
            "lookup_method": lookup_method,
            "order": None,
        }

    if enforce_privacy and sender_email.strip().lower() != matched["customer_email"].strip().lower():
        return {
            "found": True,
            "privacy_blocked": True,
            "lookup_method": lookup_method,
            "order": None,
            "reason": "Sender email does not match order customer_email.",
        }

    return {
        "found": True,
        "privacy_blocked": False,
        "lookup_method": lookup_method,
        "order": matched,
    }


def search_faq(query: str) -> dict[str, Any]:
    """Tool 2: Search data/faq.md sections and product table for grounded answers."""
    text = FAQ_PATH.read_text(encoding="utf-8")
    sections = re.split(r"(?=^##\s+)", text, flags=re.MULTILINE)
    q_lower = query.lower()
    tokens = [t for t in re.findall(r"[a-z0-9]+", q_lower) if len(t) > 2]

    scored: list[tuple[int, str, str]] = []
    for sec in sections:
        sec_clean = sec.strip()
        if not sec_clean.startswith("##"):
            continue
        first_line = sec_clean.splitlines()[0].lstrip("# ").strip()
        sec_lower = sec_clean.lower()
        score = sum(1 for tok in tokens if tok in sec_lower)
        # Boost exact product or policy keywords
        boost_terms = [
            "saffron", "kumkumadi", "ubtan", "rose water", "toner", "bhringraj",
            "sandalwood", "aloe", "bridal", "cod", "shipping", "return", "refund",
            "damaged", "leaking", "wrong", "missing", "eczema", "vegan", "oily",
            "cancel", "partnership", "collab", "shelf life", "cruelty"
        ]
        for term in boost_terms:
            if term in q_lower and term in sec_lower:
                score += 3
        if score > 0:
            scored.append((score, first_line, sec_clean))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:2]
    return {
        "matched": len(top) > 0,
        "sections": [{"title": t, "score": s, "content": c} for s, t, c in top],
    }


def check_return_eligibility(
    order: dict[str, Any],
    received_at: str,
    issue_type: str,
    has_photos: bool = False,
) -> dict[str, Any]:
    """Tool 3: Deterministic return/refund eligibility using email received_at timestamp."""
    email_dt = datetime.fromisoformat(received_at).date()
    status = order.get("status", "")
    payment_method = order.get("payment_method", "prepaid")

    if status != "delivered" or not order.get("delivered_date"):
        return {
            "eligible": False,
            "reason": f"Order status is '{status}' (not yet delivered).",
            "policy": "pre_delivery",
            "payment_method": payment_method,
        }

    delivered_dt = datetime.fromisoformat(order["delivered_date"]).date()
    days_since_delivery = (email_dt - delivered_dt).days

    if issue_type in {"damaged", "leaking", "wrong_item", "missing_item"}:
        within_48h = days_since_delivery <= 2
        return {
            "eligible": within_48h,
            "days_since_delivery": days_since_delivery,
            "policy": "damaged_wrong_missing_48h",
            "requires_photos": not has_photos,
            "payment_method": payment_method,
            "reason": (
                "Reported within 48 hours of delivery; eligible for free replacement or full refund."
                if within_48h
                else "Reported more than 48 hours after delivery; requires human review."
            ),
        }

    if issue_type == "opened_unsatisfied":
        return {
            "eligible": False,
            "days_since_delivery": days_since_delivery,
            "policy": "hygiene_no_opened_returns",
            "payment_method": payment_method,
            "reason": "Opened or used products cannot be returned for hygiene reasons (including didn't suit / no results).",
        }

    # Standard unopened return (within 7 days of delivery)
    within_7d = days_since_delivery <= 7
    is_kit = any("kit" in item["name"].lower() for item in order.get("items", []))
    return {
        "eligible": within_7d,
        "days_since_delivery": days_since_delivery,
        "policy": "standard_7d_unopened",
        "is_combo_kit": is_kit,
        "payment_method": payment_method,
        "reason": (
            f"Delivered {days_since_delivery} day(s) ago (within 7-day window); eligible if unused, unopened, and seal intact."
            if within_7d
            else f"Delivered {days_since_delivery} day(s) ago (past 7-day return window)."
        ),
    }


def upsert_ticket(
    tickets_path: Path,
    order_id: str | None,
    customer_email: str,
    email_id: str,
    received_at: str,
    intent: str,
    priority: str,
    summary: str,
    note: str,
) -> dict[str, Any]:
    """Tool 4: Create a support ticket or update an existing open ticket for the same order_id."""
    rows = read_csv_rows(tickets_path, TICKET_HEADERS)
    norm_order = (order_id or "").strip().upper()

    if norm_order:
        for row in rows:
            if row.get("order_id", "").strip().upper() == norm_order and row.get("status", "") in {"open", "in_progress"}:
                existing_ids = [x.strip() for x in row.get("email_ids", "").split(",") if x.strip()]
                if email_id not in existing_ids:
                    existing_ids.append(email_id)
                row["email_ids"] = ", ".join(existing_ids)
                row["updated_at"] = received_at
                # Escalate priority if new email is higher
                if priority == "High":
                    row["priority"] = "High"
                prev_notes = row.get("notes", "").strip()
                row["notes"] = f"{prev_notes} | [{email_id}] {note}".strip(" |")
                write_csv_rows(tickets_path, TICKET_HEADERS, rows)
                return {"action": "updated", "ticket_id": row["ticket_id"]}

    next_num = len(rows) + 1
    ticket_id = f"TKT-{next_num:03d}"
    new_row = {
        "ticket_id": ticket_id,
        "created_at": received_at,
        "updated_at": received_at,
        "order_id": norm_order or "N/A",
        "customer_email": customer_email,
        "email_ids": email_id,
        "intent": intent,
        "priority": priority,
        "status": "open",
        "summary": summary[:200],
        "notes": f"[{email_id}] {note}",
    }
    rows.append(new_row)
    write_csv_rows(tickets_path, TICKET_HEADERS, rows)
    return {"action": "created", "ticket_id": ticket_id}
