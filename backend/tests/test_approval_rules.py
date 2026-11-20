from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import ApprovalRequest, User
from app.rules.business import BusinessRuleError, enforce_outbound_rules
from app.tools.base import ToolContext, tool_registry
from tests.conftest import auth_header


def test_discount_cap_is_enforced_in_code() -> None:
    ok = enforce_outbound_rules(
        "price_offer",
        {"deal_title": "ورق", "amount": 1000, "discount_percent": 15},
        max_discount_percent=15,
    )
    assert ok["discount_percent"] == 15
    with pytest.raises(BusinessRuleError) as over:
        enforce_outbound_rules(
            "price_offer",
            {"deal_title": "ورق", "amount": 1000, "discount_percent": 15.1},
            max_discount_percent=15,
        )
    assert over.value.code == "max_discount_exceeded"
    with pytest.raises(BusinessRuleError) as negative:
        enforce_outbound_rules(
            "price_offer",
            {"deal_title": "ورق", "discount_percent": -1},
        )
    assert negative.value.code == "invalid_discount"


def test_email_and_unknown_actions() -> None:
    enforce_outbound_rules(
        "email",
        {"to": "buyer@example.com", "subject": "سلام", "body": "متن"},
    )
    with pytest.raises(BusinessRuleError) as bad_email:
        enforce_outbound_rules("email", {"to": "not-an-email", "subject": "سلام", "body": "متن"})
    assert bad_email.value.code == "invalid_email"
    with pytest.raises(BusinessRuleError) as unknown:
        enforce_outbound_rules("wire_transfer", {"amount": 10})
    assert unknown.value.code == "unknown_outbound_action"


def test_outbound_tool_records_approval_and_does_not_execute(client) -> None:  # noqa: ARG001
    from app.database import open_session

    db = open_session()
    try:
        user = db.scalar(select(User))
        assert user is not None
        before = db.scalar(select(func.count()).select_from(ApprovalRequest)) or 0
        blocked = tool_registry.get("propose_price").execute(
            {
                "deal_title": "قرارداد",
                "amount": 5000,
                "currency": "IRR",
                "discount_percent": 40,
            },
            ToolContext(user_id=user.id, db=db),
        )
        assert blocked.ok is False
        assert blocked.approval_id is None
        assert blocked.data["code"] == "max_discount_exceeded"
        result = tool_registry.get("send_email").execute(
            {"to": "buyer@example.com", "subject": "پیشنهاد", "body": "سلام"},
            ToolContext(user_id=user.id, db=db),
        )
        db.commit()
        assert result.approval_required is True
        row = db.get(ApprovalRequest, result.approval_id)
        assert row is not None
        assert row.status == "pending"
        assert row.execution_status == "not_started"
        after = db.scalar(select(func.count()).select_from(ApprovalRequest)) or 0
        assert after == before + 1
    finally:
        db.close()


def test_api_blocks_over_cap_and_executes_only_after_approval(client) -> None:
    headers = auth_header(client)
    rejected = client.post(
        "/api/approvals",
        headers=headers,
        json={
            "action_type": "price_offer",
            "payload": {"deal_title": "ورق", "amount": 1000, "discount_percent": 40},
        },
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "max_discount_exceeded"

    created = client.post(
        "/api/approvals",
        headers=headers,
        json={
            "action_type": "price_offer",
            "payload": {
                "deal_title": "ورق",
                "amount": 1000,
                "currency": "IRR",
                "discount_percent": 10,
            },
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["execution_status"] == "not_started"

    denied = client.post(
        "/api/users",
        headers=headers,
        json={
            "email": "buyer2@example.com",
            "password": "sales12345",
            "full_name": "کارشناس فروش",
            "role": "sales",
        },
    )
    assert denied.status_code == 201
    sales = auth_header(client, "buyer2@example.com", "sales12345")
    forbidden = client.post(
        f"/api/approvals/{body['id']}/decide",
        headers=sales,
        json={"decision": "approved"},
    )
    assert forbidden.status_code == 403

    decided = client.post(
        f"/api/approvals/{body['id']}/decide",
        headers=headers,
        json={"decision": "approved", "note": "مورد تأیید است"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"
    assert decided.json()["execution_status"] == "executed"
