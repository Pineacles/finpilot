"""camt.053 XML parser for Swiss bank statements (ISO 20022).

Handles Valiant Bank's camt.053.001.04 format where:
- Card payments (CCRD/POSD): Cdtr is the account owner, real merchant is in RmtInf/Ustrd
- TWINT: info is in AddtlTxInf (e.g. "TWINT Belastung Migros 0400001234567")
- E-banking (ICDT): Cdtr has the real creditor name + address
- Salary (RCDT/SALA): Dbtr has the employer name
- Standing orders (ICDT/STDO): Cdtr has the real creditor
"""
import re
import xml.etree.ElementTree as ET
from datetime import date


def _find_ns(root: ET.Element) -> str:
    tag = root.tag
    if "{" in tag:
        return tag.split("}")[0].strip("{")
    return ""


def _f(el: ET.Element, path: str, ns: str) -> ET.Element | None:
    """Find element with namespace."""
    if ns:
        nsed = "/".join(f"{{{ns}}}{p}" for p in path.split("/"))
        return el.find(nsed)
    return el.find(path)


def _fa(el: ET.Element, path: str, ns: str) -> list[ET.Element]:
    if ns:
        nsed = "/".join(f"{{{ns}}}{p}" for p in path.split("/"))
        return el.findall(nsed)
    return el.findall(path)


def _t(el: ET.Element | None, path: str, ns: str) -> str:
    if el is None:
        return ""
    found = _f(el, path, ns)
    return found.text.strip() if found is not None and found.text else ""


def parse_camt053(content: str, owner_name: str = "") -> list[dict]:
    """Parse camt.053 XML. owner_name is used to detect self-referencing entries."""
    root = ET.fromstring(content)
    ns = _find_ns(root)

    # Detect account owner from the file
    stmt = _f(root, "BkToCstmrStmt/Stmt", ns)
    if stmt is None:
        stmts = _fa(root, "BkToCstmrStmt/Stmt", ns)
        stmt = stmts[0] if stmts else None
    if stmt is None:
        return []

    if not owner_name:
        owner_name = _t(stmt, "Acct/Ownr/Nm", ns)
    owner_lower = owner_name.lower()
    currency = _t(stmt, "Acct/Ccy", ns) or "CHF"

    transactions = []
    entries = _fa(stmt, "Ntry", ns)

    for ntry in entries:
        # Amount and direction
        amt_el = _f(ntry, "Amt", ns)
        if amt_el is None or not amt_el.text:
            continue
        amount = float(amt_el.text)
        cdt_dbt = _t(ntry, "CdtDbtInd", ns)
        if cdt_dbt == "DBIT":
            amount = -abs(amount)
        else:
            amount = abs(amount)

        # Dates
        booking_date_str = _t(ntry, "BookgDt/Dt", ns)
        value_date_str = _t(ntry, "ValDt/Dt", ns)
        try:
            txn_date = date.fromisoformat(booking_date_str) if booking_date_str else date.today()
        except ValueError:
            txn_date = date.today()

        # Reference for dedup
        acct_svcr_ref = _t(ntry, "AcctSvcrRef", ns)

        # Bank transaction code (tells us the type)
        domn_cd = _t(ntry, "BkTxCd/Domn/Cd", ns)  # PMNT
        fmly_cd = _t(ntry, "BkTxCd/Domn/Fmly/Cd", ns)  # CCRD, ICDT, RCDT
        subfmly_cd = _t(ntry, "BkTxCd/Domn/Fmly/SubFmlyCd", ns)  # POSD, SALA, STDO, OTHR

        # Entry-level additional info (fallback description)
        addtl_ntry_inf = _t(ntry, "AddtlNtryInf", ns)

        # Process transaction details
        tx_details = _fa(ntry, "NtryDtls/TxDtls", ns)

        if tx_details:
            for txd in tx_details:
                txn = _parse_tx_detail(txd, ns, txn_date, currency, cdt_dbt,
                                        acct_svcr_ref, owner_lower,
                                        fmly_cd, subfmly_cd, addtl_ntry_inf)

                # Individual amount if present
                ind_amt = _f(txd, "Amt", ns)
                if ind_amt is not None and ind_amt.text:
                    txn_amount = float(ind_amt.text)
                    if cdt_dbt == "DBIT":
                        txn_amount = -abs(txn_amount)
                    else:
                        txn_amount = abs(txn_amount)
                    txn["amount"] = txn_amount
                else:
                    txn["amount"] = amount

                transactions.append(txn)
        else:
            # No detail: use entry-level info
            transactions.append({
                "date": txn_date,
                "description": addtl_ntry_inf or f"Transaction {abs(amount)} {currency}",
                "merchant": addtl_ntry_inf or "Unknown",
                "amount": amount,
                "currency": currency,
                "reference": acct_svcr_ref,
                "counterparty": "",
                "payment_type": fmly_cd,
                "payment_subtype": subfmly_cd,
            })

    return transactions


