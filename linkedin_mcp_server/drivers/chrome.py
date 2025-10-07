# linkedin_mcp_server/drivers/chrome.py
"""
Chrome WebDriver management for LinkedIn scraping with session persistence.

Handles Chrome WebDriver creation, configuration, authentication, and lifecycle management.
Implements singleton pattern for driver reuse across tools with automatic cleanup.
Provides cookie-based authentication and comprehensive error handling.
"""

import logging
import os
import platform
from typing import Dict, Optional

from linkedin_scraper.exceptions import (
    CaptchaRequiredError,
    InvalidCredentialsError,
    LoginTimeoutError,
    RateLimitError,
    SecurityChallengeError,
    TwoFactorAuthError,
)
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from linkedin_mcp_server.config import get_config
from linkedin_mcp_server.exceptions import DriverInitializationError


# Constants
def get_default_user_agent() -> str:
    """Get platform-specific default user agent to reduce fingerprinting."""
    system = platform.system()

    if system == "Windows":
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    elif system == "Darwin":  # macOS
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    else:  # Linux and others
        return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"


# Global driver storage to reuse sessions
active_drivers: Dict[str, webdriver.Chrome] = {}


logger = logging.getLogger(__name__)


def create_chrome_options(config) -> Options:
    """
    Create Chrome options with all necessary configuration for LinkedIn scraping.

    Args:
        config: AppConfig instance with Chrome configuration

    Returns:
        Options: Configured Chrome options object
    """
    chrome_options = Options()

    logger.info(
        f"Running browser in {'headless' if config.chrome.headless else 'visible'} mode"
    )
    if config.chrome.headless:
        chrome_options.add_argument("--headless=new")

    # Add essential options for stability
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--metrics-recording-only")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--disable-features=TranslateUI,BlinkGenPropertyTrees")
    chrome_options.add_argument("--aggressive-cache-discard")
    chrome_options.add_argument("--disable-ipc-flooding-protection")

    # Set user agent (configurable with platform-specific default)
    user_agent = config.chrome.user_agent or get_default_user_agent()
    chrome_options.add_argument(f"--user-agent={user_agent}")

    # Add any custom browser arguments from config
    for arg in config.chrome.browser_args:
        chrome_options.add_argument(arg)

    return chrome_options


def create_chrome_service(config):
    """
    Create Chrome service with ChromeDriver path resolution.

    Args:
        config: AppConfig instance with Chrome configuration

    Returns:
        Service or None: Chrome service if path is configured, None for auto-detection
    """
    # Use ChromeDriver path from environment or config
    chromedriver_path = (
        os.environ.get("CHROMEDRIVER_PATH") or config.chrome.chromedriver_path
    )

    if chromedriver_path:
        logger.info(f"Using ChromeDriver at path: {chromedriver_path}")
        return Service(executable_path=chromedriver_path)
    else:
        logger.info("Using auto-detected ChromeDriver")
        return None


def create_temporary_chrome_driver() -> webdriver.Chrome:
    """
    Create a temporary Chrome WebDriver instance for one-off operations.

    This driver is NOT stored in the global active_drivers dict and should be
    manually cleaned up by the caller.

    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance

    Raises:
        WebDriverException: If driver creation fails
    """
    config = get_config()

    logger.info("Creating temporary Chrome WebDriver...")

    # Create Chrome options using shared function
    chrome_options = create_chrome_options(config)

    # Create Chrome service using shared function
    service = create_chrome_service(config)

    # Initialize Chrome driver
    if service:
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        driver = webdriver.Chrome(options=chrome_options)

    logger.info("Temporary Chrome WebDriver created successfully")

    # Add a page load timeout for safety
    driver.set_page_load_timeout(60)

    # Set shorter implicit wait for faster operations
    driver.implicitly_wait(10)

    return driver


