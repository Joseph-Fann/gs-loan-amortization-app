from decimal import Decimal, ROUND_HALF_DOWN
from typing import List
import os

from fastapi import Depends, FastAPI,HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session


from models import User, Loan, Base
from schemas import UserCreate, LoanCreate, LoanSchedule, LoanSummary

app = FastAPI()

if os.path.exists("database.db"):
    os.remove("database.db")
engine = create_engine("sqlite:///database.db")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

Base.metadata.create_all(bind=engine)

@app.post("/user")
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = User(name=user.name, email=user.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"message": f"User {db_user.name} created successfully"}

@app.post("/loan")
async def create_loan(loan: LoanCreate, db: Session = Depends(get_db)):
    
    users = db.query(User).filter(User.id.in_(loan.user_ids)).all()
    
    loan_data = loan.loan_record.dict()
    annual_interest_rate = loan_data["annual_interest_rate"]
    loan_data["annual_interest_rate"] = Decimal(annual_interest_rate).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_DOWN
    )
    db_loan = Loan(users=users, **loan_data)
    db.add(db_loan)
    db.commit()
    db.refresh(db_loan)
    return {"message": f"Loan {db_loan.id} created successfully"}


def calculate_monthly_payment(amount: Decimal, interest_rate: Decimal, loan_term: int) -> Decimal:
    monthly_interest_rate = interest_rate / Decimal(12 * 100)
    denominator = (1 - (1 + monthly_interest_rate) ** -loan_term)
    monthly_payment = (amount * monthly_interest_rate) / denominator
    return monthly_payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)

def calculate_loan_schedule(amount: Decimal, interest_rate: Decimal, loan_term: int) -> List[LoanSchedule]:
    schedule = []
    remaining_balance = amount
    monthly_interest_rate = interest_rate / Decimal(12) / Decimal(100)
    monthly_payment = calculate_monthly_payment(amount, interest_rate, loan_term)

    for month in range(1, loan_term + 1):
        interest_payment = remaining_balance * monthly_interest_rate
        principal_payment = monthly_payment - interest_payment
        remaining_balance -= principal_payment

        loan_schedule = LoanSchedule(
            month=month,
            remaining_balance=remaining_balance.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN),
            monthly_payment=monthly_payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN),
        )
        schedule.append(loan_schedule)

    return schedule
@app.get("/loan/{loan_id}/schedule")
async def get_loan_schedule(loan_id: int,db: Session = Depends(get_db)):
    
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        return {"message": "Loan not found"}

    schedule = calculate_loan_schedule(loan.amount, loan.annual_interest_rate, loan.loan_term)

    return schedule


@app.get("/loan/{loan_id}/summary")
async def get_loan_summary(loan_id: int, month_number: int,db: Session = Depends(get_db)):
    
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        return {"message": "Loan not found"}

    schedule = calculate_loan_schedule(loan.amount, loan.annual_interest_rate, loan.loan_term)

    principal_paid = Decimal(0.0)
    interest_paid = Decimal(0.0)
    remaining_balance = loan.amount
    for month in range(1, month_number + 1):
        interest_payment = schedule[month - 1].monthly_payment - (remaining_balance * loan.annual_interest_rate / Decimal(12) / Decimal(100))
        principal_payment = schedule[month - 1].monthly_payment - interest_payment
        principal_paid += principal_payment
        interest_paid += interest_payment
        remaining_balance -= principal_payment

    loan_summary = LoanSummary(
        current_principal_balance=remaining_balance.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN),
        aggregate_principal_paid=principal_paid.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN),
        aggregate_interest_paid=interest_paid.quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN),
    )

    return loan_summary

@app.get("/user/{user_id}/loans")
async def get_user_loans(user_id: int,db: Session = Depends(get_db)):
    
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    loans = user.loans
    return loans


@app.post("/loan/{loan_id}/share")
async def share_loan(loan_id: int, user_ids: List[int],db: Session = Depends(get_db)):
    
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    for user_id in user_ids:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
        loan.users.append(user)

    db.commit()

    return {"message": "Loan shared successfully"}