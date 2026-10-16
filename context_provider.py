"""
Active window title and cursor-annotated screenshot provider for Dictating-app.

Captures the currently focused window title (used both for multimodal prompt
context and for extracting custom vocabulary terms for `gemini-3.5-transcribe`)
and optionally captures a screenshot of the active monitor with a translucent
red circle highlighting the cursor position.
"""

import logging
import os
from typing import Optional, Tuple

from PIL import Image, ImageDraw

logger = logging.getLogger("dictating_app")

try:
    import pygetwindow as gw
except Exception:
    gw = None  # type: ignore

try:
    import pyautogui
except Exception:
    pyautogui = None  # type: ignore

try:
    import mss
except Exception:
    mss = None  # type: ignore


class ContextProvider:
    """Captures active window metadata and cursor-highlighted screenshots."""

    def __init__(self, screenshot_filename: str = "context_screen.png") -> None:
        """Initialize the context provider.

        Args:
            screenshot_filename: Temporary filename for storing the captured screenshot.
        """
        self.screenshot_path = os.path.abspath(screenshot_filename)

    def get_active_window_title(self) -> str:
        """Return the title of the currently active desktop window.

        Returns:
            Window title string, or `'Unknown Window'` if unavailable.
        """
        if gw is None:
            return "Unknown Window"
        try:
            window = gw.getActiveWindow()
            if window and getattr(window, "title", None):
                return str(window.title)
        except Exception as exc:
            logger.debug("Could not retrieve active window title: %s", exc)
        return "Unknown Window"

    def capture_screen_with_cursor(self) -> Optional[str]:
        """Capture the monitor containing the mouse cursor and draw a red indicator.

        Returns:
            Absolute path to the saved PNG screenshot, or `None` if screen
            capture is unavailable.
        """
        if pyautogui is None or mss is None:
            logger.debug("Screen capture libraries (pyautogui/mss) unavailable.")
            return None

        try:
            mx, my = pyautogui.position()

            with mss.mss() as sct:
                target_monitor = None
                for monitor in sct.monitors[1:]:
                    if (
                        monitor["left"] <= mx < monitor["left"] + monitor["width"]
                        and monitor["top"] <= my < monitor["top"] + monitor["height"]
                    ):
                        target_monitor = monitor
                        break

                if not target_monitor:
                    target_monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

                sct_img = sct.grab(target_monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                rel_x = mx - target_monitor["left"]
                rel_y = my - target_monitor["top"]

                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)
                radius = 30
                draw.ellipse(
                    (rel_x - radius, rel_y - radius, rel_x + radius, rel_y + radius),
                    fill=(255, 0, 0, 80),
                    outline=(255, 0, 0, 200),
                    width=2,
                )

                img = img.convert("RGBA")
                combined = Image.alpha_composite(img, overlay)
                combined.convert("RGB").save(self.screenshot_path, "PNG")
                return self.screenshot_path

        except Exception as exc:
            logger.warning("Error capturing screen context: %s", exc)
            return None

    def get_context(
        self, include_screenshot: bool = True
    ) -> Tuple[str, Optional[str]]:
        """Collect active window title and optionally capture a screenshot.

        When a `transcribe`-family model (`gemini-3.5-transcribe`) is used in
        standard dictation mode, `include_screenshot=False` skips screenshot
        capture while still returning the active window title for custom
        vocabulary extraction.

        Args:
            include_screenshot: Whether to capture a PNG screenshot.

        Returns:
            Tuple of `(window_title, screenshot_path_or_none)`.
        """
        title = self.get_active_window_title()
        screenshot = self.capture_screen_with_cursor() if include_screenshot else None
        logger.info(
            "Captured context | window_title=%r | include_screenshot=%s | screenshot=%s",
            title,
            include_screenshot,
            screenshot,
        )
        return title, screenshot
