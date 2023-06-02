from decimal import Decimal, ROUND_DOWN
from typing import List

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, Integer, Numeric, Float, String, Table, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship

app = FastAPI()

engine = create_engine("sqlite:///database.db")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

loan_users = Table(
    "loan_users",
    Base.metadata,
    Column("loan_id", Integer, ForeignKey("loans.id")),
    Column("user_id", Integer, ForeignKey("users.id")),
)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)

    loans = relationship("Loan", secondary=loan_users, back_populates="users")
class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Numeric(precision=12, scale=2))
    annual_interest_rate = Column(Numeric(precision=6, scale=4))
    loan_term = Column(Integer)

    users = relationship("User", secondary=loan_users, back_populates="loans")
Base.metadata.create_all(bind=engine)

class UserCreate(BaseModel):
    username: str
    email: str
class LoanRecord(BaseModel):
    amount: float
    annual_interest_rate: Decimal
    loan_term: int

class LoanCreate(BaseModel):
    loan_record: LoanRecord
    user_ids: List[int]


@app.post("/users")
async def create_user(user: UserCreate):
    db = SessionLocal()
    db_user = User(username=user.username, email=user.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"message": "User created successfully"}

@app.post("/loans")
async def create_loan(loan: LoanCreate):
    db = SessionLocal()
    users = db.query(User).filter(User.id.in_(loan.user_ids)).all()
    
    loan_data = loan.loan_record.dict()
    annual_interest_rate = loan_data["annual_interest_rate"]
    loan_data["annual_interest_rate"] = Decimal(annual_interest_rate).quantize(
        Decimal("0.0001"), rounding=ROUND_DOWN
    )
    db_loan = Loan(users=users, **loan_data)
    db.add(db_loan)
    db.commit()
    db.refresh(db_loan)
    return {"message": "Loan created successfully"}


class LoanSchedule(BaseModel):
    month: int
    remaining_balance: float
    monthly_payment: float
def calculate_loan_schedule(amount: float, interest_rate: float, loan_term: int) -> List[LoanSchedule]:
    monthly_interest_rate = interest_rate / 12 / 100
    monthly_payment = (amount * monthly_interest_rate) / (1 - (1 + monthly_interest_rate) ** -loan_term)

    schedule = []
    remaining_balance = amount
    for month in range(1, loan_term + 1):
        interest_payment = remaining_balance * monthly_interest_rate
        principal_payment = monthly_payment - interest_payment
        remaining_balance -= principal_payment

        schedule.append(
            LoanSchedule(
                month=month,
                remaining_balance=remaining_balance.quantize(Decimal("0.01"), rounding=ROUND_DOWN),
                monthly_payment=monthly_payment.quantize(Decimal("0.01"), rounding=ROUND_DOWN),
            )
        )

    return schedule
@app.get("/loan_schedule/{loan_id}")
async def get_loan_schedule(loan_id: int):
    db = SessionLocal()
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        return {"message": "Loan not found"}

    schedule = calculate_loan_schedule(loan.amount, loan.annual_interest_rate, loan.loan_term)

    return schedule

class LoanSummary(BaseModel):
    current_principal_balance: float
    aggregate_principal_paid: float
    aggregate_interest_paid: float



@app.get("/loan_summary/{loan_id}")
async def get_loan_summary(loan_id: int, month_number: int):
    db = SessionLocal()
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        return {"message": "Loan not found"}

    schedule = calculate_loan_schedule(loan.amount, loan.annual_interest_rate, loan.loan_term)

    principal_paid = 0.0
    interest_paid = 0.0
    remaining_balance = loan.amount
    for month in range(1, month_number + 1):
        interest_payment = schedule[month - 1].monthly_payment - (remaining_balance * loan.annual_interest_rate / 12 / 100)
        principal_payment = schedule[month - 1].monthly_payment - interest_payment
        principal_paid += principal_payment
        interest_paid += interest_payment
        remaining_balance -= principal_payment

    loan_summary = LoanSummary(
        current_principal_balance=remaining_balance.quantize(Decimal("0.01"), rounding=ROUND_DOWN),
        aggregate_principal_paid=principal_paid.quantize(Decimal("0.01"), rounding=ROUND_DOWN),
        aggregate_interest_paid=interest_paid.quantize(Decimal("0.01"), rounding=ROUND_DOWN),
    )

    return loan_summary