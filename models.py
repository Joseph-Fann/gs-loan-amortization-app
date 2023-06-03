from sqlalchemy import Column, Integer, Numeric, String, Table, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

loan_users = Table(
    "loan_users",
    Base.metadata,
    Column("loan_id", Integer, ForeignKey("loans.id")),
    Column("user_id", Integer, ForeignKey("users.id")),
)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True,autoincrement=True)
    name = Column(String, unique=False, index=True)
    email = Column(String, unique=True, index=True)

    loans = relationship("Loan", secondary=loan_users, back_populates="users")

class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Numeric(precision=12, scale=2))
    annual_interest_rate = Column(Numeric(precision=6, scale=4))
    loan_term = Column(Integer)

    users = relationship("User", secondary=loan_users, back_populates="loans")