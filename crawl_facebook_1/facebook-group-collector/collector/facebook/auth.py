"""
collector/facebook/auth.py — Authentication state detector & account session manager.

Supports:
- Detecting auth status from URL patterns and DOM selectors:
  OK, LOGIN_REQUIRED, CHECKPOINT, MFA, UNKNOWN
- Multi-account management: each account stores its browser session in
  data/browser_state/{account_name}.json
- Flexible switching: user can change accounts or add fallback accounts if an account is banned.
"""
from __future__ import annotations

import asyncio
from enum import Enum
import logging
from pathlib import Path
from typing import Optional

from collector.facebook.selectors import AuthSelectors

logger = logging.getLogger(__name__)


class AuthStatus(str, Enum):
    OK = "OK"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    CHECKPOINT = "CHECKPOINT"
    MFA = "MFA"
    UNKNOWN = "UNKNOWN"


class AccountManager:
    """Manages browser session states for multiple Facebook accounts."""

    def __init__(self, base_dir: str | Path = "data/browser_state"):
        self.base_dir = Path(base_dir)

    def get_state_path(self, account_name: str = "default") -> Path:
        """Resolve session JSON file path for an account."""
        # Sanitize account name (e.g. replace @ or / or spaces)
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in account_name).strip("_")
        if not safe_name:
            safe_name = "default"
        return self.base_dir / f"{safe_name}.json"

    def has_session(self, account_name: str = "default") -> bool:
        """Check if a session state file exists for the account."""
        path = self.get_state_path(account_name)
        return path.exists() and path.stat().st_size > 0

    def list_accounts(self) -> list[str]:
        """List all accounts that have saved sessions."""
        if not self.base_dir.exists():
            return []
        return [f.stem for f in self.base_dir.glob("*.json") if f.stat().st_size > 0]


async def check_auth_status(page) -> AuthStatus:
    """
    Check Facebook authentication status for a given page.
    Never raises exceptions — returns AuthStatus enum.

    Detection strategy:
      1. Check URL patterns (fastest & most reliable for redirects)
      2. Check DOM selectors (login form, checkpoint indicator, 2fa, profile icon)
    """
    try:
        url = page.url.lower()
        logger.debug("Auth check: current URL = %s", url)

        # 1. URL pattern detection
        if "/checkpoint" in url:
            logger.warning("Auth check: Facebook CHECKPOINT detected at %s", url)
            return AuthStatus.CHECKPOINT

        if any(p in url for p in ["/two_step", "/two-step", "approvals_code", "2fa"]):
            logger.warning("Auth check: Facebook MFA/2FA prompt detected at %s", url)
            return AuthStatus.MFA

        if any(p in url for p in ["/login", "/login.php", "/recover", "/session/expired"]):
            logger.info("Auth check: Login page URL detected at %s", url)
            return AuthStatus.LOGIN_REQUIRED

        # If not on Facebook at all, return UNKNOWN
        if "facebook.com" not in url:
            return AuthStatus.UNKNOWN

        # 2. DOM selector check for error states first (checkpoint, MFA, login form)
        try:
            checkpoint = await page.query_selector(AuthSelectors.CHECKPOINT_INDICATOR)
            if checkpoint:
                logger.warning("Auth check: Checkpoint selector matched")
                return AuthStatus.CHECKPOINT
        except Exception:
            pass

        try:
            mfa = await page.query_selector(AuthSelectors.MFA_PROMPT)
            if mfa:
                logger.warning("Auth check: MFA selector matched")
                return AuthStatus.MFA
        except Exception:
            pass

        try:
            login_form = await page.query_selector(AuthSelectors.LOGIN_FORM)
            if login_form:
                # If element has is_visible method, check visibility, else consider present
                is_vis = login_form.is_visible() if hasattr(login_form, "is_visible") else True
                if asyncio.iscoroutine(is_vis):
                    is_vis = await is_vis
                if is_vis:
                    logger.info("Auth check: Login form selector matched")
                    return AuthStatus.LOGIN_REQUIRED
        except Exception:
            pass

        # 3. Check cookies: c_user is Facebook's definitive user session cookie
        try:
            cookies = await page.context.cookies()
            has_c_user = any(c.get("name") == "c_user" and c.get("value") for c in cookies)
            if has_c_user:
                logger.debug("Auth check: c_user cookie found — session is active")
                return AuthStatus.OK
        except Exception as e:
            logger.debug("Cookie check failed: %s", e)

        # 4. DOM selector check — profile / logged in indicators
        try:
            logged_in_el = await page.query_selector(AuthSelectors.LOGGED_IN_INDICATOR)
            if logged_in_el:
                logger.debug("Auth check: Logged-in indicator found — OK")
                return AuthStatus.OK
        except Exception:
            pass

        # If on facebook.com without c_user cookie and no positive logged_in element, it's not authenticated
        logger.info("Auth check: On facebook.com without c_user cookie or profile indicator -> LOGIN_REQUIRED")
        return AuthStatus.LOGIN_REQUIRED

        return AuthStatus.UNKNOWN

    except Exception as e:
        logger.error("Error during auth status check: %s", e)
        return AuthStatus.UNKNOWN


