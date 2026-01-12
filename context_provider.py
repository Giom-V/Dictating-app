import pyautogui
import pygetwindow as gw
from PIL import Image, ImageGrab, ImageDraw
import tempfile
import os
import mss

class ContextProvider:
    def get_active_window_title(self):
        try:
            window = gw.getActiveWindow()
            if window:
                return window.title
            return "Inconnue"
        except Exception as e:
            print(f"Erreur recuperation titre fenêtre: {e}")
            return "Erreur"

    def capture_screen_with_cursor(self):
        """Captures the specific monitor where the cursor is and highlights the cursor position."""
        try:
            # Get global cursor position
            x, y = pyautogui.position()
            
            with mss.mss() as sct:
                # Find the monitor containing the cursor
                active_monitor = None
                monitor_idx = 0
                
                # sct.monitors[0] is usually "all monitors combined", so we check others first or iterate carefully
                # We skip index 0 to avoid the combined view unless it's the only one
                monitors = sct.monitors[1:] if len(sct.monitors) > 1 else sct.monitors
                
                for m in monitors:
                    # Check if cursor (x, y) is within this monitor's bounds
                    if (m["left"] <= x < m["left"] + m["width"] and 
                        m["top"] <= y < m["top"] + m["height"]):
                        active_monitor = m
                        break
                
                # Fallback to primary if not found (shouldn't happen)
                if not active_monitor:
                    active_monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

                # Capture only the active monitor
                sct_img = sct.grab(active_monitor)
                screenshot = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                screenshot = screenshot.convert("RGBA")

                # Calculate local cursor position relative to this monitor
                local_x = x - active_monitor["left"]
                local_y = y - active_monitor["top"]

                # Create a transparent overlay
                overlay = Image.new('RGBA', screenshot.size, (255, 255, 255, 0))
                draw = ImageDraw.Draw(overlay)
                
                radius = 30
                # Red with alpha (Highlighter style)
                highlight_color = (255, 0, 0, 80) 
                
                draw.ellipse((local_x - radius, local_y - radius, local_x + radius, local_y + radius), fill=highlight_color, outline=None)
                
                # Composite
                screenshot = Image.alpha_composite(screenshot, overlay)
                
                # Save to temp file
                fd, path = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                
                screenshot.save(path)
                return path

        except Exception as e:
            print(f"Erreur capture écran: {e}")
            return None
