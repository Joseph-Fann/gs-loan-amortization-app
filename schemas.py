from pydantic import BaseModel, EmailStr, Field
from decimal import Decimal
from typing import List

class BaseUser(BaseModel):
    name: str
    email: EmailStr


class UserCreate(BaseUser):
    pass

class LoanRecord(BaseModel):
    amount: Decimal = Field(ge=1, decimal_places=2,  description="Loan amount (positive)")
    annual_interest_rate: Decimal = Field(gt=0, decimal_places=4, description="Annual interest rate")
    loan_term: int = Field(gt=0, description="Loan term in months")

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
