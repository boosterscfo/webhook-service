"""
웹훅 테스트

- 웹훅 라우팅 (job/function 분기)
- HMAC-SHA256 서명 인증
- 레거시 X-Webhook-Token 인증 (하위 호환)
- payload 필수 필드 검증
"""

import hashlib
import hmac
import json
import time

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

VALID_TOKEN = "test-webhook-token-12345"
VALID_SECRET = "test-webhook-secret-67890"


@pytest.fixture(autouse=True)
def mock_webhook_settings():
    """모든 테스트에서 WEBHOOK_TOKEN, WEBHOOK_SECRET을 고정값으로 설정"""
    with patch("app.dependencies.settings") as mock_settings:
        mock_settings.WEBHOOK_TOKEN = VALID_TOKEN
        mock_settings.WEBHOOK_SECRET = VALID_SECRET
        yield


def _make_hmac_headers(body: str, secret: str = VALID_SECRET, timestamp: int = None):
    """HMAC-SHA256 서명 헤더 생성 헬퍼"""
    ts = str(timestamp or int(time.time()))
    sig_basestring = f"{ts}.{body}"
    signature = hmac.new(
        secret.encode("utf-8"),
        sig_basestring.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Webhook-Timestamp": ts,
        "X-Webhook-Signature": f"sha256={signature}",
        "Content-Type": "application/json",
    }


# ===== HMAC 인증 테스트 =====


def test_hmac_auth_success():
    """HMAC-SHA256 서명이 올바르면 정상 처리"""
    with patch("app.router.execute_job") as mock_execute:
        mock_execute.return_value = "ok"

        payload = {"job": "cash_mgmt", "function": "banktransactionUpload"}
        body = json.dumps(payload)
        headers = _make_hmac_headers(body)

        response = client.post("/webhook", content=body, headers=headers)

        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_hmac_auth_invalid_signature():
    """잘못된 서명이면 401 반환"""
    payload = {"job": "cash_mgmt", "function": "banktransactionUpload"}
    body = json.dumps(payload)

    response = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Webhook-Timestamp": str(int(time.time())),
            "X-Webhook-Signature": "sha256=invalid_signature",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid signature"


def test_hmac_auth_expired_timestamp():
    """타임스탬프가 5분 이상 지났으면 401 반환"""
    payload = {"job": "cash_mgmt", "function": "banktransactionUpload"}
    body = json.dumps(payload)
    old_ts = int(time.time()) - 600  # 10분 전
    headers = _make_hmac_headers(body, timestamp=old_ts)

    response = client.post("/webhook", content=body, headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Request expired"


def test_hmac_auth_tampered_body():
    """서명 후 body가 변조되면 401 반환"""
    original = {"job": "cash_mgmt", "function": "banktransactionUpload"}
    tampered = {"job": "cash_mgmt", "function": "banktransactionUpload", "extra": "hacked"}

    headers = _make_hmac_headers(json.dumps(original))

    response = client.post(
        "/webhook",
        content=json.dumps(tampered),
        headers=headers,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid signature"


# ===== 레거시 토큰 인증 테스트 =====


def test_legacy_token_auth_success():
    """레거시 X-Webhook-Token이 올바르면 정상 처리"""
    with patch("app.router.execute_job") as mock_execute:
        mock_execute.return_value = "result: 100 records upserted"

        response = client.post(
            "/webhook",
            json={"job": "cash_mgmt", "function": "banktransactionUpload"},
            headers={"X-Webhook-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "result" in data


def test_legacy_token_auth_invalid():
    """잘못된 X-Webhook-Token이면 401 반환"""
    response = client.post(
        "/webhook",
        json={"job": "cash_mgmt", "function": "banktransactionUpload"},
        headers={"X-Webhook-Token": "wrong-token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid webhook token"


def test_no_auth_headers():
    """인증 헤더가 없으면 401 반환"""
    response = client.post(
        "/webhook",
        json={"job": "cash_mgmt", "function": "banktransactionUpload"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


# ===== 라우팅 / payload 검증 =====


def test_webhook_requires_job_and_function():
    """job 또는 function이 없으면 400 반환"""
    for payload in [
        {},
        {"job": "cash_mgmt"},
        {"function": "banktransactionUpload"},
    ]:
        response = client.post(
            "/webhook",
            json=payload,
            headers={"X-Webhook-Token": VALID_TOKEN},
        )
        assert response.status_code == 400


def test_webhook_rejects_unknown_job():
    """존재하지 않는 job이면 400 반환"""
    with patch("app.router.execute_job") as mock_execute:
        mock_execute.side_effect = ValueError("Unknown job: unknown_job")

        response = client.post(
            "/webhook",
            json={"job": "unknown_job", "function": "banktransactionUpload"},
            headers={"X-Webhook-Token": VALID_TOKEN},
        )

        assert response.status_code == 400


def test_webhook_rejects_unknown_function():
    """존재하지 않는 function이면 400 반환"""
    with patch("app.router.execute_job") as mock_execute:
        mock_execute.side_effect = ValueError(
            "Unknown function: cash_mgmt.invalidFunc"
        )

        response = client.post(
            "/webhook",
            json={"job": "cash_mgmt", "function": "invalidFunc"},
            headers={"X-Webhook-Token": VALID_TOKEN},
        )

        assert response.status_code == 400


def test_health_endpoint():
    """/health 엔드포인트 확인"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