async def login_and_save_session(
    page,
    account_name: str = "default",
    email: Optional[str] = None,
    password: Optional[str] = None,
    state_path: Optional[str | Path] = None,
    timeout_seconds: int = 300,
) -> tuple[bool, Path]:
    """
    Automate or assist Facebook login and save the resulting session.

    Args:
        page: Playwright Page instance
        account_name: Name of the account profile
        email: Optional account email/phone
        password: Optional account password
        state_path: Custom state path; if None, defaults to data/browser_state/{account_name}.json
        timeout_seconds: Max seconds to wait for login completion (useful for 2FA/checkpoint)

    Returns:
        (success: bool, saved_path: Path)
    """
    account_mgr = AccountManager()
    resolved_path = Path(state_path) if state_path else account_mgr.get_state_path(account_name)

    logger.info("Navigating to Facebook login page...")
    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
    await asyncio.sleep(2)

    initial_status = await check_auth_status(page)
    if initial_status == AuthStatus.OK:
        logger.info("Session is already active and authenticated!")
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        await page.context.storage_state(path=str(resolved_path))
        return True, resolved_path

    # If email and password are provided, attempt autofill
    if email and password:
        logger.info("Attempting auto-fill credentials for %s...", email)
        try:
            # Wait for email input
            email_el = await page.wait_for_selector(AuthSelectors.EMAIL_INPUT, timeout=5000)
            if email_el:
                await email_el.fill(email)
                await asyncio.sleep(0.5)

            pass_el = await page.query_selector(AuthSelectors.PASSWORD_INPUT)
            if pass_el:
                await pass_el.fill(password)
                await asyncio.sleep(0.5)

            login_btn = await page.query_selector(AuthSelectors.LOGIN_BUTTON)
            if login_btn:
                logger.info("Submitting login form...")
                await login_btn.click()
                await asyncio.sleep(3)
        except Exception as e:
            logger.warning("Auto-fill attempt encountered an issue: %s. Continuing...", e)

    # Monitor status loop until OK or timeout
    logger.info("Waiting for authenticated session (timeout: %ds)...", timeout_seconds)
    print(f"\n[FB Auth] Account profile: '{account_name}'")
    print("[FB Auth] If prompted for 2FA, approval code, or security checkpoint, please complete it in the browser window.\n")

    start_time = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
        status = await check_auth_status(page)
        if status == AuthStatus.OK:
            logger.info("Login confirmed! Saving session...")
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            await page.context.storage_state(path=str(resolved_path))
            print(f"[FB Auth] Successfully authenticated and saved session to: {resolved_path}\n")
            return True, resolved_path

        if status == AuthStatus.CHECKPOINT:
            print("[FB Auth] Checkpoint detected! Please approve/verify in the browser window...", end="\r", flush=True)
        elif status == AuthStatus.MFA:
            print("[FB Auth] 2FA / Approval code requested! Please enter it in the browser...", end="\r", flush=True)

        await asyncio.sleep(2)

    logger.error("Authentication timed out after %ds", timeout_seconds)
    return False, resolved_path

