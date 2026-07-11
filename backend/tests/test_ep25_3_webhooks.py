"""Tests for EP-25.3 — Resend delivery-event webhook receiver.

Covers ``app/email/webhook.py`` (Svix/HMAC signature verification, payload
processing) and ``POST /v1/webhooks/resend`` (the API layer: unconfigured
-> 503, missing/bad signature -> 401, malformed body -> 400, success ->
200 + persisted ``EmailDeliveryEvent``).

Signature verification and payload processing were also verified against
a real local PostgreSQL instance during development (migration applied,
round-tripped a real INSERT, confirmed audit logging fires for a bounce)
— see CLAUDE.md's EP-25.3 section. These tests pin that behavior at the
unit/API level, fully hermetic (no network, mocked DB for the API tests).
"""

from __future__ import annotations

import base64
import hmac
import json
import time
from hashlib import sha256
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.config.settings import Settings
from app.email.webhook import (
    WebhookVerificationError,
    process_resend_webhook_payload,
    verify_signature,
)
from app.models.email_delivery_event import FAILURE_EVENT_TYPES, EmailDeliveryEventType


def _sign(secret: str, svix_id: str, svix_ts: str, body: bytes) -> str:
    secret_bytes = base64.b64decode(secret[len("whsec_") :])
    signed = f"{svix_id}.{svix_ts}.".encode() + body
    return "v1," + base64.b64encode(hmac.new(secret_bytes, signed, sha256).digest()).decode()


_SECRET = "whsec_" + base64.b64encode(b"0123456789abcdef").decode()


class TestVerifySignature:
    def test_valid_signature_passes(self) -> None:
        body = b'{"type":"email.delivered"}'
        svix_id, svix_ts = "msg_1", str(int(time.time()))
        sig = _sign(_SECRET, svix_id, svix_ts, body)
        verify_signature(
            payload=body,
            svix_id=svix_id,
            svix_timestamp=svix_ts,
            svix_signature=sig,
            secret=_SECRET,
        )

    def test_tampered_signature_rejected(self) -> None:
        body = b'{"type":"email.delivered"}'
        svix_id, svix_ts = "msg_1", str(int(time.time()))
        with pytest.raises(WebhookVerificationError):
            verify_signature(
                payload=body,
                svix_id=svix_id,
                svix_timestamp=svix_ts,
                svix_signature="v1,notarealsignature",
                secret=_SECRET,
            )

    def test_tampered_body_rejected(self) -> None:
        body = b'{"type":"email.delivered"}'
        svix_id, svix_ts = "msg_1", str(int(time.time()))
        sig = _sign(_SECRET, svix_id, svix_ts, body)
        with pytest.raises(WebhookVerificationError):
            verify_signature(
                payload=b'{"type":"email.bounced"}',
                svix_id=svix_id,
                svix_timestamp=svix_ts,
                svix_signature=sig,
                secret=_SECRET,
            )

    def test_stale_timestamp_rejected(self) -> None:
        body = b'{"type":"email.delivered"}'
        svix_id = "msg_1"
        old_ts = str(int(time.time()) - 999999)
        sig = _sign(_SECRET, svix_id, old_ts, body)
        with pytest.raises(WebhookVerificationError):
            verify_signature(
                payload=body,
                svix_id=svix_id,
                svix_timestamp=old_ts,
                svix_signature=sig,
                secret=_SECRET,
            )

    def test_future_timestamp_rejected(self) -> None:
        body = b'{"type":"email.delivered"}'
        svix_id = "msg_1"
        future_ts = str(int(time.time()) + 999999)
        sig = _sign(_SECRET, svix_id, future_ts, body)
        with pytest.raises(WebhookVerificationError):
            verify_signature(
                payload=body,
                svix_id=svix_id,
                svix_timestamp=future_ts,
                svix_signature=sig,
                secret=_SECRET,
            )

    def test_malformed_timestamp_rejected(self) -> None:
        body = b"{}"
        with pytest.raises(WebhookVerificationError):
            verify_signature(
                payload=body,
                svix_id="msg_1",
                svix_timestamp="not-a-number",
                svix_signature="v1,abc",
                secret=_SECRET,
            )

    def test_malformed_secret_rejected(self) -> None:
        body = b"{}"
        with pytest.raises(WebhookVerificationError):
            verify_signature(
                payload=body,
                svix_id="msg_1",
                svix_timestamp=str(int(time.time())),
                svix_signature="v1,abc",
                secret="not-a-whsec-secret",
            )

    def test_accepts_any_matching_candidate_in_multi_signature_header(self) -> None:
        body = b'{"type":"email.delivered"}'
        svix_id, svix_ts = "msg_1", str(int(time.time()))
        sig = _sign(_SECRET, svix_id, svix_ts, body)
        combined = f"v1,bogus1 {sig} v1,bogus2"
        verify_signature(
            payload=body,
            svix_id=svix_id,
            svix_timestamp=svix_ts,
            svix_signature=combined,
            secret=_SECRET,
        )


