import sys
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.main import app, Base
from app.database import engine, SessionLocal
from app.models import RefundLog, Booking

client = TestClient(app)

def _future(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(
        minute=0, second=0, microsecond=0
    ).isoformat()

def run_tests():
    # Setup user
    org = f"acme-{datetime.now().timestamp()}"
    client.post("/auth/register", json={"org_name": org, "username": "admin", "password": "pw"})
    login = client.post("/auth/login", json={"org_name": org, "username": "admin", "password": "pw"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    room_1 = client.post("/rooms", json={"name": "Room 1", "capacity": 4, "hourly_rate_cents": 35}, headers=headers).json()
    room_2 = client.post("/rooms", json={"name": "Room 2", "capacity": 4, "hourly_rate_cents": 1001}, headers=headers).json()
    room_3 = client.post("/rooms", json={"name": "Room 3", "capacity": 4, "hourly_rate_cents": 1000}, headers=headers).json()

    db = SessionLocal()
    
    b1 = client.post("/bookings", json={"room_id": room_1["id"], "start_time": _future(25), "end_time": _future(26)}, headers=headers).json()
    c1 = client.post(f"/bookings/{b1['id']}/cancel", headers=headers).json()
    assert c1["refund_percent"] == 50
    assert c1["refund_amount_cents"] == 18
    r1 = db.query(RefundLog).filter_by(booking_id=b1['id']).first()
    assert r1.amount_cents == 18
    print("Scenario 1 passed: 35 cents, 50% refund -> 18 cents")

    b2 = client.post("/bookings", json={"room_id": room_2["id"], "start_time": _future(25), "end_time": _future(26)}, headers=headers).json()
    c2 = client.post(f"/bookings/{b2['id']}/cancel", headers=headers).json()
    assert c2["refund_percent"] == 50
    assert c2["refund_amount_cents"] == 501
    r2 = db.query(RefundLog).filter_by(booking_id=b2['id']).first()
    assert r2.amount_cents == 501
    print("Scenario 2 passed: 1001 cents, 50% refund -> 501 cents")

    b3 = client.post("/bookings", json={"room_id": room_3["id"], "start_time": _future(12), "end_time": _future(13)}, headers=headers).json()
    c3 = client.post(f"/bookings/{b3['id']}/cancel", headers=headers).json()
    assert c3["refund_percent"] == 0
    assert c3["refund_amount_cents"] == 0
    r3 = db.query(RefundLog).filter_by(booking_id=b3['id']).first()
    assert r3.amount_cents == 0
    print("Scenario 3 passed: 1000 cents, 0% refund -> 0 cents")

    b4 = client.post("/bookings", json={"room_id": room_3["id"], "start_time": _future(50), "end_time": _future(51)}, headers=headers).json()
    c4 = client.post(f"/bookings/{b4['id']}/cancel", headers=headers).json()
    assert c4["refund_percent"] == 100
    assert c4["refund_amount_cents"] == 1000
    r4 = db.query(RefundLog).filter_by(booking_id=b4['id']).first()
    assert r4.amount_cents == 1000
    print("Scenario 4 passed: 1000 cents, 100% refund -> 1000 cents")

if __name__ == '__main__':
    run_tests()
