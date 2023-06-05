import os
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from main import (app, calculate_loan_schedule, calculate_loan_summary,
                  calculate_monthly_payment, get_db)
from models import Base, Loan, User

if os.path.exists("./test.db"):
    os.remove("./test.db")
TEST_DATABASE_URL = "sqlite:///test.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=engine)
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


def insert_test_data(session):
    # Prepare test data
    person_data = [
        {"name": "Adam", "email": "adam@example.com"},
        {"name": "Bob", "email": "Bob@example.com"},
        {"name": "Charlie", "email": "charlie@example.com"},
    ]

    test_user = []
    for person in person_data:
        # Create a test person
        test_person = User(name=person["name"], email=person["email"])
        session.add(test_person)
        test_user.append(test_person)

    session.commit()

    test_loans = []
    test_loan_1 = Loan(
        amount=Decimal(10000),
        annual_interest_rate=Decimal(3),
        loan_term=12,
        users=[test_user[0]],
    )
    session.add(test_loan_1)
    test_loans.append(test_loan_1)

    test_loan_2 = Loan(
        amount=Decimal(20000),
        annual_interest_rate=Decimal(6),
        loan_term=24,
        users=[test_user[0], test_user[1]],
    )
    session.add(test_loan_2)
    test_loans.append(test_loan_2)
    session.commit()

    return {"user": test_user, "loan": test_loans}


def test_create_user(db_session):
    users_table = db_session.query(User).all()
    assert len(users_table) == 0

    response = client.post(
        "/user",
        json={"name": "John", "email": "john@example.com"},
    )
    assert response.status_code == 200

    users_table = db_session.query(User).all()
    assert len(users_table) == 1

    user = db_session.query(User).filter(User.email == "john@example.com").first()
    assert user is not None
    assert user.name == "John"
    assert user.email == "john@example.com"

    response = client.post(
        "/user",
        json={"email": "john@example.com"},
    )
    # fail for missing name
    assert response.status_code == 422

    response = client.post(
        "/user",
        json={"name": "John", "email": "john@example.com"},
    )
    user = db_session.query(User).filter(User.email == "john@example.com").all()
    assert len(user) == 2


def test_create_loan(db_session):
    test_data = insert_test_data(db_session)
    loans = db_session.query(Loan).all()
    assert len(loans) == 2  # 2 existing records

    # normal loan
    response = client.post(
        "/loan",
        json={
            "loan_record": {
                "amount": 10000,
                "annual_interest_rate": 3,
                "loan_term": 12,
            },
            "user_ids": [test_data["user"][0].id],
        },
    )

    assert response.status_code == 200

    loan = db_session.query(Loan).first()
    assert loan is not None
    assert loan.amount == 10000
    assert loan.annual_interest_rate == 3
    assert loan.loan_term == 12
    assert loan.users[0].id == test_data["user"][0].id

    # multiple users
    response = client.post(
        "/loan",
        json={
            "loan_record": {
                "amount": 10002,
                "annual_interest_rate": 4,
                "loan_term": 12,
            },
            "user_ids": [test_data["user"][0].id, test_data["user"][1].id],
        },
    )

    assert response.status_code == 200

    loans = db_session.query(Loan).filter(Loan.amount == 10002).all()
    assert len(loans) == 1
    loan = loans[0]
    assert loan.amount == 10002
    assert loan.annual_interest_rate == 4
    assert loan.loan_term == 12
    assert loan.users[0].id == test_data["user"][0].id
    assert loan.users[1].id == test_data["user"][1].id

    # no id is ok
    response = client.post(
        "/loan",
        json={
            "loan_record": {
                "amount": 10001.0,
                "annual_interest_rate": 3.5,
                "loan_term": 12,
            },
            "user_ids": [],
        },
    )
    assert response.status_code == 200
    loans = db_session.query(Loan).filter(Loan.amount == 10001).all()
    assert len(loans) == 1
    loan = loans[0]
    assert loan.amount == 10001.0
    assert loan.annual_interest_rate == 3.5
    assert loan.loan_term == 12
    assert loan.users == []

    count_before = db_session.query(Loan).count()

    # bad amount
    response = client.post(
        "/loan",
        json={
            "loan_record": {
                "amount": -10000,
                "annual_interest_rate": 3,
                "loan_term": 12,
            },
            "user_ids": [1],
        },
    )

    assert response.status_code == 422

    # bad interest rate
    response = client.post(
        "/loan",
        json={
            "loan_record": {
                "amount": 10000,
                "annual_interest_rate": -3,
                "loan_term": 12,
            },
            "user_ids": [1],
        },
    )

    assert response.status_code == 422

    # bad term
    response = client.post(
        "/loan",
        json={
            "loan_record": {
                "amount": 10000,
                "annual_interest_rate": 2,
                "loan_term": -2,
            },
            "user_ids": [1],
        },
    )

    assert response.status_code == 422

    count_after = db_session.query(Loan).count()
    assert count_before == count_after  # number of records didn't change


def test_calculate_monthly_payment():
    # Test data
    amount = Decimal("10000")
    annual_interest_rate = Decimal("5.5")
    loan_term = 12

    # Calculate the monthly payment
    monthly_payment = calculate_monthly_payment(amount, annual_interest_rate, loan_term)

    # Assert the calculated monthly payment
    assert monthly_payment == Decimal("858.37")


