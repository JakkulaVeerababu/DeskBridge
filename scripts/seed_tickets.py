"""
seed_tickets.py – Creates 12 FAKE tickets in your Freshdesk trial account.

Purpose: populate a fresh trial so you have real data to run smoke_test.py
against. The descriptions deliberately contain fake emails and phone numbers
so you can verify PII masking is working.

This script is NOT part of the connector. The connector is read-only.

Usage:
    cp .env.example .env    # fill in FRESHDESK_DOMAIN and FRESHDESK_API_KEY
    python scripts/seed_tickets.py
"""
import os
import random
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

DOMAIN = os.getenv("FRESHDESK_DOMAIN", "")
API_KEY = os.getenv("FRESHDESK_API_KEY", "")

if not DOMAIN or not API_KEY:
    print("ERROR: set FRESHDESK_DOMAIN and FRESHDESK_API_KEY in .env", file=sys.stderr)
    sys.exit(1)

# Fake ticket templates – all data is fictional
TEMPLATES = [
    ("Refund not received for order #1042", "refund",
     "My order was cancelled but the refund hasn't appeared. "
     "I paid via UPI. Contact: fake.user01@example.com / 9876540001"),
    ("Payment link expired before customer could pay", "payments",
     "The payment link I sent to my customer expired in under 10 minutes. "
     "Customer email: fake.user02@example.com, phone 9876540002"),
    ("Settlement delayed by 2 business days", "settlement",
     "Expected settlement on Monday but funds arrived Wednesday. "
     "Merchant: fake.user03@example.com"),
    ("Need GST invoice copy for August", "invoice",
     "Please resend the August invoice to fake.user04@example.com. "
     "Callback: +91 98765 40004"),
    ("Webhook not firing on payment.captured event", "integration",
     "Our integration at fake.user05@example.com stopped receiving webhooks "
     "after the v2 migration. Phone 9876540005"),
    ("Autopay mandate failed twice this month", "autopay",
     "Customer fake.user06@example.com has two failed autopay attempts. "
     "Mobile: 9876540006. Please advise next steps."),
    ("Dashboard showing wrong currency for USD transactions", "dashboard",
     "All USD amounts show as INR. Contact fake.user07@example.com"),
    ("API returning 422 on recurring charge", "api",
     "POST /recurring/charges returns 422. Raised by fake.user08@example.com. "
     "ph: 9876540008"),
    ("Payout to ICICI account bouncing", "payout",
     "Three consecutive payouts to our ICICI account have bounced. "
     "Email fake.user09@example.com for IFSC details."),
    ("QR code payments not reflecting in reports", "qr-code",
     "QR payments from yesterday are missing in the daily report. "
     "Reporter: fake.user10@example.com / 9876540010"),
    ("Duplicate charge on the same order ID", "duplicate",
     "Order #2087 was charged twice. Customer fake.user11@example.com. "
     "Cell: 9876540011"),
    ("International card payments being declined", "international",
     "All Visa international cards are failing at checkout. "
     "Contact fake.user12@example.com, ph 9876540012"),
]


def main() -> None:
    created = 0
    with httpx.Client(
        base_url=f"https://{DOMAIN}.freshdesk.com/api/v2",
        auth=(API_KEY, "X"),
        timeout=15.0,
    ) as client:
        for i, (subject, tag, description) in enumerate(TEMPLATES):
            payload = {
                "subject": subject,
                "description": description,
                "email": f"fake.user{i + 1:02d}@example.com",
                "priority": random.choice([1, 2, 3, 4]),
                "status": random.choice([2, 3, 4]),
                "tags": [tag],
            }
            resp = client.post("/tickets", json=payload)
            if resp.status_code == 201:
                tid = resp.json().get("id", "?")
                print(f"  [OK] #{tid} – {subject}")
                created += 1
            else:
                print(f"  [FAIL {resp.status_code}] {subject}: {resp.text[:100]}")
            time.sleep(1)   # stay well under the rate limit

    print(f"\nDone. {created}/{len(TEMPLATES)} tickets created in {DOMAIN}.freshdesk.com")


if __name__ == "__main__":
    main()