def create_chrome_driver() -> webdriver.Chrome:
    """
    Create a new Chrome WebDriver instance with proper configuration.

    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance

    Raises:
        WebDriverException: If driver creation fails
    """
    config = get_config()

    logger.info("Initializing Chrome WebDriver...")

    # Create Chrome options using shared function
    chrome_options = create_chrome_options(config)

    # Create Chrome service using shared function
    service = create_chrome_service(config)

    # Initialize Chrome driver
    if service:
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        driver = webdriver.Chrome(options=chrome_options)

    logger.info("Chrome WebDriver initialized successfully")

    # Add a page load timeout for safety
    driver.set_page_load_timeout(60)

    # Set shorter implicit wait for faster cookie validation
    driver.implicitly_wait(10)

    return driver


def _normalize_cookie_value(cookie: str) -> str:
    """Normalize cookie input to raw li_at value."""

    if cookie.startswith("li_at="):
        return cookie.split("li_at=", 1)[1]
    return cookie


def login_with_cookie(driver: webdriver.Chrome, cookie: str) -> bool:
    """
    Log in to LinkedIn using session cookie.

    Args:
        driver: Chrome WebDriver instance
        cookie: LinkedIn session cookie

    Returns:
        bool: True if login was successful, False otherwise
    """
    import time

    try:
        from linkedin_scraper import actions  # type: ignore
        from selenium.common.exceptions import TimeoutException

        logger.info("Attempting cookie authentication...")

        # Set longer timeout to handle slow LinkedIn loading
        # Invalid cookies cause indefinite loading, so timeout is our detection mechanism
        driver.set_page_load_timeout(45)

        # Attempt login
        retry_count = 0
        max_retries = 1

        cookie_value = _normalize_cookie_value(cookie)

        while retry_count <= max_retries:
            try:
                actions.login(driver, cookie=cookie_value)
                # If we reach here without timeout, login attempt completed
                break
            except TimeoutException:
                # Timeout indicates invalid cookie (page loads forever)
                logger.warning(
                    "Cookie authentication failed - page load timeout (likely invalid cookie)"
                )
                return False
            except Exception as e:
                # Handle InvalidCredentialsError from linkedin-scraper
                # This library sometimes incorrectly reports failure even when login succeeds
                if "InvalidCredentialsError" in str(
                    type(e)
                ) or "Cookie login failed" in str(e):
                    logger.info(
                        "LinkedIn-scraper reported InvalidCredentialsError - verifying actual authentication status..."
                    )
                    # Give LinkedIn time to complete redirect
                    time.sleep(2)
                    break
                else:
                    logger.warning(f"Login attempt failed: {e}")
                    if retry_count < max_retries:
                        retry_count += 1
                        logger.info(
                            f"Retrying authentication (attempt {retry_count + 1}/{max_retries + 1})"
                        )
                        time.sleep(2)
                        continue
                    else:
                        return False

        # Check authentication status by examining the current URL
        try:
            current_url = driver.current_url

            # Check if we're on login page (authentication failed)
            if "login" in current_url or "uas/login" in current_url:
                logger.warning(
                    "Cookie authentication failed - redirected to login page"
                )
                return False

            # Check if we're on authenticated pages (authentication succeeded)
            elif any(
                indicator in current_url
                for indicator in ["feed", "mynetwork", "linkedin.com/in/", "/feed/"]
            ):
                logger.info("Cookie authentication successful")
                return True

            # Unexpected page - wait briefly and check again
            else:
                logger.info(
                    "Unexpected page after login, checking authentication status..."
                )
                time.sleep(2)

                final_url = driver.current_url
                if "login" in final_url or "uas/login" in final_url:
                    logger.warning("Cookie authentication failed - ended on login page")
                    return False
                elif any(
                    indicator in final_url
                    for indicator in ["feed", "mynetwork", "linkedin.com/in/", "/feed/"]
                ):
                    logger.info("Cookie authentication successful after verification")
                    return True
                else:
                    logger.warning(
                        f"Cookie authentication uncertain - unexpected final page: {final_url}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Error checking authentication status: {e}")
            return False

    except Exception as e:
        logger.error(f"Cookie authentication failed with error: {e}")
        return False
    finally:
        # Restore normal timeout
        driver.set_page_load_timeout(60)


