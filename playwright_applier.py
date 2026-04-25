"""
Playwright-based Easy Apply bot for jobs.cz
Handles login, session management, and job applications.
"""

import os
import asyncio
import random
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class JobsCzApplier:
    """Handles automated job applications on jobs.cz"""

    def __init__(self):
        self.email = os.getenv("JOBSCZ_EMAIL")
        self.password = os.getenv("JOBSCZ_PASSWORD")
        self.cookies_file = Path("jobscz_cookies.json")
        self.screenshots_dir = Path("screenshots")
        self.screenshots_dir.mkdir(exist_ok=True)

        if not self.email or not self.password:
            raise ValueError("JOBSCZ_EMAIL and JOBSCZ_PASSWORD must be set in .env")

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def __aenter__(self):
        """Context manager entry - initialize browser"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup"""
        await self.close()

    async def start(self):
        """Initialize Playwright and browser"""
        self.playwright = await async_playwright().start()
        
        # Use stealth mode
        self.browser = await self.playwright.chromium.launch(
            headless=True,  # Set to True for production
            args=['--start-maximized']
        )
        
        # Create context with saved cookies if available
        if self.cookies_file.exists():
            logger.info("Loading saved cookies")
            self.context = await self.browser.new_context(
                storage_state=str(self.cookies_file),
                viewport={'width': 1920, 'height': 1080}
            )
        else:
            logger.info("No saved cookies found, will need to login")
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080}
            )

        self.page = await self.context.new_page()
        
        # Set realistic user agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15"
        ]
        await self.page.set_extra_http_headers({
            "User-Agent": random.choice(user_agents)
        })

    async def close(self):
        """Close browser and cleanup"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def _random_delay(self, min_seconds=1, max_seconds=3):
        """Add random delay between actions"""
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)

    async def login(self) -> bool:
        """
        Login to jobs.cz and save session cookies
        Returns: True if login successful, False otherwise
        """
        try:
            logger.info("Navigating to jobs.cz login page")
            await self.page.goto("https://www.jobs.cz/prihlasit-se/", wait_until="domcontentloaded")
            
            # Wait for network idle to ensure all resources are loaded
            await self.page.wait_for_load_state("networkidle")
            
            # Print debugging information
            logger.info(f"Current URL: {self.page.url}")
            logger.info(f"Page title: {await self.page.title()}")
            content_preview = (await self.page.content())[:500]
            logger.info(f"Page content preview: {content_preview}")
            
            # Check for CAPTCHA or iframe indicators
            captcha_indicators = [
                await self.page.query_selector('img[alt*="captcha"], img[src*="captcha"]'),
                await self.page.query_selector('div[class*="captcha"], div[id*="captcha"]'),
                await self.page.query_selector('iframe[src*="captcha"]')
            ]
            
            if any(captcha_indicators):
                logger.error("CAPTCHA detected on login page")
                await self._take_screenshot("captcha_detected")
                return False
            
            # Check for iframes
            frames = self.page.frames
            logger.info(f"Found {len(frames)} frames")
            for i, frame in enumerate(frames):
                logger.info(f"Frame {i}: {frame.url}")
            
            # Wait a bit for page to fully load
            await self._random_delay(1, 2)
            
            # Take screenshot of login page for debugging
            await self._take_screenshot("login_page")

            # Fill email/username field
            logger.info("Filling username field")
            email_selector = 'input[name="username"], input[type="email"], input[name="email"], input[id*="email"]'
            try:
                await self.page.wait_for_selector(email_selector, timeout=30000)
                await self.page.fill(email_selector, self.email)
                logger.info("Username field filled successfully")
            except Exception as e:
                logger.error(f"Failed to find username field with selector: {email_selector}")
                # Log available input fields for debugging
                page_html = await self.page.content()
                logger.error("Available input fields:")
                inputs = await self.page.query_selector_all('input')
                for inp in inputs:
                    inp_name = await inp.get_attribute('name')
                    inp_type = await inp.get_attribute('type')
                    inp_id = await inp.get_attribute('id')
                    logger.error(f"  - type={inp_type}, name={inp_name}, id={inp_id}")
                raise

            # Fill password field (labeled "Heslo")
            logger.info("Filling password field")
            password_selector = 'input[type="password"], input[name="password"]'
            try:
                await self.page.fill(password_selector, self.password)
                logger.info("Password field filled successfully")
            except Exception as e:
                logger.error(f"Failed to find password field with selector: {password_selector}")
                raise

            # Click login button "Přihlásit se"
            logger.info("Clicking login button")
            login_button_selector = 'button:has-text("Přihlásit se")'
            try:
                await self.page.wait_for_selector(login_button_selector, timeout=30000)
                await self.page.click(login_button_selector)
                logger.info("Login button clicked")
            except Exception as e:
                logger.error(f"Failed to find login button with selector: {login_button_selector}")
                # Log available buttons for debugging
                buttons = await self.page.query_selector_all('button')
                logger.error("Available buttons:")
                for btn in buttons:
                    btn_text = await btn.text_content()
                    btn_type = await btn.get_attribute('type')
                    logger.error(f"  - text={btn_text}, type={btn_type}")
                raise

            # Wait for navigation after login
            await self._random_delay(2, 3)

            # Check if login was successful by looking for user-specific elements
            # or checking if we're redirected away from login page
            current_url = self.page.url
            logger.info(f"Current URL after login attempt: {current_url}")

            if "prihlasit-se" not in current_url:
                logger.info("Login successful!")

                # Save cookies for future sessions
                await self.context.storage_state(path=str(self.cookies_file))
                logger.info(f"Cookies saved to {self.cookies_file}")

                return True
            else:
                logger.error("Login failed - still on login page")
                await self._take_screenshot("login_failed")
                return False

        except Exception as e:
            logger.error(f"Login error: {e}")
            await self._take_screenshot("login_error")
            return False

    async def check_logged_in(self) -> bool:
        """Check if currently logged in"""
        try:
            # Go to jobs.cz and check if we're logged in
            await self.page.goto("https://www.jobs.cz", wait_until="domcontentloaded")
            await self._random_delay(1, 2)

            # Look for login link - if it exists, we're not logged in
            login_link = await self.page.query_selector('a[href*="prihlasit-se"]')

            # Also check for user menu or account elements
            user_menu = await self.page.query_selector('[class*="user"], [class*="profile"], [data-testid*="user"]')

            is_logged_in = login_link is None or user_menu is not None
            logger.info(f"Login check: {'Logged in' if is_logged_in else 'Not logged in'}")

            return is_logged_in

        except Exception as e:
            logger.error(f"Error checking login status: {e}")
            return False

    async def ensure_logged_in(self) -> bool:
        """Ensure we're logged in, login if necessary"""
        if await self.check_logged_in():
            logger.info("Already logged in")
            return True

        logger.info("Not logged in, attempting login")
        return await self.login()

    async def apply_to_job(self, job_url: str, cover_letter_text: str) -> dict:
        """
        Apply to a job on jobs.cz

        Args:
            job_url: Full URL of the job posting
            cover_letter_text: Cover letter content to submit

        Returns:
            dict with keys: success (bool), message (str), screenshot_path (str)
        """
        result = {
            "success": False,
            "message": "",
            "screenshot_path": None
        }

        try:
            # Ensure we're logged in
            if not await self.ensure_logged_in():
                result["message"] = "Failed to login"
                return result

            # Navigate to job URL
            logger.info(f"Navigating to job: {job_url}")
            await self.page.goto(job_url, wait_until="domcontentloaded")
            await self._random_delay(1, 2)

            # Check if already applied
            already_applied = await self.page.query_selector('text=/již jste poslali|already applied/i')
            if already_applied:
                logger.info("Already applied to this job")
                result["success"] = True
                result["message"] = "Already applied"
                return result

            # Look for "Přihlásit se a poslat přihlášku" button
            logger.info("Looking for apply button")
            
            # Debug: print all buttons on page
            buttons = await self.page.query_selector_all('button')
            logger.info(f"Found {len(buttons)} buttons on page")
            for i, btn in enumerate(buttons[:10]):  # First 10
                text = await btn.inner_text()
                logger.info(f"Button {i}: {text}")

            # Also check for links that might be apply buttons
            links = await self.page.query_selector_all('a[href*="prihlasit"], a:has-text("Přihlásit"), a:has-text("Apply")')
            logger.info(f"Found {len(links)} potential apply links")
            for i, link in enumerate(links[:10]):
                text = await link.inner_text()
                logger.info(f"Link {i}: {text}")

            apply_button_selectors = [
                'button:has-text("Přihlásit se a poslat přihlášku")',
                'button:has-text("Poslat přihlášku")',
                'a:has-text("Přihlásit se a poslat přihlášku")',
                'a:has-text("Poslat přihlášku")',
                '[data-testid*="apply"]',
                'button[class*="apply"]'
            ]

            apply_button = None
            for selector in apply_button_selectors:
                apply_button = await self.page.query_selector(selector)
                if apply_button:
                    logger.info(f"Found apply button with selector: {selector}")
                    break

            if not apply_button:
                result["message"] = "Apply button not found"
                await self._take_screenshot("apply_button_not_found")
                result["screenshot_path"] = self._get_latest_screenshot()
                return result

            # Click apply button
            logger.info("Clicking apply button")
            await apply_button.click()
            await self._random_delay(1, 2)

            # Fill application form with cover letter
            logger.info("Looking for cover letter field")
            cover_letter_selectors = [
                'textarea[name*="cover"]',
                'textarea[name*="letter"]',
                'textarea[placeholder*="motivační"]',
                'textarea[id*="cover"]',
                'textarea[id*="letter"]',
                'textarea'  # Fallback to any textarea
            ]

            cover_letter_field = None
            for selector in cover_letter_selectors:
                cover_letter_field = await self.page.query_selector(selector)
                if cover_letter_field:
                    logger.info(f"Found cover letter field with selector: {selector}")
                    break

            if cover_letter_field:
                logger.info("Filling cover letter")
                await cover_letter_field.fill(cover_letter_text)
                await self._random_delay(0.5, 1)
            else:
                logger.warning("Cover letter field not found, proceeding without it")

            # Submit the form
            logger.info("Looking for submit button")
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Odeslat")',
                'button:has-text("Poslat")',
                'input[type="submit"]'
            ]

            submit_button = None
            for selector in submit_selectors:
                submit_button = await self.page.query_selector(selector)
                if submit_button:
                    logger.info(f"Found submit button with selector: {selector}")
                    break

            if not submit_button:
                result["message"] = "Submit button not found"
                await self._take_screenshot("submit_button_not_found")
                result["screenshot_path"] = self._get_latest_screenshot()
                return result

            # Take screenshot before submitting
            await self._take_screenshot("before_submit")

            # Click submit
            logger.info("Clicking submit button")
            await submit_button.click()
            await self._random_delay(2, 3)

            # Take screenshot after submission
            await self._take_screenshot("after_submit")

            # Check for success message or confirmation
            success_indicators = await self.page.query_selector('text=/úspěšně|success|odesláno|sent/i')

            if success_indicators:
                logger.info("Application submitted successfully!")
                result["success"] = True
                result["message"] = "Application submitted successfully"
            else:
                logger.warning("Could not confirm submission, but no errors detected")
                result["success"] = True
                result["message"] = "Application likely submitted (no confirmation message found)"

            result["screenshot_path"] = self._get_latest_screenshot()
            return result

        except Exception as e:
            logger.error(f"Error applying to job: {e}")
            result["message"] = f"Error: {str(e)}"
            await self._take_screenshot("application_error")
            result["screenshot_path"] = self._get_latest_screenshot()
            return result

    async def _take_screenshot(self, name: str):
        """Take a screenshot with timestamp"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.png"
            filepath = self.screenshots_dir / filename
            await self.page.screenshot(path=str(filepath), full_page=True)
            logger.info(f"Screenshot saved: {filepath}")
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")

    def _get_latest_screenshot(self) -> str:
        """Get path to most recent screenshot"""
        screenshots = sorted(self.screenshots_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        return str(screenshots[0]) if screenshots else None


async def test_login():
    """Test the login flow"""
    async with JobsCzApplier() as applier:
        success = await applier.login()
        if success:
            print("✓ Login successful!")
            print(f"✓ Cookies saved to {applier.cookies_file}")
        else:
            print("✗ Login failed")


async def test_apply(job_url: str):
    """Test applying to a job"""
    async with JobsCzApplier() as applier:
        cover_letter = """
Vážený pane/paní,

rád bych se ucházel o tuto pozici. Mám relevantní zkušenosti a dovednosti.

S pozdravem
"""
        result = await applier.apply_to_job(job_url, cover_letter)
        print(f"Application result: {result}")


if __name__ == "__main__":
    # Test login
    print("Testing login flow...")
    asyncio.run(test_login())

    # Uncomment to test applying to a specific job
    # asyncio.run(test_apply("https://www.jobs.cz/rpd/..."))
