import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.account import Account
from app.models.user import User
from app.services.csv_import import import_transactions
from app.services.seed_merchants import seed_merchants
from app.services import mapped_import
from app.services import import_profile_service
from app.services.import_profile_service import ImportProfileNotFoundError
from app.schemas.import_profile import (
    ColumnMappingSchema,
    CsvPreviewResponse,
    ImportProfileCreate,
    ImportProfileResponse,
)

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/csv")
async def upload_file(
    file: UploadFile = File(...),
    account_id: str = Form(default=""),
    use_ai: bool = Form(default=True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import bank statement. Supports Valiant CSV and camt.053 XML."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("csv", "xml", "tsv", "pdf"):
        raise HTTPException(status_code=400, detail="File must be .csv, .tsv, .xml, or .pdf")

    raw = await file.read()

    # PDF files are handled separately (binary, not text)
    if ext == "pdf":
        from app.services.pdf_import import parse_postfinance_pdf_auto
        try:
            parsed = parse_postfinance_pdf_auto(raw)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"PDF parse failed: {e}")

        fmt = "postfinance_cc_pdf" if parsed.get("is_credit_card") else "postfinance_pdf"
        content = None  # not used for PDF
        raw_transactions = parsed["transactions"]
        opening_balance = parsed.get("opening_balance")
    else:
        # Text-based files
        for encoding in ("utf-8-sig", "utf-8", "iso-8859-1", "cp1252"):
            try:
                content = raw.decode(encoding)
                break
            except (UnicodeDecodeError, ValueError):
                continue
        else:
            raise HTTPException(status_code=400, detail="Could not decode file")

        from app.services.csv_import import detect_format
        fmt = detect_format(content)
        raw_transactions = None
        opening_balance = None

    is_credit_card = fmt in ("viseca", "postfinance_cc_pdf")

    # Find or create the right account
    if not account_id:
        acct_type = "credit_card" if is_credit_card else "bank"
        if fmt == "viseca":
            acct_name = "Viseca Credit Card"
        elif fmt == "postfinance_cc_pdf":
            acct_name = "PostFinance Mastercard"
        elif fmt in ("postfinance", "postfinance_pdf"):
            acct_name = "PostFinance"
        else:
            acct_name = "Valiant Bank"
        result = await db.execute(
            select(Account).where(Account.user_id == user.id, Account.type == acct_type)
        )
        account = result.scalar_one_or_none()
        if not account:
            account = Account(user_id=user.id, name=acct_name, type=acct_type, currency="CHF")
            db.add(account)
            await db.flush()
        account_id = account.id

    await seed_merchants(db, user.id)

    try:
        if fmt in ("postfinance_pdf", "postfinance_cc_pdf"):
            # Pass pre-parsed transactions to import function
            result = await import_transactions(
                db, user.id, account_id, "",
                use_ai=use_ai,
                pre_parsed=raw_transactions,
                opening_balance=opening_balance,
            )
        else:
            result = await import_transactions(db, user.id, account_id, content, use_ai=use_ai)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback, logging
        logging.getLogger(__name__).error(f"Import failed:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")


@router.post("/seed-merchants")
async def trigger_seed_merchants(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Seed the merchant database with Swiss defaults."""
    await seed_merchants(db, user.id)
    return {"status": "ok", "message": "Merchants seeded"}


# ── Generic CSV column-mapper import ────────────────────────────────
# For any CSV format not recognized by detect_format() above (e.g. a
# Cumulus/Cembra card export): preview the columns, let the user map them,
# then import through the exact same pipeline (dedup/categorize/settlement)
# via import_transactions(pre_parsed=...).

@router.post("/csv/preview", response_model=CsvPreviewResponse)
async def preview_csv_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Sniff delimiter/encoding and return the header + first ~10 rows so the
    frontend can render a column-mapping UI."""
    raw = await file.read()
    try:
        preview = mapped_import.preview_csv(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return preview


@router.post("/csv/mapped")
async def import_mapped_csv(
    file: UploadFile = File(...),
    account_id: str = Form(...),
    mapping: str = Form(..., description="JSON-encoded ColumnMappingSchema"),
    use_ai: bool = Form(default=True),
    save_as_profile_name: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import a CSV using an explicit user-supplied column mapping, for any
    format detect_format() doesn't recognize."""
    try:
        mapping_dict = json.loads(mapping)
        column_mapping = ColumnMappingSchema(**mapping_dict)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid mapping: {e}")

    # Verify the target account belongs to this user
    acct_result = await db.execute(
        select(Account).where(Account.id == account_id, Account.user_id == user.id)
    )
    if not acct_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Account not found")

    raw = await file.read()
    try:
        internal_mapping = mapped_import.ColumnMapping(**column_mapping.model_dump())
        raw_transactions = mapped_import.parse_mapped_csv(raw, internal_mapping)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not raw_transactions:
        raise HTTPException(status_code=400, detail="No rows matched the given mapping")

    await seed_merchants(db, user.id)

    try:
        result = await import_transactions(
            db, user.id, account_id, "",
            use_ai=use_ai,
            pre_parsed=raw_transactions,
            source_format="mapped_csv",
        )
    except Exception as e:
        import traceback, logging
        logging.getLogger(__name__).error(f"Mapped import failed:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")

    if save_as_profile_name:
        await import_profile_service.create_profile(
            db, user.id, save_as_profile_name, account_id, column_mapping.model_dump()
        )
        result["saved_profile"] = save_as_profile_name

    return result


# ── ImportProfile CRUD (saved column mappings) ──────────────────────

@router.get("/profiles", response_model=list[ImportProfileResponse])
async def list_import_profiles(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await import_profile_service.list_profiles(db, user.id)


@router.post("/profiles", response_model=ImportProfileResponse)
async def create_import_profile(
    body: ImportProfileCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await import_profile_service.create_profile(
        db, user.id, body.name, body.account_id, body.mapping.model_dump()
    )


@router.delete("/profiles/{profile_id}")
async def delete_import_profile(
    profile_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await import_profile_service.delete_profile(db, user.id, profile_id)
    except ImportProfileNotFoundError:
        raise HTTPException(status_code=404, detail="Import profile not found")
    return {"status": "deleted", "id": profile_id}
