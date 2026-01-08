import keyboard
import time
import os
import threading
import sys
import winreg
from PIL import Image
import pystray
from pystray import MenuItem as item
import pyperclip
from dotenv import load_dotenv

from recorder import AudioRecorder
from llm_client import GeminiClient
from context_provider import ContextProvider

load_dotenv(override=True)

HOTKEY = os.getenv("HOTKEY", "F8")
APP_NAME = "Gemini Dictating Agent"
ICON_PATH = "icon.png"

class DictatingApp:
    def __init__(self):
        self.running = True
        self.client = None
        self.recorder = None
        self.context_provider = None
        self.icon = None

    def setup_components(self):
        try:
            self.client = GeminiClient()
            self.recorder = AudioRecorder()
            self.context_provider = ContextProvider()
            print("[INFO] Components initialized.")
            return True
        except Exception as e:
            print(f"[ERROR] Init failed: {e}")
            return False

    def listen_loop(self):
        print(f"[INFO] Listening for {HOTKEY}...")
        while self.running:
            try:
                # Polling wait to check self.running occasionally
                while self.running and not keyboard.is_pressed(HOTKEY):
                    time.sleep(0.1)
                
                if not self.running: break

                print(f"\n[EVENT] Key {HOTKEY} pressed.")
                self.recorder.start()
                
                # Context
                print("[INFO] Context capture...")
                try:
                    window_title = self.context_provider.get_active_window_title()
                    image_path = self.context_provider.capture_screen_with_cursor()
                except Exception as e:
                    print(f"[WARN] Context error: {e}")
                    window_title = None
                    image_path = None

                # Wait for release
                while self.running and keyboard.is_pressed(HOTKEY):
                    time.sleep(0.05)
                
                print(f"[EVENT] Key released.")
                audio_path = self.recorder.stop()
                
                if audio_path:
                    try:
                        text = self.client.process_audio(audio_path, image_path, window_title)
                        if text:
                            pyperclip.copy(text)
                            time.sleep(0.1)
                            keyboard.send('ctrl+v')
                    except Exception as e:
                        print(f"[ERROR] processing: {e}")
                    
                    # Cleanup
                    try:
                        os.remove(audio_path)
                        if image_path and os.path.exists(image_path):
                            os.remove(image_path)
                    except: pass
                
            except Exception as e:
                print(f"[ERROR] Loop error: {e}")
                time.sleep(1)

    def on_quit(self, icon, item):
        self.running = False
        icon.stop()
        sys.exit()

    def set_startup(self, enable=True):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if enable:
                # Path to python executable + script
                # Or if compiled to exe, just the exe path.
                # Since we are running .py, we use pythonw.exe to minimize console
                python_exe = sys.executable.replace("python.exe", "pythonw.exe")
                script_path = os.path.abspath(__file__)
                cmd = f'"{python_exe}" "{script_path}"'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                print("[INFO] Added to startup.")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    print("[INFO] Removed from startup.")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[ERROR] Startup toggle failed: {e}")

    def is_startup_enabled(self):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def toggle_startup(self, icon, item):
        new_state = not item.checked
        self.set_startup(new_state)

    def run(self):
        if not self.setup_components():
            return

        # Start listener thread
        t = threading.Thread(target=self.listen_loop, daemon=True)
        t.start()
        
        # Load Icon
        try:
            image = Image.open(ICON_PATH)
        except:
             # Create simple icon if not found
            image = Image.new('RGB', (64, 64), color = (73, 109, 137))
        
        # Build menu
        menu = pystray.Menu(
            item('Start with Windows', self.toggle_startup, checked=lambda item: self.is_startup_enabled()),
            item('Quit', self.on_quit)
        )

        self.icon = pystray.Icon(APP_NAME, image, APP_NAME, menu)
        print("[INFO] System Tray Icon started.")
        self.icon.run()

if __name__ == "__main__":
    app = DictatingApp()
    app.run()