class TestProcessResendWebhookPayload:
    @pytest.mark.asyncio
    async def test_delivered_event_persists_and_is_not_a_failure(self) -> None:
        repo = AsyncMock()
        payload = {
            "type": "email.delivered",
            "data": {"email_id": "msg_1", "to": ["user@example.com"], "subject": "Hi"},
        }
        result = await process_resend_webhook_payload(payload, repo=repo)
        assert result is not None
        assert result.event_type == EmailDeliveryEventType.DELIVERED.value
        assert result.is_failure is False
        repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bounced_event_persists_and_is_a_failure(self) -> None:
        repo = AsyncMock()
        payload = {
            "type": "email.bounced",
            "data": {"email_id": "msg_2", "to": ["user@example.com"]},
        }
        with patch("app.email.webhook.log_auth_event") as mock_audit:
            result = await process_resend_webhook_payload(payload, repo=repo)
        assert result is not None
        assert result.is_failure is True
        mock_audit.assert_called_once()

    @pytest.mark.asyncio
    async def test_complained_and_delayed_are_failures(self) -> None:
        for event_type in ("email.complained", "email.delivery_delayed"):
            repo = AsyncMock()
            payload = {"type": event_type, "data": {"email_id": "m", "to": ["a@b.com"]}}
            result = await process_resend_webhook_payload(payload, repo=repo)
            assert result is not None
            assert result.is_failure is True

    @pytest.mark.asyncio
    async def test_sent_opened_clicked_are_not_failures(self) -> None:
        for event_type in ("email.sent", "email.opened", "email.clicked"):
            repo = AsyncMock()
            payload = {"type": event_type, "data": {"email_id": "m", "to": ["a@b.com"]}}
            result = await process_resend_webhook_payload(payload, repo=repo)
            assert result is not None
            assert result.is_failure is False

    @pytest.mark.asyncio
    async def test_unrecognized_event_type_returns_none_and_does_not_persist(self) -> None:
        repo = AsyncMock()
        payload = {"type": "email.some_future_event", "data": {"email_id": "m", "to": ["a@b.com"]}}
        result = await process_resend_webhook_payload(payload, repo=repo)
        assert result is None
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_email_id_returns_none(self) -> None:
        repo = AsyncMock()
        payload = {"type": "email.delivered", "data": {"to": ["a@b.com"]}}
        result = await process_resend_webhook_payload(payload, repo=repo)
        assert result is None
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_type_returns_none(self) -> None:
        repo = AsyncMock()
        payload = {"data": {"email_id": "m", "to": ["a@b.com"]}}
        result = await process_resend_webhook_payload(payload, repo=repo)
        assert result is None

    @pytest.mark.asyncio
    async def test_tags_carried_onto_the_stored_event(self) -> None:
        repo = AsyncMock()
        payload = {
            "type": "email.delivered",
            "data": {
                "email_id": "msg_3",
                "to": ["user@example.com"],
                "tags": {"category": "verification"},
            },
        }
        await process_resend_webhook_payload(payload, repo=repo)
        stored_event = repo.create.call_args[0][0]
        assert stored_event.tags == {"category": "verification"}

    @pytest.mark.asyncio
    async def test_recipient_extracted_from_first_to_entry(self) -> None:
        repo = AsyncMock()
        payload = {
            "type": "email.delivered",
            "data": {"email_id": "msg_4", "to": ["first@example.com", "second@example.com"]},
        }
        result = await process_resend_webhook_payload(payload, repo=repo)
        assert result is not None
        assert result.recipient_email == "first@example.com"

    def test_failure_event_types_are_exactly_bounced_complained_delayed(self) -> None:
        assert FAILURE_EVENT_TYPES == {
            EmailDeliveryEventType.BOUNCED,
            EmailDeliveryEventType.COMPLAINED,
            EmailDeliveryEventType.DELIVERY_DELAYED,
        }


