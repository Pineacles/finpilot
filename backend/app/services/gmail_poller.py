"""Gmail IMAP poller for Valiant bank notifications.

Reads emails from noreply@valiant.ch, parses transaction amounts and balance,
creates pending transactions and updates account balance.

Email format:
  "Belastung von CHF 30.02 auf dem Konto main. Neuer Saldo CHF 6'170.84."
  "Gutschrift von CHF 3'500.00 auf dem Konto main. Neuer Saldo CHF 9'670.84."
"""
import re
import imaplib
import email
import logging
from datetime import datetime, date, timezone
from email.header import decode_header

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Transaction, Category
from app.models.account import Account
from app.services.settings import get_setting

logger = logging.getLogger(__name__)

# Pattern to parse Valiant notifications
VALIANT_PATTERN = re.compile(
    r"(Belastung|Gutschrift)\s+von\s+CHF\s+([\d']+\.\d{2})\s+"
    r"auf\s+dem\s+Konto\s+(\w+)\.\s+"
    r"Neuer\s+Saldo\s+CHF\s+([\d']+\.\d{2})\.",
    re.IGNORECASE,
)


def _parse_chf(s: str) -> float:
    """Parse Swiss number format: 6'170.84 -> 6170.84"""
    return float(s.replace("'", ""))


def parse_valiant_email(body: str) -> dict | None:
    """Parse a Valiant notification email body.

    Returns: {"type": "debit"|"credit", "amount": float, "account": str, "balance": float}
    """
    match = VALIANT_PATTERN.search(body)
    if not match:
        return None

    txn_type = "credit" if "gutschrift" in match.group(1).lower() else "debit"
    amount = _parse_chf(match.group(2))
    account_name = match.group(3)
    balance = _parse_chf(match.group(4))

    return {
        "type": txn_type,
        "amount": amount,
        "account": account_name,
        "balance": balance,
    }


async def poll_gmail(db: AsyncSession, user_id: str) -> dict:
    """Poll Gmail for new Valiant notifications.

    Settings needed:
      - gmail_address: email address (e.g. your-email@gmail.com)
      - gmail_app_password: 16-char app password
      - gmail_last_uid: last processed email UID (for incremental polling)

    Returns: {"new_transactions": int, "balance": float | None, "errors": list}
    """
    gmail_addr = await get_setting(db, user_id, "gmail_address")
    gmail_pass = await get_setting(db, user_id, "gmail_app_password")

    if not gmail_addr or not gmail_pass:
        return {"new_transactions": 0, "balance": None, "errors": ["Gmail not configured"]}

    last_uid = await get_setting(db, user_id, "gmail_last_uid") or "1"

    # Configurable sender filter (default: Valiant)
    sender_filter = await get_setting(db, user_id, "gmail_sender_filter")
    senders = [s.strip() for s in sender_filter.split(",") if s.strip()] if sender_filter else ["noreply@valiant.ch"]

    # Find or create bank account
    result = await db.execute(
        select(Account).where(and_(Account.user_id == user_id, Account.type == "bank"))
    )
    account = result.scalar_one_or_none()
    if not account:
        account = Account(user_id=user_id, name="Valiant Bank", type="bank", currency="CHF")
        db.add(account)
        await db.flush()

    errors = []
    new_count = 0
    latest_balance = None
    max_uid = int(last_uid)

    try:
        # Connect to Gmail IMAP
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(gmail_addr, gmail_pass)
        imap.select("INBOX")

        # Search for emails from configured senders
        # Build OR query for multiple senders
        if len(senders) == 1:
            from_query = f'FROM "{senders[0]}"'
        else:
            # IMAP OR syntax: (OR (FROM "a") (FROM "b"))
            from_query = " ".join(f'FROM "{s}"' for s in senders)
            if len(senders) > 1:
                from_query = f'OR {from_query}'

        search_query = f'({from_query} UID {int(last_uid) + 1}:*)'
        status, data = imap.uid("search", None, search_query)
        if status != "OK" or not data[0]:
            imap.logout()
            return {"new_transactions": 0, "balance": None, "errors": []}

        uids = data[0].split()
        logger.info(f"Gmail: found {len(uids)} potential new Valiant emails (UIDs from {last_uid})")

        for uid_bytes in uids:
            uid = int(uid_bytes)
            if uid <= int(last_uid):
                continue

            # Fetch email
            status, msg_data = imap.uid("fetch", str(uid), "(RFC822)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Get email date
            date_str = msg.get("Date", "")
            try:
                email_date = email.utils.parsedate_to_datetime(date_str)
                txn_date = email_date.date()
            except Exception:
                txn_date = date.today()

            # Get body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        charset = part.get_content_charset() or "utf-8"
                        body = part.get_payload(decode=True).decode(charset, errors="replace")
                        break
                    elif part.get_content_type() == "text/html" and not body:
                        charset = part.get_content_charset() or "utf-8"
                        body = part.get_payload(decode=True).decode(charset, errors="replace")
            else:
                charset = msg.get_content_charset() or "utf-8"
                body = msg.get_payload(decode=True).decode(charset, errors="replace")

            # Strip HTML tags if needed
            body = re.sub(r"<[^>]+>", " ", body)
            body = re.sub(r"\s+", " ", body).strip()

            parsed = parse_valiant_email(body)
            if not parsed:
                logger.debug(f"Gmail UID {uid}: not a transaction notification")
                if uid > max_uid:
                    max_uid = uid
                continue

            # Check dedup: same date + same amount + same minute = likely same transaction
            amount = -parsed["amount"] if parsed["type"] == "debit" else parsed["amount"]
            existing = await db.execute(
                select(Transaction).where(and_(
                    Transaction.user_id == user_id,
                    Transaction.account_id == account.id,
                    Transaction.date == txn_date,
                    Transaction.amount == amount,
                    Transaction.merchant == "Pending",
                ))
            )
            if existing.scalar_one_or_none():
                if uid > max_uid:
                    max_uid = uid
                continue

            # Create pending transaction
            txn = Transaction(
                user_id=user_id,
                account_id=account.id,
                date=txn_date,
                merchant="Pending",
                amount=amount,
                currency="CHF",
                notes=f"Email notification | {parsed['type']} CHF {parsed['amount']} | Balance: CHF {parsed['balance']}",
            )
            db.add(txn)
            new_count += 1

            latest_balance = parsed["balance"]
            if uid > max_uid:
                max_uid = uid

            logger.info(f"Gmail: {parsed['type']} CHF {parsed['amount']}, balance CHF {parsed['balance']}")

        imap.logout()

    except imaplib.IMAP4.error as e:
        errors.append(f"IMAP error: {e}")
        logger.error(f"Gmail IMAP error: {e}")
    except Exception as e:
        errors.append(f"Gmail poll error: {e}")
        logger.error(f"Gmail poll error: {e}", exc_info=True)

    # Save last processed UID
    if max_uid > int(last_uid):
        from app.services.settings import set_setting
        await set_setting(db, user_id, "gmail_last_uid", str(max_uid))

    await db.commit()

    return {
        "new_transactions": new_count,
        "balance": latest_balance,
        "errors": errors,
    }