def login_to_linkedin(driver: webdriver.Chrome, authentication: str) -> None:
    """
    Log in to LinkedIn using provided authentication.

    Args:
        driver: Chrome WebDriver instance
        authentication: LinkedIn session cookie

    Raises:
        Various login-related errors from linkedin-scraper or this module
    """
    # Try cookie authentication
    if login_with_cookie(driver, authentication):
        logger.info("Successfully logged in to LinkedIn using cookie")
        return

    # If we get here, cookie authentication failed
    logger.error("Cookie authentication failed")

    # Clear invalid cookie from keyring
    from linkedin_mcp_server.authentication import clear_authentication

    clear_authentication()
    logger.info("Cleared invalid cookie from authentication storage")

    # Check current page to determine the issue
    try:
        current_url: str = driver.current_url

        if "checkpoint/challenge" in current_url:
            if "security check" in driver.page_source.lower():
                raise SecurityChallengeError(
                    challenge_url=current_url,
                    message="LinkedIn requires a security challenge. Please complete it manually and restart the application.",
                )
            else:
                raise CaptchaRequiredError(captcha_url=current_url)
        else:
            raise InvalidCredentialsError(
                "Cookie authentication failed - cookie may be expired or invalid"
            )

    except Exception as e:
        # If we can't determine the specific error, raise a generic one
        raise LoginTimeoutError(f"Login failed: {str(e)}")


def get_or_create_driver(authentication: str, session_id: str = "default") -> webdriver.Chrome:
    """
    Get existing driver or create a new one and login.

    Args:
        authentication: LinkedIn session cookie for login

    Returns:
        webdriver.Chrome: Chrome WebDriver instance, logged in and ready

    Raises:
        DriverInitializationError: If driver creation fails
        Various login-related errors: If login fails
    """
    # Return existing driver if available
    if session_id in active_drivers:
        logger.info("Using existing Chrome WebDriver session")
        return active_drivers[session_id]

    try:
        # Create new driver
        driver = create_chrome_driver()

        # Login to LinkedIn
        login_to_linkedin(driver, authentication)

        # Store successful driver
        active_drivers[session_id] = driver
        logger.info("Chrome WebDriver session created and authenticated successfully")

        return driver

    except WebDriverException as e:
        error_msg = f"Error creating web driver: {e}"
        logger.error(error_msg)
        raise DriverInitializationError(error_msg)
    except (
        CaptchaRequiredError,
        InvalidCredentialsError,
        SecurityChallengeError,
        TwoFactorAuthError,
        RateLimitError,
        LoginTimeoutError,
    ) as e:
        # Login-related errors - clean up driver if it was created
        if session_id in active_drivers:
            active_drivers[session_id].quit()
            del active_drivers[session_id]
        raise e


def close_driver(session_id: str) -> bool:
    """Close a specific driver session if it exists."""

    driver = active_drivers.pop(session_id, None)
    if not driver:
        return False

    try:
        logger.info(f"Closing Chrome WebDriver session: {session_id}")
        driver.quit()
        return True
    except Exception as e:
        logger.warning(f"Error closing driver {session_id}: {e}")
        return False


def close_all_drivers() -> None:
    """Close all active drivers and clean up resources."""

    session_ids = list(active_drivers.keys())
    for session_id in session_ids:
        close_driver(session_id)

    logger.info("All Chrome WebDriver sessions closed")


def get_active_driver(session_id: str = "default") -> Optional[webdriver.Chrome]:
    """Get the currently active driver for a session without creating a new one."""

    return active_drivers.get(session_id)


def capture_session_cookie(driver: webdriver.Chrome) -> Optional[str]:
    """
    Capture LinkedIn session cookie from driver.

    Args:
        driver: Chrome WebDriver instance

    Returns:
        Optional[str]: Session cookie if found, None otherwise
    """
    try:
        # Get li_at cookie which is the main LinkedIn session cookie
        cookie = driver.get_cookie("li_at")
        if cookie and cookie.get("value"):
            return f"li_at={cookie['value']}"
        return None
    except Exception as e:
        logger.warning(f"Failed to capture session cookie: {e}")
        return None
