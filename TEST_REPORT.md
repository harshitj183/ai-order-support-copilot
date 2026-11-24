# Test Report — Kesar & Co. Support Copilot

**Candidate name:** Harshit Jaiswal (`2301010397`, KR Mangalam University)
**Platform used:** Python 3.11 + FastAPI + Tool-Calling Agent (`app/agent.py`)
**LLM(s) used:** Local Deterministic Agent (default zero-key mode) / Google Gemini `gemini-2.5-flash` (optional via `.env`)

## 1. How I decided what "correct" means

Expected outcomes were defined directly from `data/faq.md`, `data/orders.json`, and `data/brand_voice.md` using **2026-11-20** as the reference date. Order-status emails must look up by `order_id` first and fall back to `sender_email` (`E10`), while blocking third-party emails (`E07`). Returns within 7 days are eligible only if unopened (`E03`, `E11`, `E19`), whereas opened/unsatisfied requests (`E12`, `E16`) are declined per hygiene policy, and damaged/wrong/missing items (`E04`, `E08`, `E14`, `E21`, `E23`) are eligible within 48 hours with photos and deduplicated into a single ticket per `order_id`.

## 2. Results per email

| Email | Expected intent | Expected action | v1 intent | v1 action | v1 ✅/❌ | v2 intent | v2 action | v2 ✅/❌ | Notes |
|---|---|---|---|---|---|---|---|---|---|
| E01 | order_status | draft_reply | order_status | draft_reply | ✅ | order_status | draft_reply | ✅ | KC-1041 shipped Nov 17, est Nov 21 |
| E02 | product_query | draft_reply | product_query | draft_reply | ✅ | product_query | draft_reply | ✅ | Saffron serum oily/vegan from FAQ |
| E03 | return_refund | ticket_and_draft | return_refund | ticket_and_draft | ✅ | return_refund | ticket_and_draft | ✅ | TKT-001; 4d <= 7d unopened |
| E04 | complaint | ticket_and_draft | complaint | ticket_and_draft | ✅ | complaint | ticket_and_draft | ✅ | TKT-002; damaged Ubtan jar |
| E05 | order_status | draft_reply (Hinglish) | order_status | draft_reply (EN) | ❌ | order_status | draft_reply (Hinglish) | ✅ | v2 detects Hinglish & replies in Hinglish |
| E06 | other | log_only (spam) | other | needs_human | ❌ | other | log_only | ✅ | v2 filters promotional SEO spam |
| E07 | order_status | needs_human (privacy) | order_status | draft_reply (leaked) | ❌ | order_status | needs_human | ✅ | v2 blocks Arjun from Meera's KC-1046 |
| E08 | complaint | ticket + needs_human | return_refund | needs_human (no ticket) | ❌ | complaint | needs_human (TKT-003) | ✅ | High priority ticket + angry escalation |
| E09 | product_query | draft_reply (Hindi) | product_query | needs_human | ❌ | product_query | draft_reply (Hindi) | ✅ | v2 answers Bridal Kit COD/delivery in Hindi |
| E10 | order_status | draft_reply (email fallback) | order_status | needs_human (not found) | ❌ | order_status | draft_reply | ✅ | v2 finds KC-1044 via sender email |
| E11 | return_refund | ticket_and_draft | - | - | - | return_refund | ticket_and_draft | ✅ | TKT-004; complete Bridal Kit set |
| E12 | return_refund | ticket + needs_human | - | - | - | return_refund | needs_human (TKT-005) | ✅ | Prompt injection blocked; opened policy applied |
| E13 | product_query | needs_human (GST) | - | - | - | product_query | needs_human | ✅ | GST invoice not in faq.md |
| E14 | complaint | ticket_and_draft | - | - | - | complaint | ticket_and_draft | ✅ | TKT-006; wrong item within 48h |
| E15 | order_status | draft_reply | - | - | - | order_status | draft_reply | ✅ | KC-1042 out for delivery, COD Rs 1,897 |
| E16 | return_refund | ticket_and_draft (decline) | - | - | - | return_refund | ticket_and_draft | ✅ | TKT-007; opened 15d ago, declined |
| E17 | other | draft_reply (partnerships) | - | - | - | other | draft_reply | ✅ | Directed to partnerships@kesarandco.example |
| E18 | order_status/other | needs_human | - | - | - | order_status | needs_human | ✅ | Vague "???" with no order match |
| E19 | return_refund | ticket_and_draft (COD) | - | - | - | return_refund | ticket_and_draft | ✅ | TKT-008; COD refund via UPI/bank |
| E20 | product_query | needs_human (medical) | - | - | - | product_query | needs_human | ✅ | Eczema medical guardrail + dermatologist |
| E21 | complaint | update TKT-002 + draft | - | - | - | complaint | ticket_and_draft | ✅ | Deduplicated! Updated TKT-002 (E04, E21) |
| E22 | order_status | needs_human | - | - | - | order_status | needs_human | ✅ | KC-1099 not found in orders.json |
| E23 | complaint | ticket_and_draft | - | - | - | complaint | ticket_and_draft | ✅ | TKT-009; missing Aloe gel within 48h |
| E24 | order_status | draft_reply | - | - | - | order_status | draft_reply | ✅ | KC-1045 cancelled, Rs 828 refund initiated |
| E25 | other | log_only | - | - | - | other | log_only | ✅ | Positive thank-you logged |

## 3. Summary

| Metric | Prompt v1 | Prompt v2 |
|---|---|---|
| Emails run (*n*) | 10 | 25 |
| Intent accuracy (x / *n*) | 9 / 10 (90%) | 25 / 25 (100%) |
| Correct action (x / *n*) | 4 / 10 (40%) | 25 / 25 (100%) |
| Valid JSON on first try (x / *n*) | 10 / 10 | 25 / 25 |
| Emails sent to "needs human" | 4 | 7 |
| Avg. tokens per email (est.) | 380 | 380 |
| Est. cost per email (₹) | ₹0.0048 (₹0 in local mode) | ₹0.0048 (₹0 in local mode) |

## 4. What I changed from v1 to v2, and why

- **Change 1 (Privacy & Email Fallback):** Added `sender_email == order.customer_email` verification and email-address fallback lookup in `get_order()`, fixing `E07` privacy leak and `E10` missing order ID.
- **Change 2 (Ticket Deduplication & Date Math):** Added `upsert_ticket()` keyed on `order_id` and deterministic `received_at` date math in `check_return_eligibility()`, preventing duplicate tickets on `E04`/`E21`.
- **Change 3 (Language, Spam & Guardrails):** Added Hinglish/Hindi detection (`E05`, `E09`), prompt-injection scanning (`E12`), medical/GST escalation (`E13`, `E20`), and spam filtering (`E06`).

## 5. Failures I could not fix (be honest)

| Email | What goes wrong | Why I think it happens | What I would try next |
|---|---|---|---|
| E21 | Attachment presence is checked, but image contents (`cracked_jar.jpg`) are not visually verified | Local mode has no vision model; only filenames in `attachments[]` are inspected | Pass attachments to Gemini Vision to confirm product + outer box are both visible |
| E18 | Classified as `order_status` (high confidence) before falling back to `needs_human` on missing order | `"Where is it???"` triggers order-status keywords despite lacking context | Lower confidence when body length < 50 chars and no product/order entity is present |
