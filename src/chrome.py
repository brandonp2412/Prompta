"""Compatibility exports for the Playwright-backed Chromium driver."""

from .playwright_driver import ChromeDebuggerUnavailableError, PlaywrightDriver

# Keep the old public name temporarily for callers importing prompta.chrome.
ChromeDriverDriver = PlaywrightDriver

__all__ = ["ChromeDebuggerUnavailableError", "ChromeDriverDriver", "PlaywrightDriver"]
