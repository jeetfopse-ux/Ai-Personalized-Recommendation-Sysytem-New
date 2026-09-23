import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date
from models import db, User, Income, Expense, Budget, ExpenseCategory, SavingsGoal

from services.finance_service import (
    get_monthly_summary,
    get_category_spending,
    get_budget_performance,
    get_50_30_20_breakdown,
    get_emergency_fund_status
)

def test_income_and_expense_tracking(app):
    with app.app_context():
        user = User.query.filter_by(email="tester@finance.ai").first()
        today = date.today()

        # Add Income
        inc = Income(
            user_id=user.id,
            source="Monthly Salary",
            amount=4000.0,
            date=today,
            frequency="Monthly"
        )
        db.session.add(inc)

        # Get Groceries category
        groceries = ExpenseCategory.query.filter_by(name="Groceries").first()
        exp = Expense(
            user_id=user.id,
            category_id=groceries.id,
            amount=350.0,
            date=today,
            description="Supermarket groceries"
        )
        db.session.add(exp)
        db.session.commit()

        # Check Summary
        summary = get_monthly_summary(user.id, today.year, today.month)
        assert summary["total_income"] == 4000.0
        assert summary["total_expenses"] == 350.0
        assert summary["net_savings"] == 3650.0
        assert summary["savings_rate"] == 91.2

def test_budget_overspending_detection(app):
    with app.app_context():
        user = User.query.filter_by(email="tester@finance.ai").first()
        today = date.today()

        dining = ExpenseCategory.query.filter_by(name="Dining & Takeout").first()
        
        # Allocate $200 budget
        bgt = Budget(
            user_id=user.id,
            category_id=dining.id,
            month=today.month,
            year=today.year,
            allocated_amount=200.0
        )
        db.session.add(bgt)

        # Spend $250 (over budget)
        exp = Expense(
            user_id=user.id,
            category_id=dining.id,
            amount=250.0,
            date=today,
            description="Fancy Dinner"
        )
        db.session.add(exp)
        db.session.commit()

        perf = get_budget_performance(user.id, today.year, today.month)
        assert perf["total_allocated"] == 200.0
        assert perf["total_spent_in_budgeted"] == 250.0
        assert perf["overbudget_count"] == 1
        assert perf["overbudget_items"][0]["status"] == "overbudget"

def test_50_30_20_breakdown(app):
    with app.app_context():
        user = User.query.filter_by(email="tester@finance.ai").first()
        today = date.today()

        # Add Income $5000
        db.session.add(Income(user_id=user.id, source="Salary", amount=5000.0, date=today))
        
        # Needs: Housing $1500
        housing = ExpenseCategory.query.filter_by(name="Housing & Rent").first()
        db.session.add(Expense(user_id=user.id, category_id=housing.id, amount=1500.0, date=today, description="Rent"))
        
        # Wants: Dining $600
        dining = ExpenseCategory.query.filter_by(name="Dining & Takeout").first()
        db.session.add(Expense(user_id=user.id, category_id=dining.id, amount=600.0, date=today, description="Dining"))

        db.session.commit()

        breakdown = get_50_30_20_breakdown(user.id, today.year, today.month)
        assert breakdown["income"] == 5000.0
        assert breakdown["needs"]["amount"] == 1500.0
        assert breakdown["needs"]["pct"] == 30.0  # 1500 / 5000 = 30%
        assert breakdown["wants"]["amount"] == 600.0
        assert breakdown["wants"]["pct"] == 12.0   # 600 / 5000 = 12%

def test_savings_and_emergency_runway(app):
    with app.app_context():
        user = User.query.filter_by(email="tester@finance.ai").first()
        today = date.today()

        # Add living expense to establish monthly burn
        groceries = ExpenseCategory.query.filter_by(name="Groceries").first()
        exp = Expense(
            user_id=user.id,
            category_id=groceries.id,
            amount=1000.0,
            date=today,
            description="Monthly Groceries"
        )
        db.session.add(exp)

        # Create an Emergency Savings Goal with $3000 saved
        goal = SavingsGoal(
            user_id=user.id,
            name="Emergency Safety Reserve",
            target_amount=6000.0,
            current_amount=3000.0,
            category="Emergency",
            status="In Progress"
        )
        db.session.add(goal)
        db.session.commit()

        status = get_emergency_fund_status(user.id)
        assert status["current_saved"] == 3000.0
        assert status["avg_monthly_burn"] == 1000.0
        # 3000 saved / 1000 monthly burn = 3.0 months runway
        assert status["runway_months"] == 3.0
        assert status["target_amount"] == 6000.0
        assert status["progress_pct"] == 50.0

def test_savings_routes_and_deposit(auth_client, app):
    # Test GET /savings renders successfully (no 500 internal server error)
    res = auth_client.get("/savings")
    assert res.status_code == 200
    assert b"Savings Goals" in res.data or b"Runway" in res.data

    # Test POST /savings to create a new goal
    res = auth_client.post("/savings", data={
        "name": "Vacation Fund",
        "target_amount": "2000.00",
        "current_amount": "500.00",
        "category": "Travel",
        "target_date": "2026-12-31"
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"Vacation Fund" in res.data

    # Test POST /savings/<goal_id>/deposit
    with app.app_context():
        goal = SavingsGoal.query.filter_by(name="Vacation Fund").first()
        assert goal is not None
        goal_id = goal.id

    deposit_res = auth_client.post(f"/savings/{goal_id}/deposit", data={
        "amount": "250.00"
    }, follow_redirects=True)
    assert deposit_res.status_code == 200
    assert b"Deposited" in deposit_res.data

    with app.app_context():
        updated_goal = db.session.get(SavingsGoal, goal_id)
        assert updated_goal.current_amount == 750.00

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__]))


