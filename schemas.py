from pydantic import BaseModel
from decimal import Decimal
from typing import List

class UserBase(BaseModel):
    username: str
    email: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int

    class Config:
        orm_mode = True

class LoanRecord(BaseModel):
    amount: Decimal
    annual_interest_rate: Decimal
    loan_term: int

class LoanCreate(BaseModel):
    loan_record: LoanRecord
    user_ids: List[int]

class LoanSchedule(BaseModel):
    month: int
    remaining_balance: Decimal
    monthly_payment: Decimal

class LoanSummary(BaseModel):
    current_principal_balance: Decimal
    aggregate_principal_paid: Decimal
    aggregate_interest_paid: Decimal
