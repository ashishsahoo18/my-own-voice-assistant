"""Isolated browser driver manager and HTTP fallback extractor for OLIVER 2.0."""

from __future__ import annotations

import atexit
import logging
import os
import shutil
import tempfile
import time
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from browser.models import BrowserPageContent
from browser.security import BrowserSecurity, BrowserSecurityError
from core.config import get_config
from research.security import ResponseTooLargeError, SafeHTTPClient, SecurityError

logger = logging.getLogger("oliver.browser.driver")


class IsolatedBrowserManager:
    """Manages an ephemeral, hardened browser session and safe HTTP fallback extraction.
    
    Security Architecture:
    1. Ephemeral Profile: Every browser instance runs in a freshly isolated tempdir.
       Personal profiles, user data, cookies, saved passwords, and extensions are NEVER loaded.
    2. Strict Read-Only: Downloads disabled, form actions prohibited, and scripts bounded.
    3. Pre-flight & Post-navigation Validation: Target URLs and redirect chains are validated against
       domain allowlists and anti-SSRF IP filters.
    4. Safe Cleanup: Process and temporary profiles are cleaned up on normal exit, exceptions,
       and driver failure.
       
    Known Architectural Limitation:
    Standard WebDriver browser engines handle client-side JavaScript redirects asynchronously.
    While pre-flight HTTP 3xx headers and post-navigation final URLs (driver.current_url) are strictly
    revalidated, instantaneous interception of arbitrary client-side JS redirects mid-render cannot be
    guaranteed by the WebDriver protocol without an external forward proxy.
    """

    def __init__(
        self,
        security: Optional[BrowserSecurity] = None,
        headless: Optional[bool] = None,
        driver_type: Optional[str] = None,
        page_load_timeout: Optional[float] = None,
    ) -> None:
        self.config = get_config()
        self.security = security or BrowserSecurity()
        self.headless = headless if headless is not None else self.config.browser.headless
        self.driver_type = (driver_type or self.config.browser.driver_type).lower()
        self.page_load_timeout = page_load_timeout or self.config.browser.page_load_timeout_seconds

        self._driver: Optional[Any] = None
        self._temp_profile_dir: Optional[str] = None
        self._current_url: Optional[str] = None
        self._http_client = SafeHTTPClient(
            connect_timeout=3.0,
            read_timeout=self.page_load_timeout,
            max_bytes=self.config.browser.max_page_bytes,
        )

        atexit.register(self.cleanup)

    @property
    def is_active(self) -> bool:
        return self._driver is not None

    @property
    def current_url(self) -> Optional[str]:
        return self._current_url

    def get_or_create_driver(self) -> Any:
        """Create an isolated, hardened Edge or Chrome WebDriver instance."""
        if self._driver is not None:
            return self._driver

        # Create isolated ephemeral profile directory
        self._temp_profile_dir = tempfile.mkdtemp(prefix="oliver_browser_profile_")

        try:
            from selenium import webdriver
            from selenium.webdriver.edge.options import Options as EdgeOptions
            from selenium.webdriver.chrome.options import Options as ChromeOptions
        except ImportError as imp_err:
            logger.warning("Selenium not installed; falling back to SafeHTTPClient: %s", imp_err)
            raise RuntimeError(f"Selenium is not available: {imp_err}") from imp_err

        driver_instance = None
        last_error = None

        # Determine driver order (Edge default on Windows, Chrome as secondary)
        driver_candidates = ["edge", "chrome"] if self.driver_type in {"auto", "edge"} else ["chrome", "edge"]

        for dtype in driver_candidates:
            try:
                if dtype == "edge":
                    options = EdgeOptions()
                    options.add_argument(f"--user-data-dir={self._temp_profile_dir}")
                    options.add_argument("-inprivate")
                    if self.headless:
                        options.add_argument("--headless=new")
                    self._apply_hardened_options(options)
                    driver_instance = webdriver.Edge(options=options)
                    break
                elif dtype == "chrome":
                    options = ChromeOptions()
                    options.add_argument(f"--user-data-dir={self._temp_profile_dir}")
                    options.add_argument("--incognito")
                    if self.headless:
                        options.add_argument("--headless=new")
                    self._apply_hardened_options(options)
                    driver_instance = webdriver.Chrome(options=options)
                    break
            except Exception as exc:
                logger.warning("Failed to launch %s driver: %s", dtype, exc)
                last_error = exc

        if driver_instance is None:
            self._cleanup_temp_profile()
            raise RuntimeError(f"Unable to initialize WebDriver (tested Edge/Chrome): {last_error}")

        driver_instance.set_page_load_timeout(self.page_load_timeout)
        driver_instance.set_script_timeout(self.config.browser.script_timeout_seconds)
        self._driver = driver_instance
        return self._driver

    def _apply_hardened_options(self, options: Any) -> None:
        """Apply security hardening, disable downloads, and block extensions."""
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-default-apps")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-search-engine-choice-screen")

        # Disable file downloads
        prefs = {
            "download.default_directory": "NUL" if os.name == "nt" else "/dev/null",
            "download.prompt_for_download": False,
            "download.directory_upgrade": False,
            "download_restrictions": 3,  # Block all downloads
            "safebrowsing.enabled": True,
        }
        options.add_experimental_option("prefs", prefs)

    def navigate_and_extract(self, url: str) -> BrowserPageContent:
        """Navigate to URL, validate security constraints, and extract readable content."""
        # 1. Pre-navigation validation (Scheme, Domain Allowlist, SSRF/IP resolution)
        validated_url, _ = self.security.validate_target_url(url, resolve_dns=True)

        # 2. Try WebDriver first if enabled
        try:
            driver = self.get_or_create_driver()
            driver.get(validated_url)

            # Re-validate landing URL post-navigation (catches HTTP redirects and meta-refreshes)
            landing_url = driver.current_url or validated_url
            self.security.validate_target_url(landing_url, resolve_dns=True)
            self._current_url = landing_url

            title = driver.title or ""
            html_source = driver.page_source or ""
            content = self._extract_text_from_html(
                html=html_source,
                current_url=landing_url,
                requested_url=validated_url,
                title_override=title,
            )
            return content

        except Exception as driver_err:
            logger.info("WebDriver navigation failed or driver unavailable (%s); falling back to SafeHTTPClient", driver_err)
            return self._navigate_with_http_fallback(validated_url)

    def _navigate_with_http_fallback(self, url: str) -> BrowserPageContent:
        """Fallback to secure streaming HTTP client when WebDriver is unavailable."""
        # Pre-validate target
        validated_url, _ = self.security.validate_target_url(url, resolve_dns=True)

        # Fetch via SafeHTTPClient (which enforces per-redirect SSRF revalidation and size bounds)
        html_text, final_url, headers = self._http_client.get(validated_url)

        # Re-validate final URL after redirect chain
        self.security.validate_target_url(final_url, resolve_dns=True)
        self._current_url = final_url

        content = self._extract_text_from_html(
            html=html_text,
            current_url=final_url,
            requested_url=validated_url,
            content_type=headers.get("content-type", "text/html"),
        )
        return content

    def _extract_text_from_html(
        self,
        html: str,
        current_url: str,
        requested_url: str,
        title_override: str = "",
        content_type: str = "text/html",
    ) -> BrowserPageContent:
        """Parse HTML, extract title, meta description, and clean readable text."""
        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title = title_override.strip()
        if not title:
            title_tag = soup.find("title")
            title = title_tag.get_text().strip() if title_tag else ""

        # Extract meta description
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        if meta_tag and meta_tag.get("content"):
            meta_desc = str(meta_tag["content"]).strip()

        # Remove scripts, styles, forms, inputs, and navigation elements
        for element in soup(["script", "style", "nav", "header", "footer", "form", "noscript", "svg", "button", "input"]):
            element.decompose()

        # Extract clean text
        raw_text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)

        # Enforce maximum text length bound
        max_chars = self.config.browser.max_text_chars
        is_truncated = False
        if len(clean_text) > max_chars:
            clean_text = clean_text[:max_chars]
            is_truncated = True

        return BrowserPageContent(
            url=current_url,
            requested_url=requested_url,
            title=title or urlparse(current_url).netloc,
            text=clean_text,
            meta_description=meta_desc,
            extracted_length=len(clean_text),
            is_truncated=is_truncated,
            content_type=content_type,
            status_code=200,
        )

    def close(self) -> None:
        """Close active driver and clean up temporary profile directory."""
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception as exc:
                logger.warning("Error quitting driver: %s", exc)
            finally:
                self._driver = None

        self._cleanup_temp_profile()
        self._current_url = None

    def _cleanup_temp_profile(self) -> None:
        """Safely remove the temporary profile directory from disk."""
        if self._temp_profile_dir and os.path.exists(self._temp_profile_dir):
            try:
                shutil.rmtree(self._temp_profile_dir, ignore_errors=True)
            except Exception as exc:
                logger.warning("Could not fully delete temp browser profile '%s': %s", self._temp_profile_dir, exc)
            finally:
                self._temp_profile_dir = None

    def cleanup(self) -> None:
        """Atexit handler to ensure processes and profiles are released."""
        self.close()

    def __enter__(self) -> IsolatedBrowserManager:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
