from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.account import Account
from app.models.user import User
from app.services.csv_import import import_transactions
from app.services.seed_merchants import seed_merchants

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
    if ext not in ("csv", "xml"):
        raise HTTPException(status_code=400, detail="File must be .csv or .xml")

    raw = await file.read()
    # Try multiple encodings for CSV, XML is usually UTF-8
    for encoding in ("utf-8-sig", "utf-8", "iso-8859-1", "cp1252"):
        try:
            content = raw.decode(encoding)
            break
        except (UnicodeDecodeError, ValueError):
            continue
    else:
        raise HTTPException(status_code=400, detail="Could not decode file")

    # Find or create bank account
    if not account_id:
        result = await db.execute(
            select(Account).where(Account.user_id == user.id, Account.type == "bank")
        )
        account = result.scalar_one_or_none()
        if not account:
            account = Account(user_id=user.id, name="Bank Account", type="bank", currency="CHF")
            db.add(account)
            await db.flush()
        account_id = account.id

    await seed_merchants(db, user.id)

    try:
        result = await import_transactions(db, user.id, account_id, content, use_ai=use_ai)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")


@router.post("/seed-merchants")
async def trigger_seed_merchants(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Seed the merchant database with Swiss defaults."""
    await seed_merchants(db, user.id)
    return {"status": "ok", "message": "Merchants seeded"}
