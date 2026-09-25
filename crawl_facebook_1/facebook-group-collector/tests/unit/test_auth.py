"""
tests/unit/test_auth.py — Tests for Facebook authentication detection and AccountManager.
All tests use mocked Playwright Page objects (no network calls, fast & deterministic).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from collector.facebook.auth import AccountManager, AuthStatus, check_auth_status
from collector.facebook.selectors import AuthSelectors


class MockPage:
    def __init__(self, url: str, has_c_user: bool = True):
        self.url = url
        self._selectors = {}
        self.context = MagicMock()
        cookies = [{"name": "c_user", "value": "100012345678"}] if has_c_user else []
        self.context.cookies = AsyncMock(return_value=cookies)

    def set_selector(self, selector: str, element):
        self._selectors[selector] = element

    async def query_selector(self, selector: str):
        return self._selectors.get(selector, None)


# ---------------------------------------------------------------------------
# AuthStatus Detection Tests (URL-based)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_status_ok_feed():
    page = MockPage(url="https://www.facebook.com/groups/techvietnam/")
    status = await check_auth_status(page)
    assert status == AuthStatus.OK


@pytest.mark.asyncio
async def test_auth_status_login_required_url():
    page = MockPage(url="https://www.facebook.com/login.php?next=...")
    status = await check_auth_status(page)
    assert status == AuthStatus.LOGIN_REQUIRED


@pytest.mark.asyncio
async def test_auth_status_checkpoint_url():
    page = MockPage(url="https://www.facebook.com/checkpoint/?next=...")
    status = await check_auth_status(page)
    assert status == AuthStatus.CHECKPOINT


@pytest.mark.asyncio
async def test_auth_status_mfa_url():
    page = MockPage(url="https://www.facebook.com/two_step_verification/two-factor")
    status = await check_auth_status(page)
    assert status == AuthStatus.MFA


# ---------------------------------------------------------------------------
# AuthStatus Detection Tests (DOM-based)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_status_dom_login_form():
    page = MockPage(url="https://www.facebook.com/")
    page.set_selector(AuthSelectors.LOGIN_FORM, MagicMock())
    status = await check_auth_status(page)
    assert status == AuthStatus.LOGIN_REQUIRED


@pytest.mark.asyncio
async def test_auth_status_dom_checkpoint():
    page = MockPage(url="https://www.facebook.com/")
    page.set_selector(AuthSelectors.CHECKPOINT_INDICATOR, MagicMock())
    status = await check_auth_status(page)
    assert status == AuthStatus.CHECKPOINT


@pytest.mark.asyncio
async def test_auth_status_dom_mfa():
    page = MockPage(url="https://www.facebook.com/")
    page.set_selector(AuthSelectors.MFA_PROMPT, MagicMock())
    status = await check_auth_status(page)
    assert status == AuthStatus.MFA


@pytest.mark.asyncio
async def test_auth_status_unknown_url():
    page = MockPage(url="https://example.com/not-fb")
    status = await check_auth_status(page)
    assert status == AuthStatus.UNKNOWN


# ---------------------------------------------------------------------------
# AccountManager Tests (Multi-account switching)
# ---------------------------------------------------------------------------

def test_account_manager_path_resolution(tmp_path: Path):
    mgr = AccountManager(base_dir=tmp_path)

    # Default account
    p_default = mgr.get_state_path("default")
    assert p_default == tmp_path / "default.json"

    # Custom named account
    p_acc1 = mgr.get_state_path("backup_account")
    assert p_acc1 == tmp_path / "backup_account.json"

    # Email address sanitized to safe filename
    p_email = mgr.get_state_path("ngohoangkhoi02@gmail.com")
    assert p_email.suffix == ".json"
    assert "@" not in p_email.name
    assert "ngohoangkhoi02" in p_email.name


def test_account_manager_has_session_and_listing(tmp_path: Path):
    mgr = AccountManager(base_dir=tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)

    assert not mgr.has_session("acc1")
    assert mgr.list_accounts() == []

    # Write a session file
    state_file = mgr.get_state_path("acc1")
    state_file.write_text('{"cookies": []}')

    assert mgr.has_session("acc1")
    assert "acc1" in mgr.list_accounts()

    # Empty file does not count as active session
    empty_file = mgr.get_state_path("acc_empty")
    empty_file.write_text("")
    assert not mgr.has_session("acc_empty")
