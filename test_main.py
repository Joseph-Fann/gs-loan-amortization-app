from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session
import pytest
import os

from models import Base, User, Loan
from main import app, get_db, calculate_monthly_payment, calculate_loan_schedule

SQLALCHEMY_DATABASE_URL = "sqlite:///test.db"
# if os.path.exists("./test.db"):
#     os.remove("./test.db")
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture
def db_session():
    # Establish a test database session
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    # Provide the session to the application via dependency injection
    app.dependency_overrides[get_db] = lambda: session

    yield session

    # Clean up the test database session
    session.close()
    transaction.rollback()
    connection.close()

def test_create_user(db_session):
    response = client.post(
        "/user",
        json = {
            "name": "John",
            "email": "john@example.com"
        },
    )
    
    assert response.status_code == 200

    user = db_session.query(User).filter(User.email == "john@example.com").first()

    assert user is not None
    assert user.name == "John"
    assert user.email == "john@example.com"

def test_create_loan(db_session):
    response = client.post(
        "/user",
        json = {
            "name": "John",
            "email": "john@example.com"
        },
    )
    
    assert response.status_code == 200

    user = db_session.query(User).filter(User.email == "john@example.com").first()
    # normal loan
    response = client.post(
        "/loan",
        json = {
            "loan_record": {
                "amount": 10000,
                "annual_interest_rate": 3,
                "loan_term": 12
            },
            "user_ids": [
                user.id
            ]
        },
    )
    
    assert response.status_code == 200
    
    loan = db_session.query(Loan).first()
    assert loan is not None
    assert loan.amount == 10000
    assert loan.annual_interest_rate == 3
    assert loan.loan_term == 12

    # no id is ok
    response = client.post(
        "/loan",
        json = {
            "loan_record": {
                "amount": 10000,
                "annual_interest_rate": 3,
                "loan_term": 12
            },
            "user_ids": []
        },
    )
    
    assert response.status_code == 200

    # bad amount
    response = client.post(
        "/loan",
        json = {
            "loan_record": {
                "amount": -10000,
                "annual_interest_rate": 3,
                "loan_term": 12
            },
            "user_ids": [
                user.id
            ]
        },
    )
    
    assert response.status_code == 422

    # bad interest rate
    response = client.post(
        "/loan",
        json = {
            "loan_record": {
                "amount": 10000,
                "annual_interest_rate": -3,
                "loan_term": 12
            },
            "user_ids": [
                user.id
            ]
        },
    )
    
    assert response.status_code == 422

    # bad term
    response = client.post(
        "/loan",
        json = {
            "loan_record": {
                "amount": 10000,
                "annual_interest_rate": 2,
                "loan_term": -2
            },
            "user_ids": [
                user.id
            ]
        },
    )
    
    assert response.status_code == 422


def test_calculate_monthly_payment():
    # Test data
    principal = Decimal('10000')
    annual_interest_rate = Decimal('5.5')
    loan_term = 12

    # Calculate the monthly payment
    monthly_payment = calculate_monthly_payment(principal, annual_interest_rate, loan_term)

    # Assert the calculated monthly payment
    assert monthly_payment == Decimal('858.37')

def test_calculate_loan_schedule():
    principal = Decimal('10000')
    annual_interest_rate = Decimal('5.5')
    loan_term = 12

    # Calculate the loan schedule
    loan_schedule = calculate_loan_schedule(principal, annual_interest_rate, loan_term)

    # Assert the length of the loan schedule
    assert len(loan_schedule) == loan_term

    # Assert the first month's monthly payment
    assert loan_schedule[0].monthly_payment == Decimal('858.37')

    # Last month remaining balance almost equal to zero
    assert loan_schedule[-1].remaining_balance == Decimal('-0.03')


def test_get_loan_schedule(db_session):

    response = client.post(
        "/user",
        json = {
            "name": "John",
            "email": "john@example.com"
        },
    )
    
    assert response.status_code == 200

    user = db_session.query(User).filter(User.email == "john@example.com").first()
    # normal loan
    response = client.post(
        "/loan",
        json = {
            "loan_record": {
                "amount": 10000,
                "annual_interest_rate": 5.5,
                "loan_term": 12
            },
            "user_ids": [
                user.id
            ]
        },
    )
    assert response.status_code == 200

    response = client.get("/loan/1/schedule")
    assert response.status_code == 200

    loan_schedule = response.json()
    assert len(loan_schedule) == 12
    assert loan_schedule[0]["monthly_payment"] == 858.37  # almost euqal?


def test_get_loan_summary(db_session):
    response = client.post(
        "/user",
        json = {
            "name": "John",
            "email": "john@example.com"
        },
    )
    
    assert response.status_code == 200

    user = db_session.query(User).filter(User.email == "john@example.com").first()
    # normal loan
    response = client.post(
        "/loan",
        json = {
            "loan_record": {
                "amount": 10000,
                "annual_interest_rate": 5.5,
                "loan_term": 12
            },
            "user_ids": [
                user.id
            ]
        },
    )
    assert response.status_code == 200
    loan = db_session.query(Loan).first()

    response = client.get(
        f"/loan/{loan.id}/summary?month_number=0",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["current_principal_balance"] == 10000  # it seems this is not consistent with loan schedule endpoint
    assert True == False