def _parse_tx_detail(txd: ET.Element, ns: str, txn_date: date, currency: str,
                     cdt_dbt: str, entry_ref: str, owner_lower: str,
                     fmly_cd: str, subfmly_cd: str, addtl_ntry_inf: str) -> dict:
    """Parse a single TxDtls element with smart merchant extraction."""

    # Get all text fields
    cdtr_name = _t(txd, "RltdPties/Cdtr/Nm", ns)
    dbtr_name = _t(txd, "RltdPties/Dbtr/Nm", ns)
    remittance = _t(txd, "RmtInf/Ustrd", ns)
    addtl_tx_inf = _t(txd, "AddtlTxInf", ns)
    ref = _t(txd, "Refs/AcctSvcrRef", ns) or _t(txd, "Refs/EndToEndId", ns) or entry_ref

    # Creditor address (for e-banking payments)
    cdtr_addr_parts = []
    cdtr_addr_el = _f(txd, "RltdPties/Cdtr/PstlAdr", ns)
    if cdtr_addr_el is not None:
        for line in _fa(cdtr_addr_el, "AdrLine", ns):
            if line.text:
                cdtr_addr_parts.append(line.text.strip())
    cdtr_address = ", ".join(cdtr_addr_parts)

    # Determine the real counterparty and description
    # The key insight: for card payments, Cdtr is the account owner
    # The real merchant is in RmtInf/Ustrd or AddtlTxInf

    is_cdtr_self = _is_self(cdtr_name, owner_lower)
    is_dbtr_self = _is_self(dbtr_name, owner_lower)

    merchant = ""
    description = ""

    if fmly_cd == "CCRD":
        # Card payment: merchant is in remittance info
        description = remittance or addtl_tx_inf or addtl_ntry_inf
        merchant = _extract_merchant_from_text(description)

    elif fmly_cd == "ICDT":
        # Outgoing credit transfer (e-banking, standing order)
        if not is_cdtr_self and cdtr_name and cdtr_name != "NOTPROVIDED":
            merchant = cdtr_name
            description = f"{cdtr_name}" + (f" - {remittance}" if remittance else "")
        else:
            description = addtl_tx_inf or remittance or addtl_ntry_inf
            merchant = _extract_merchant_from_text(description)

    elif fmly_cd == "RCDT":
        # Incoming credit (salary, transfers received)
        if not is_dbtr_self and dbtr_name and dbtr_name != "NOTPROVIDED":
            merchant = dbtr_name
            description = f"{dbtr_name}" + (f" - {remittance}" if remittance else "")
        elif not is_cdtr_self and cdtr_name and cdtr_name != "NOTPROVIDED":
            merchant = cdtr_name
            description = f"{cdtr_name}" + (f" - {remittance}" if remittance else "")
        else:
            description = addtl_tx_inf or remittance or addtl_ntry_inf
            merchant = _extract_merchant_from_text(description)

    else:
        # Other: use whatever info is available
        description = addtl_tx_inf or remittance or addtl_ntry_inf

        # TWINT: Cdtr is "TWINT" but real merchant is in AddtlTxInf
        is_twint = (
            cdtr_name and "twint" in cdtr_name.lower()
            or (description and "twint" in description.lower())
        )
        if is_twint and description:
            merchant = _extract_merchant_from_text(description)
        elif not is_cdtr_self and cdtr_name and cdtr_name != "NOTPROVIDED" and not is_twint:
            merchant = cdtr_name
        elif not is_dbtr_self and dbtr_name and dbtr_name != "NOTPROVIDED":
            merchant = dbtr_name
        else:
            merchant = _extract_merchant_from_text(description)

    if not merchant:
        merchant = _extract_merchant_from_text(description) or "Unknown"
    if not description:
        description = merchant

    return {
        "date": txn_date,
        "description": description,
        "merchant": merchant,
        "amount": 0,  # Set by caller
        "currency": currency,
        "reference": ref,
        "counterparty": merchant,
        "counterparty_address": cdtr_address if fmly_cd == "ICDT" else "",
        "payment_type": fmly_cd,
        "payment_subtype": subfmly_cd,
    }


def _is_self(name: str, owner_lower: str) -> bool:
    """Check if a name is the account owner or NOTPROVIDED."""
    if not name or name == "NOTPROVIDED":
        return True
    return name.lower() == owner_lower


def _extract_merchant_from_text(text: str) -> str:
    """Extract merchant name from Swiss bank description text.

    Examples:
    - "Zahlung - Lidl Emmenbruecke - 30.12.2023 14:32 - Karten-Nr. 535445******3303"
      → "Lidl Emmenbruecke"
    - "TWINT Belastung Migros Willisau 0400001234567"
      → "Migros Willisau"
    - "- PAYPAL *TWITCHINTER - 28.12.2023 00:00 - Karten-Nr. 535445******3303"
      → "PAYPAL *TWITCHINTER"
    """
    if not text:
        return ""

    t = text.strip()

    # Strip leading "- " or "Zahlung - "
    t = re.sub(r"^(?:Zahlung\s*)?-\s*", "", t, flags=re.IGNORECASE)

    # Strip TWINT prefix, keep merchant
    twint_match = re.match(r"TWINT\s+(?:Belastung|Gutschrift)\s+(.+)", t, re.IGNORECASE)
    if twint_match:
        t = twint_match.group(1)
        # Strip phone number and reference at end
        t = re.sub(r"\s*\+\d{10,}.*$", "", t)
        t = re.sub(r"\s*\d{13,}.*$", "", t)
        return t.strip().rstrip(",")

    # Strip date/time pattern " - DD.MM.YYYY HH:MM" and everything after
    t = re.sub(r"\s*-\s*\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}.*$", "", t)

    # Strip card number
    t = re.sub(r"\s*-?\s*Karten?-?Nr\.?\s*\d+\*+\d+.*$", "", t, flags=re.IGNORECASE)

    # Strip trailing reference numbers
    t = re.sub(r"\s+\d{10,}$", "", t)

    return t.strip().rstrip(",")
