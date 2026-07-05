"""Rate-limit middleware: session doc cap and IP daily upload cap."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.ingestion.errors import IngestValidationError
from backend.middleware.rate_limit import check_and_increment_ip_upload, check_session_doc_limit


def _redis_with(smembers=None, incr_sequence=None):
    redis = AsyncMock()
    redis.smembers = AsyncMock(return_value=smembers or [])
    if incr_sequence is not None:
        redis.incr = AsyncMock(side_effect=incr_sequence)
    redis.expire = AsyncMock()
    return redis


async def test_session_under_limit_passes():
    redis = _redis_with(smembers=["a", "b"])  # MAX_DOCS_PER_SESSION default is 3
    with patch("backend.middleware.rate_limit.get_redis", return_value=redis):
        await check_session_doc_limit("sess-1")  # must not raise


async def test_session_at_limit_is_rejected():
    redis = _redis_with(smembers=["a", "b", "c"])
    with patch("backend.middleware.rate_limit.get_redis", return_value=redis):
        with pytest.raises(IngestValidationError) as exc_info:
            await check_session_doc_limit("sess-1")
    assert exc_info.value.error == "too_many_documents"
    assert exc_info.value.status_code == 400


async def test_ip_first_upload_sets_ttl():
    redis = _redis_with(incr_sequence=[1])
    with patch("backend.middleware.rate_limit.get_redis", return_value=redis):
        await check_and_increment_ip_upload("1.2.3.4")
    redis.expire.assert_awaited_once()


async def test_ip_under_limit_does_not_set_ttl_again():
    redis = _redis_with(incr_sequence=[5])  # default MAX_UPLOADS_PER_IP_DAY is 10
    with patch("backend.middleware.rate_limit.get_redis", return_value=redis):
        await check_and_increment_ip_upload("1.2.3.4")
    redis.expire.assert_not_awaited()


async def test_ip_over_limit_is_rejected():
    redis = _redis_with(incr_sequence=[11])
    with patch("backend.middleware.rate_limit.get_redis", return_value=redis):
        with pytest.raises(IngestValidationError) as exc_info:
            await check_and_increment_ip_upload("1.2.3.4")
    assert exc_info.value.error == "upload_limit_exceeded"
    assert exc_info.value.status_code == 429


async def test_session_check_degrades_open_on_redis_outage():
    redis = AsyncMock()
    redis.smembers = AsyncMock(side_effect=ConnectionError("redis unreachable"))
    with patch("backend.middleware.rate_limit.get_redis", return_value=redis):
        await check_session_doc_limit("sess-1")  # must not raise


async def test_ip_check_degrades_open_on_redis_outage():
    redis = AsyncMock()
    redis.incr = AsyncMock(side_effect=ConnectionError("redis unreachable"))
    with patch("backend.middleware.rate_limit.get_redis", return_value=redis):
        await check_and_increment_ip_upload("1.2.3.4")  # must not raise
