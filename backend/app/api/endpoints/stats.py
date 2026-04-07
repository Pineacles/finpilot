"""Statistics endpoints — monthly and yearly aggregated data."""
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, and_, func, extract, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.finance import Transaction, Category, Budget, RecurringExpense
from app.models.stock import StockPosition, PortfolioSnapshot
from app.models.user import User

router = APIRouter(prefix="/api/dashboard/stats", tags=["stats"])


@router.get("/monthly")
async def monthly_stats(
    year: int | None = None,
    month: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    y = year or today.year
    m = month or today.month
    month_start = date(y, m, 1)
    month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)
    prev_start = month_start - relativedelta(months=1)
    prev_end = month_start - timedelta(days=1)

    async def _period_totals(start: date, end: date):
        result = await db.execute(
            select(
                func.coalesce(func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)), 0).label("income"),
                func.coalesce(func.sum(case((Transaction.amount < 0, func.abs(Transaction.amount)), else_=0)), 0).label("expenses"),
                func.count(Transaction.id).label("txn_count"),
            ).where(and_(Transaction.user_id == user.id, Transaction.date >= start, Transaction.date <= end))
        )
        row = result.one()
        return {"income": float(row.income), "expenses": float(row.expenses), "txn_count": int(row.txn_count)}

    current = await _period_totals(month_start, month_end)
    previous = await _period_totals(prev_start, prev_end)

    current["net"] = current["income"] - current["expenses"]
    current["savings_rate"] = (current["net"] / current["income"] * 100) if current["income"] else 0
    days_elapsed = min((today - month_start).days + 1, (month_end - month_start).days + 1)
    current["avg_daily_spend"] = current["expenses"] / days_elapsed if days_elapsed else 0

    # Month-over-month change
    mom = {}
    for key in ["income", "expenses", "net"]:
        prev_val = previous.get(key, previous["income"] - previous["expenses"] if key == "net" else 0)
        if key == "net":
            prev_val = previous["income"] - previous["expenses"]
        curr_val = current[key]
        mom[key] = {
            "current": curr_val,
            "previous": prev_val,
            "change": curr_val - prev_val,
            "change_pct": ((curr_val - prev_val) / prev_val * 100) if prev_val else 0,
        }

    # Spending by category
    cat_result = await db.execute(
        select(
            Category.id,
            Category.name,
            Category.color,
            func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(and_(
            Transaction.user_id == user.id,
            Transaction.date >= month_start,
            Transaction.date <= month_end,
            Transaction.amount < 0,
        ))
        .group_by(Category.id, Category.name, Category.color)
        .order_by(func.sum(func.abs(Transaction.amount)).desc())
    )
    categories = [
        {"id": r.id, "name": r.name or "Uncategorized", "color": r.color, "total": float(r.total), "count": int(r.count)}
        for r in cat_result.all()
    ]

    # Top merchants
    merchant_result = await db.execute(
        select(
            Transaction.merchant,
            func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .where(and_(
            Transaction.user_id == user.id,
            Transaction.date >= month_start,
            Transaction.date <= month_end,
            Transaction.amount < 0,
        ))
        .group_by(Transaction.merchant)
        .order_by(func.sum(func.abs(Transaction.amount)).desc())
        .limit(10)
    )
    top_merchants = [
        {"merchant": r.merchant, "total": float(r.total), "count": int(r.count)}
        for r in merchant_result.all()
    ]

    # Daily spending for velocity chart
    daily_result = await db.execute(
        select(
            Transaction.date,
            func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("total"),
        )
        .where(and_(
            Transaction.user_id == user.id,
            Transaction.date >= month_start,
            Transaction.date <= month_end,
            Transaction.amount < 0,
        ))
        .group_by(Transaction.date)
        .order_by(Transaction.date)
    )
    daily_spend = [{"date": r.date.isoformat(), "amount": float(r.total)} for r in daily_result.all()]

    # Cumulative spending (for velocity curve)
    cumulative = []
    running = 0
    for d in daily_spend:
        running += d["amount"]
        cumulative.append({"date": d["date"], "cumulative": running})

    # Budget vs actual
    budget_result = await db.execute(select(Budget, Category).outerjoin(Category, Budget.category_id == Category.id).where(Budget.user_id == user.id))
    budget_vs_actual = []
    for budget, cat in budget_result.all():
        spent_q = select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0)).where(
            and_(Transaction.user_id == user.id, Transaction.date >= month_start, Transaction.date <= month_end, Transaction.amount < 0)
        )
        if budget.category_id:
            spent_q = spent_q.where(Transaction.category_id == budget.category_id)
        spent = float((await db.execute(spent_q)).scalar())
        budget_vs_actual.append({
            "name": budget.name,
            "category": cat.name if cat else "All",
            "budget": budget.amount,
            "spent": spent,
            "remaining": max(budget.amount - spent, 0),
            "pct": (spent / budget.amount * 100) if budget.amount else 0,
        })

    # Recurring vs discretionary
    rec_result = await db.execute(
        select(func.coalesce(func.sum(RecurringExpense.amount), 0))
        .where(and_(RecurringExpense.user_id == user.id, RecurringExpense.active == True))
    )
    recurring_total = float(rec_result.scalar())

    return {
        "period": {"year": y, "month": m, "start": month_start.isoformat(), "end": month_end.isoformat()},
        "summary": current,
        "comparison": mom,
        "categories": categories,
        "top_merchants": top_merchants,
        "daily_spend": daily_spend,
        "spending_velocity": cumulative,
        "budget_vs_actual": budget_vs_actual,
        "recurring_vs_discretionary": {
            "recurring": recurring_total,
            "discretionary": max(current["expenses"] - recurring_total, 0),
        },
    }


