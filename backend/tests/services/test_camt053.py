"""camt.053 XML parser (ISO 20022) — pure function, no DB.

Exercises app.services.camt053.parse_camt053 directly against a minimal
synthetic (unnamespaced) camt.053 document covering the four transaction
shapes the parser special-cases: card payment (CCRD/POSD), TWINT (no
Fmly code match -> else branch), e-banking/standing order (ICDT), and
salary (RCDT/SALA).
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.camt053 import parse_camt053


def _camt053_doc() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Document>
  <BkToCstmrStmt>
    <Stmt>
      <Acct>
        <Ownr><Nm>Test User</Nm></Ownr>
        <Ccy>CHF</Ccy>
      </Acct>
      <Ntry>
        <Amt>25.90</Amt>
        <CdtDbtInd>DBIT</CdtDbtInd>
        <BookgDt><Dt>2026-03-15</Dt></BookgDt>
        <ValDt><Dt>2026-03-15</Dt></ValDt>
        <AcctSvcrRef>REF-CARD-1</AcctSvcrRef>
        <BkTxCd>
          <Domn>
            <Cd>PMNT</Cd>
            <Fmly>
              <Cd>CCRD</Cd>
              <SubFmlyCd>POSD</SubFmlyCd>
            </Fmly>
          </Domn>
        </BkTxCd>
        <NtryDtls>
          <TxDtls>
            <Refs><AcctSvcrRef>REF-CARD-1</AcctSvcrRef></Refs>
            <RmtInf><Ustrd>Zahlung - Migros Zuerich - 15.03.2026 12:00 - Karten-Nr. 1234******5678</Ustrd></RmtInf>
          </TxDtls>
        </NtryDtls>
      </Ntry>
      <Ntry>
        <Amt>42.50</Amt>
        <CdtDbtInd>DBIT</CdtDbtInd>
        <BookgDt><Dt>2026-03-16</Dt></BookgDt>
        <ValDt><Dt>2026-03-16</Dt></ValDt>
        <AcctSvcrRef>REF-TWINT-1</AcctSvcrRef>
        <BkTxCd>
          <Domn>
            <Cd>PMNT</Cd>
          </Domn>
        </BkTxCd>
        <NtryDtls>
          <TxDtls>
            <Refs><AcctSvcrRef>REF-TWINT-1</AcctSvcrRef></Refs>
            <RltdPties>
              <Cdtr><Nm>TWINT</Nm></Cdtr>
            </RltdPties>
            <AddtlTxInf>TWINT Belastung Coop Bern 0791234567890</AddtlTxInf>
          </TxDtls>
        </NtryDtls>
      </Ntry>
      <Ntry>
        <Amt>89.00</Amt>
        <CdtDbtInd>DBIT</CdtDbtInd>
        <BookgDt><Dt>2026-03-20</Dt></BookgDt>
        <ValDt><Dt>2026-03-20</Dt></ValDt>
        <AcctSvcrRef>REF-ICDT-1</AcctSvcrRef>
        <BkTxCd>
          <Domn>
            <Cd>PMNT</Cd>
            <Fmly>
              <Cd>ICDT</Cd>
              <SubFmlyCd>STDO</SubFmlyCd>
            </Fmly>
          </Domn>
        </BkTxCd>
        <NtryDtls>
          <TxDtls>
            <Refs><AcctSvcrRef>REF-ICDT-1</AcctSvcrRef></Refs>
            <RltdPties>
              <Cdtr><Nm>Swisscom AG</Nm></Cdtr>
            </RltdPties>
            <RmtInf><Ustrd>Rechnung 2026-03</Ustrd></RmtInf>
          </TxDtls>
        </NtryDtls>
      </Ntry>
      <Ntry>
        <Amt>6500.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <BookgDt><Dt>2026-03-25</Dt></BookgDt>
        <ValDt><Dt>2026-03-25</Dt></ValDt>
        <AcctSvcrRef>REF-SALA-1</AcctSvcrRef>
        <BkTxCd>
          <Domn>
            <Cd>PMNT</Cd>
            <Fmly>
              <Cd>RCDT</Cd>
              <SubFmlyCd>SALA</SubFmlyCd>
            </Fmly>
          </Domn>
        </BkTxCd>
        <NtryDtls>
          <TxDtls>
            <Refs><AcctSvcrRef>REF-SALA-1</AcctSvcrRef></Refs>
            <RltdPties>
              <Dbtr><Nm>Acme Corp AG</Nm></Dbtr>
            </RltdPties>
          </TxDtls>
        </NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>"""


def test_parse_camt053_returns_four_entries_in_order():
    txns = parse_camt053(_camt053_doc())
    assert len(txns) == 4
    for t in txns:
        assert set(["date", "description", "merchant", "amount", "currency",
                     "reference", "counterparty", "payment_type", "payment_subtype"]).issubset(t.keys())
        assert t["currency"] == "CHF"


def test_card_payment_merchant_extracted_without_date_or_card_suffix():
    txns = parse_camt053(_camt053_doc())
    card = txns[0]
    assert card["merchant"] == "Migros Zuerich"
    assert "Karten" not in card["merchant"]
    assert "15.03.2026" not in card["merchant"]
    assert card["amount"] == pytest.approx(-25.90)
    assert card["date"] == date(2026, 3, 15)
    assert card["payment_type"] == "CCRD"


def test_twint_else_branch_strips_twint_prefix_and_reference_digits():
    txns = parse_camt053(_camt053_doc())
    twint = txns[1]
    # TWINT prefix + trailing 13-digit reference must both be stripped,
    # leaving just the real merchant name.
    assert twint["merchant"] == "Coop Bern"
    assert "TWINT" not in twint["merchant"]
    assert twint["amount"] == pytest.approx(-42.50)
    assert twint["date"] == date(2026, 3, 16)


def test_icdt_standing_order_uses_creditor_name_as_merchant():
    txns = parse_camt053(_camt053_doc())
    icdt = txns[2]
    assert icdt["merchant"] == "Swisscom AG"
    assert icdt["amount"] == pytest.approx(-89.00)
    assert icdt["payment_type"] == "ICDT"
    assert icdt["date"] == date(2026, 3, 20)


def test_rcdt_salary_uses_debtor_name_and_is_positive():
    txns = parse_camt053(_camt053_doc())
    sala = txns[3]
    assert sala["merchant"] == "Acme Corp AG"
    assert sala["amount"] == pytest.approx(6500.00)
    assert sala["payment_type"] == "RCDT"
    assert sala["payment_subtype"] == "SALA"
    assert sala["date"] == date(2026, 3, 25)


def test_missing_statement_returns_empty_list():
    xml = "<Document><BkToCstmrStmt></BkToCstmrStmt></Document>"
    assert parse_camt053(xml) == []
