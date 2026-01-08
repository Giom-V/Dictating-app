import pyautogui
import pygetwindow as gw
from PIL import ImageGrab, ImageDraw
import tempfile
import os

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
        """Captures the screen and highlights the cursor position."""
        try:
            # Capture screen
            screenshot = ImageGrab.grab()
            
            # Get cursor position
            x, y = pyautogui.position()
            
            # Draw highlight (Red circle)
            draw = ImageDraw.Draw(screenshot)
            radius = 30
            # Outline red, width 5
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline="red", width=5)
            
            # Save to temp file
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            
            screenshot.save(path)
            return path
        except Exception as e:
            print(f"Erreur capture écran: {e}")
            return None
