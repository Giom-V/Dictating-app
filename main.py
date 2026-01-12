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
        HOTKEY_THINKING = os.getenv("HOTKEY_THINKING", "F9")
        HOTKEY_DEBUG = "ctrl+f9"
        
        print(f"[INFO] Listening for Dictation ({HOTKEY}), Thinking ({HOTKEY_THINKING}), and Debug ({HOTKEY_DEBUG})...")
        
        while self.running:
            try:
                active_mode = None
                pressed_key = None
                
                # Intelligent Polling
                if keyboard.is_pressed(HOTKEY):
                    active_mode = "dictation"
                    pressed_key = HOTKEY
                elif keyboard.is_pressed(HOTKEY_THINKING):
                    # Check if it is actually DEBUG (Ctrl+F9)
                    if keyboard.is_pressed(HOTKEY_DEBUG):
                         active_mode = "debug"
                         pressed_key = HOTKEY_DEBUG
                    else:
                         active_mode = "thinking"
                         pressed_key = HOTKEY_THINKING
                elif keyboard.is_pressed(HOTKEY_DEBUG): # Fallback check
                    active_mode = "debug"
                    pressed_key = HOTKEY_DEBUG
                
                if not active_mode:
                    time.sleep(0.05)
                    continue

                print(f"\n[EVENT] Key {pressed_key} pressed ({active_mode}).")
                
                # Context capture (Always needed)
                print("[INFO] Context capture...")
                try:
                    window_title = self.context_provider.get_active_window_title()
                    image_path = self.context_provider.capture_screen_with_cursor()
                except Exception as e:
                    print(f"[WARN] Context error: {e}")
                    window_title = None
                    image_path = None
                    
                # Handle Debug Mode (No Audio needed, just Screenshot analysis)
                if active_mode == "debug":
                     # Wait for release to avoid multiple triggers
                     while keyboard.is_pressed("f9") or keyboard.is_pressed("ctrl"): # Simple debounce
                         time.sleep(0.1)

                     print("[DEBUG] Analyzing screenshot...")
                     try:
                        # We pass None for audio_path
                        text = self.client.process_audio(audio_path=None, image_path=image_path, window_title=window_title, mode="debug")
                        print(f"[DEBUG REPORT]\n{text}\n")
                        # We do NOT paste the debug text, just print to console for User to see
                     except Exception as e:
                        print(f"[ERROR] Debug analysis failed: {e}")
                     
                     # Cleanup image
                     if image_path and os.path.exists(image_path):
                        os.remove(image_path)
                     continue # Loop back

                # Start recording for Voice Modes
                self.recorder.start()

                # Wait for release of the specific key
                # Note: For complex keys like ctrl+f9, simple wait might be tricky, but here we are in voice mode (F8/F9)
                while self.running and keyboard.is_pressed(pressed_key):
                    time.sleep(0.05)
                
                print(f"[EVENT] Key released.")
                audio_path = self.recorder.stop()
                
                if audio_path:
                    try:
                        text = self.client.process_audio(audio_path, image_path, window_title, mode=active_mode)
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
                
                # Prevent accidental re-trigger immediately after
                time.sleep(0.5)
                
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