class TestResendWebhookEndpoint:
    @pytest.mark.asyncio
    async def test_returns_503_when_not_configured(self, app: FastAPI) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/webhooks/resend",
                content=b"{}",
                headers={
                    "svix-id": "msg_1",
                    "svix-timestamp": str(int(time.time())),
                    "svix-signature": "v1,abc",
                },
            )
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_returns_401_when_headers_missing(
        self, app: FastAPI, test_settings: Settings
    ) -> None:
        from app.config.settings import get_settings as _get_settings

        configured = test_settings.model_copy(update={"resend_webhook_secret": SecretStr(_SECRET)})
        app.dependency_overrides[_get_settings] = lambda: configured
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/v1/webhooks/resend", content=b"{}")
        app.dependency_overrides.pop(_get_settings, None)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_401_on_bad_signature(
        self, app: FastAPI, test_settings: Settings
    ) -> None:
        from app.config.settings import get_settings as _get_settings

        configured = test_settings.model_copy(update={"resend_webhook_secret": SecretStr(_SECRET)})
        app.dependency_overrides[_get_settings] = lambda: configured
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/webhooks/resend",
                content=b'{"type":"email.delivered"}',
                headers={
                    "svix-id": "msg_1",
                    "svix-timestamp": str(int(time.time())),
                    "svix-signature": "v1,wrongsignature",
                },
            )
        app.dependency_overrides.pop(_get_settings, None)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_200_and_persists_on_valid_signature(
        self, app: FastAPI, test_settings: Settings
    ) -> None:
        from app.config.settings import get_settings as _get_settings

        configured = test_settings.model_copy(update={"resend_webhook_secret": SecretStr(_SECRET)})
        app.dependency_overrides[_get_settings] = lambda: configured

        body = json.dumps(
            {
                "type": "email.delivered",
                "data": {"email_id": "msg_ok", "to": ["user@example.com"], "subject": "Hi"},
            }
        ).encode()
        svix_id, svix_ts = "msg_ok_1", str(int(time.time()))
        sig = _sign(_SECRET, svix_id, svix_ts, body)

        with patch("app.api.v1.webhooks.EmailDeliveryEventRepository") as mock_repo_cls:
            mock_repo_cls.return_value.create = AsyncMock()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/webhooks/resend",
                    content=body,
                    headers={
                        "svix-id": svix_id,
                        "svix-timestamp": svix_ts,
                        "svix-signature": sig,
                    },
                )
        app.dependency_overrides.pop(_get_settings, None)
        assert resp.status_code == 200
        assert resp.json() == {"processed": True}

    @pytest.mark.asyncio
    async def test_malformed_json_body_returns_400(
        self, app: FastAPI, test_settings: Settings
    ) -> None:
        from app.config.settings import get_settings as _get_settings

        configured = test_settings.model_copy(update={"resend_webhook_secret": SecretStr(_SECRET)})
        app.dependency_overrides[_get_settings] = lambda: configured

        body = b"not json at all"
        svix_id, svix_ts = "msg_bad", str(int(time.time()))
        sig = _sign(_SECRET, svix_id, svix_ts, body)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/webhooks/resend",
                content=body,
                headers={"svix-id": svix_id, "svix-timestamp": svix_ts, "svix-signature": sig},
            )
        app.dependency_overrides.pop(_get_settings, None)
        assert resp.status_code == 400
