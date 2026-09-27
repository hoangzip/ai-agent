"""
scripts/auto_login_new_acc.py — Automatically log into Facebook with new account credentials.
Opens a visible Chrome window, types the credentials, and captures storage state.
If 2FA (mã xác nhận / phê duyệt đăng nhập) is required, it keeps the browser open
and waits for the user to complete 2FA.
"""
import asyncio
import os
import sys
from pathlib import Path
import logging

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import load_config
from collector.facebook.browser import BrowserFactory
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("auto_login")

async def main():
    email = os.environ.get("FB_EMAIL", "aitruongpro123@gmail.com")
    password = os.environ.get("FB_PASSWORD", "Testing12345!")
    state_file = Path("data/browser_state/default.json")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    
    config = load_config("config/crawler.yaml")
    
    logger.info("Starting login process for account: %s", email)
    
    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser, headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 850},
            locale="vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            timezone_id="Asia/Ho_Chi_Minh",
        )
        page = await context.new_page()
        
        logger.info("Opening https://www.facebook.com/login ...")
        await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        # Check if already logged in
        cookies = await context.cookies()
        c_user = next((c for c in cookies if c.get("name") == "c_user"), None)
        if not c_user:
            logger.info("Filling in email and password...")
            email_input = await page.query_selector("input#email, input[name='email']")
            pass_input = await page.query_selector("input#pass, input[name='pass']")
            login_btn = await page.query_selector("button#loginbutton, button[name='login']")
            
            if email_input and pass_input:
                await email_input.fill(email)
                await asyncio.sleep(0.5)
                await pass_input.fill(password)
                await asyncio.sleep(0.5)
                login_btn = await page.query_selector("button#loginbutton, button[name='login'], button[type='submit'], div[aria-label='Log In'], div[aria-label='Đăng nhập']")
                if login_btn:
                    logger.info("Clicking Log In button...")
                    await login_btn.click()
                else:
                    logger.info("Pressing Enter on password input...")
                    await pass_input.press("Enter")
                    
                await asyncio.sleep(3)
                logger.info("Current URL after submission: %s", page.url)
                err_el = await page.query_selector("div[role='alert'], #error_box, ._4rbf, div[aria-label*='Error'], div[aria-label*='Lỗi']")
                if err_el:
                    logger.warning("Facebook returned message: %s", (await err_el.inner_text()).strip())
            else:
                logger.warning("Could not find standard email/pass input fields. Waiting for manual entry if needed.")
                
        logger.info("Waiting for login completion / 2FA verification...")
        logger.info(">> NẾU FACEBOOK YÊU CẦU MÃ XÁC NHẬN (2FA) HOẶC PHÊ DUYỆT, BẠN VUI LÒNG THAO TÁC TRÊN CỬA SỔ CHROME VỪA MỞ <<")
        
        logged_in = False
        for i in range(150):  # 5 minutes
            await asyncio.sleep(2)
            cookies = await context.cookies()
            c_user = next((c for c in cookies if c.get("name") == "c_user"), None)
            xs = next((c for c in cookies if c.get("name") == "xs"), None)
            
            if c_user and xs:
                logger.info("Login detected! Waiting 3s for session tokens to stabilize...")
                await asyncio.sleep(3)
                await context.storage_state(path=str(state_file))
                logger.info("ĐĂNG NHẬP THÀNH CÔNG! UID = %s", c_user.get("value"))
                logger.info("Đã lưu session state thành công vào: %s", state_file.resolve())
                logged_in = True
                break
                
        if not logged_in:
            logger.error("Hết thời gian chờ đăng nhập (5 phút).")
        else:
            await asyncio.sleep(2)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