def test_calculate_loan_schedule():
    amount = Decimal("10000")
    annual_interest_rate = Decimal("3")
    loan_term = 12

    # Calculate the loan schedule
    loan_schedule = calculate_loan_schedule(amount, annual_interest_rate, loan_term)

    # Assert the length of the loan schedule
    assert len(loan_schedule) == loan_term

    # Assert the first month's monthly payment
    assert loan_schedule[0].monthly_payment == Decimal("846.94")
    assert loan_schedule[0].remaining_balance == Decimal("9178.06")
    assert loan_schedule[0].month == 1

    # Last month remaining balance almost equal to zero
    assert loan_schedule[-1].remaining_balance == Decimal("-0.04")
    assert loan_schedule[-1].monthly_payment == Decimal("846.94")
    assert loan_schedule[-1].month == 12


def test_get_loan_schedule(db_session):
    test_data = insert_test_data(db_session)

    response = client.get(f"/loan/{test_data['loan'][0].id}/schedule")
    assert response.status_code == 200

    loan_schedule = response.json()

    assert len(loan_schedule) == 12
    assert loan_schedule[0]["monthly_payment"] == 846.94  # almost euqal?
    assert loan_schedule[0]["remaining_balance"] == 9178.06
    assert loan_schedule[0]["month"] == 1

    assert loan_schedule[-1]["monthly_payment"] == 846.94
    assert loan_schedule[-1]["remaining_balance"] == -0.04
    assert loan_schedule[-1]["month"] == 12

    response = client.get(f"/loan/9999/schedule")
    assert response.status_code == 404
    assert response.json() == {"detail": "Loan not found"}


def test_calculate_loan_summary():
    # Define test inputs
    amount = Decimal("10000")
    annual_interest_rate = Decimal("3")
    loan_term = 12
    month_number = 6

    loan_schedule = calculate_loan_schedule(amount, annual_interest_rate, loan_term)
    loan_summary = calculate_loan_summary(
        schedule=loan_schedule, month_number=month_number, amount=amount
    )

    # Perform assertions
    assert loan_summary.current_principal_balance == Decimal("5037.43")
    assert loan_summary.aggregate_principal_paid == Decimal("4962.57")
    assert loan_summary.aggregate_interest_paid == Decimal("119.07")


def test_get_loan_summary(db_session):
    test_data = insert_test_data(db_session)

    response = client.get(f"/loan/{test_data['loan'][0].id}/summary?month_number=1")

    assert response.status_code == 200
    data = response.json()
    assert data["current_principal_balance"] == 9178.06
    assert data["aggregate_principal_paid"] == 821.94
    assert data["aggregate_interest_paid"] == 25

    response = client.get(f"/loan/{test_data['loan'][0].id}/summary?month_number=6")

    assert response.status_code == 200
    data = response.json()
    assert data["current_principal_balance"] == 5037.43
    assert data["aggregate_principal_paid"] == 4962.57
    assert data["aggregate_interest_paid"] == 119.07

    response = client.get(f"/loan/999/summary?month_number=6")
    assert response.status_code == 404


def test_get_user_loans(db_session):
    test_data = insert_test_data(db_session)

    response = client.get(f"/user/{test_data['user'][0].id}/loans")

    data = response.json()
    data = sorted(data, key=lambda x: x["id"])  # retuend list is unordered

    assert data[0] == {
        "annual_interest_rate": 3.0,
        "amount": 10000.0,
        "loan_term": 12,
        "id": test_data["loan"][0].id,
    }
    assert data[1] == {
        "annual_interest_rate": 6.0,
        "amount": 20000.0,
        "loan_term": 24,
        "id": test_data["loan"][1].id,
    }

    response = client.get(f"/user/{test_data['user'][1].id}/loans")
    data = response.json()
    assert data[0] == {
        "annual_interest_rate": 6.0,
        "amount": 20000.0,
        "loan_term": 24,
        "id": test_data["loan"][1].id,
    }

    response = client.get(f"/user/{test_data['user'][2].id}/loans")
    data = response.json()
    assert data == []

    response = client.get(f"/user/999/loans")
    assert response.status_code == 404


def test_share_loan(db_session):
    test_data = insert_test_data(db_session)
    response = client.get(f"/user/{test_data['user'][2].id}/loans")
    data = response.json()
    assert data == []

    response = client.post(
        f"/loan/{test_data['loan'][1].id}/share", json=[test_data["user"][2].id]
    )
    assert response.status_code == 200
    response = client.get(f"/user/{test_data['user'][2].id}/loans")
    data = response.json()
    assert data[0] == {
        "annual_interest_rate": 6.0,
        "amount": 20000.0,
        "loan_term": 24,
        "id": test_data["loan"][1].id,
    }

    # bad loan id
    response = client.post(f"/loan/999/share", json=[test_data["user"][2].id])
    assert response.status_code == 404

    # bad user id
    response = client.post(f"/loan/{test_data['loan'][1].id}/share", json=[999])
    assert response.status_code == 404