@router.get("/yearly")
async def yearly_stats(
    year: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    y = year or date.today().year
    year_start = date(y, 1, 1)
    year_end = date(y, 12, 31)
    prev_year_start = date(y - 1, 1, 1)
    prev_year_end = date(y - 1, 12, 31)

    async def _year_totals(start: date, end: date):
        result = await db.execute(
            select(
                func.coalesce(func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)), 0).label("income"),
                func.coalesce(func.sum(case((Transaction.amount < 0, func.abs(Transaction.amount)), else_=0)), 0).label("expenses"),
                func.count(Transaction.id).label("txn_count"),
            ).where(and_(Transaction.user_id == user.id, Transaction.date >= start, Transaction.date <= end))
        )
        row = result.one()
        return {"income": float(row.income), "expenses": float(row.expenses), "txn_count": int(row.txn_count)}

    current = await _year_totals(year_start, year_end)
    previous = await _year_totals(prev_year_start, prev_year_end)

    current["net"] = current["income"] - current["expenses"]
    current["savings_rate"] = (current["net"] / current["income"] * 100) if current["income"] else 0
    months_elapsed = min((date.today() - year_start).days / 30.44, 12)
    current["avg_monthly_spend"] = current["expenses"] / months_elapsed if months_elapsed else 0
    current["avg_monthly_income"] = current["income"] / months_elapsed if months_elapsed else 0

    # YoY change
    yoy = {}
    for key in ["income", "expenses"]:
        prev_val = previous[key]
        curr_val = current[key]
        yoy[key] = {
            "current": curr_val,
            "previous": prev_val,
            "change": curr_val - prev_val,
            "change_pct": ((curr_val - prev_val) / prev_val * 100) if prev_val else 0,
        }
    prev_net = previous["income"] - previous["expenses"]
    yoy["net"] = {
        "current": current["net"],
        "previous": prev_net,
        "change": current["net"] - prev_net,
        "change_pct": ((current["net"] - prev_net) / abs(prev_net) * 100) if prev_net else 0,
    }

    # Monthly breakdown for the year
    monthly_result = await db.execute(
        select(
            extract("month", Transaction.date).label("month"),
            func.coalesce(func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)), 0).label("income"),
            func.coalesce(func.sum(case((Transaction.amount < 0, func.abs(Transaction.amount)), else_=0)), 0).label("expenses"),
        )
        .where(and_(Transaction.user_id == user.id, Transaction.date >= year_start, Transaction.date <= year_end))
        .group_by("month")
        .order_by("month")
    )
    monthly = [
        {"month": int(r.month), "income": float(r.income), "expenses": float(r.expenses), "net": float(r.income) - float(r.expenses)}
        for r in monthly_result.all()
    ]

    # Annual category breakdown
    cat_result = await db.execute(
        select(
            Category.id,
            Category.name,
            Category.color,
            func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(and_(
            Transaction.user_id == user.id,
            Transaction.date >= year_start,
            Transaction.date <= year_end,
            Transaction.amount < 0,
        ))
        .group_by(Category.id, Category.name, Category.color)
        .order_by(func.sum(func.abs(Transaction.amount)).desc())
    )
    categories = [
        {"id": r.id, "name": r.name or "Uncategorized", "color": r.color, "total": float(r.total), "count": int(r.count)}
        for r in cat_result.all()
    ]

    # Category trends (per month per category, top 5)
    top_cat_names = [c["name"] for c in categories[:5]]
    category_trends = []
    if top_cat_names:
        trend_result = await db.execute(
            select(
                extract("month", Transaction.date).label("month"),
                Category.name,
                func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("total"),
            )
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(and_(
                Transaction.user_id == user.id,
                Transaction.date >= year_start,
                Transaction.date <= year_end,
                Transaction.amount < 0,
                Category.name.in_(top_cat_names),
            ))
            .group_by("month", Category.name)
            .order_by("month")
        )
        for r in trend_result.all():
            category_trends.append({"month": int(r.month), "category": r.name, "total": float(r.total)})

    # Net worth change (portfolio snapshots)
    snapshots_result = await db.execute(
        select(PortfolioSnapshot)
        .where(and_(PortfolioSnapshot.user_id == user.id, PortfolioSnapshot.snapshot_date >= year_start))
        .order_by(PortfolioSnapshot.snapshot_date)
    )
    snapshots = [
        {"date": s.snapshot_date.isoformat(), "value": s.total_value, "pnl": s.total_pnl}
        for s in snapshots_result.scalars().all()
    ]

    # Top merchants for the year
    merchant_result = await db.execute(
        select(
            Transaction.merchant,
            func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .where(and_(
            Transaction.user_id == user.id,
            Transaction.date >= year_start,
            Transaction.date <= year_end,
            Transaction.amount < 0,
        ))
        .group_by(Transaction.merchant)
        .order_by(func.sum(func.abs(Transaction.amount)).desc())
        .limit(10)
    )
    top_merchants = [
        {"merchant": r.merchant, "total": float(r.total), "count": int(r.count)}
        for r in merchant_result.all()
    ]

    return {
        "period": {"year": y},
        "summary": current,
        "comparison": yoy,
        "monthly": monthly,
        "categories": categories,
        "category_trends": category_trends,
        "top_merchants": top_merchants,
        "net_worth_history": snapshots,
    }
