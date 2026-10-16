"""
Main entry point, system tray controller, and CLI runner for Dictating-app.

Provides:
- Global push-to-talk hotkeys (`F8` for dictation, `F9` for Thinking Mode,
  `Ctrl+F9` for Debug Mode).
- System tray icon (`pystray`) with live **Model Selector** (switching between
  `gemini-3.5-transcribe`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite-preview`,
  `gemini-3.5-flash`, `gemini-2.5-flash-lite`, `gemini-3.1-pro-preview`, etc.),
  **Transcribe Mode Selector** (`SMART` vs `VERBATIM`), and **Microphone Selector**.
- Non-interactive `--dry-run` CLI mode for testing audio transcription and
  family-specific prompting without altering the clipboard or Windows hooks.
"""

import argparse
import os
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from PIL import Image, ImageDraw

from config import (
    AVAILABLE_MODELS,
    DEFAULT_CONFIG_PATH,
    DEFAULT_DICTATION_MODEL,
    DEFAULT_TRANSCRIBE_MODE,
    HOTKEY_DEBUG,
    HOTKEY_DICTATION,
    HOTKEY_THINKING,
    MODEL_REGISTRY,
    TRANSCRIBE_MODES,
    get_model_family,
    get_model_spec,
    load_app_config,
    save_app_config,
)
from context_provider import ContextProvider
from llm_client import GeminiClient
from logger_setup import setup_logging
from recorder import AudioRecorder

logger = setup_logging()

try:
    import winsound
except ImportError:
    winsound = None  # type: ignore

try:
    import keyboard
except Exception:
    keyboard = None  # type: ignore

try:
    import pyperclip
except Exception:
    pyperclip = None  # type: ignore

try:
    import pystray
except Exception:
    pystray = None  # type: ignore


class DictatingApp:
    """Main desktop application coordinating hotkeys, audio capture, tray UI, and Gemini calls."""

    def __init__(
        self,
        model_override: Optional[str] = None,
        transcribe_mode_override: Optional[str] = None,
        config_path: str = DEFAULT_CONFIG_PATH,
        dry_run: bool = False,
    ) -> None:
        """Initialize DictatingApp components and load persisted configuration.

        Args:
            model_override: Optional CLI override for the active dictation model.
            transcribe_mode_override: Optional CLI override for Transcribe mode.
            config_path: Path to `config.json`.
            dry_run: When True, disables clipboard pasting and config file writes.
        """
        self.config_path = config_path
        self.dry_run = dry_run
        self.config_data = load_app_config(self.config_path)

        self.recorder = AudioRecorder()
        self.context_provider = ContextProvider()
        self.llm_client = GeminiClient(
            model_name=model_override or self.config_data.get("model_name"),
            transcribe_mode=transcribe_mode_override or self.config_data.get("transcribe_mode"),
            config_data=self.config_data,
            dry_run=dry_run,
        )

        self.is_recording = False
        self.current_mode: Optional[str] = None
        self.context_data: Dict[str, Optional[str]] = {}
        self.icon = None
        self.running = True
        self.startup_shortcut_path = os.path.join(
            os.getenv("APPDATA", ""),
            r"Microsoft\Windows\Start Menu\Programs\Startup\DictatingApp.lnk",
        )

        self._apply_saved_microphone()

    def _apply_saved_microphone(self) -> None:
        """Restore the user's preferred microphone device from `config.json`."""
        saved_mic_name = self.config_data.get("microphone")
        if not saved_mic_name:
            return
        devices = self.recorder.get_input_devices()
        for idx, name in devices.items():
            if name == saved_mic_name:
                self.recorder.set_device(idx)
                logger.info("Restored microphone from config: %s (index=%d)", name, idx)
                return
        logger.warning("Configured microphone %r not found among active devices.", saved_mic_name)

    def save_config_updates(self, updates: Dict[str, Any]) -> None:
        """Update in-memory config and persist changes to `config.json`."""
        self.config_data.update(updates)
        save_app_config(self.config_data, self.config_path, dry_run=self.dry_run)

    def is_in_startup(self) -> bool:
        """Return True if the Windows Startup shortcut exists."""
        return bool(self.startup_shortcut_path) and os.path.exists(self.startup_shortcut_path)

    def toggle_startup(self, icon: Any, item: Any) -> None:
        """Create or remove the Windows Startup `.lnk` shortcut."""
        if self.is_in_startup():
            try:
                os.remove(self.startup_shortcut_path)
                logger.info("Removed application from Windows Startup.")
            except OSError as exc:
                logger.error("Error removing startup shortcut: %s", exc)
        else:
            try:
                target = os.path.abspath(sys.argv[0])
                work_dir = os.path.dirname(target)
                python_exe = sys.executable.replace("python.exe", "pythonw.exe")
                if not os.path.exists(python_exe):
                    python_exe = sys.executable

                ps_script = (
                    f"$WshShell = New-Object -comObject WScript.Shell; "
                    f"$Shortcut = $WshShell.CreateShortcut('{self.startup_shortcut_path}'); "
                    f"$Shortcut.TargetPath = '{python_exe}'; "
                    f"$Shortcut.Arguments = '\"{target}\"'; "
                    f"$Shortcut.WorkingDirectory = '{work_dir}'; "
                    f"$Shortcut.Save()"
                )
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.run(
                    ["powershell", "-Command", ps_script],
                    check=True,
                    creationflags=creationflags,
                )
                logger.info("Added application to Windows Startup.")
            except Exception as exc:
                logger.error("Error adding startup shortcut: %s", exc)

    def play_sound(self, frequency: int, duration: int) -> None:
        """Play an audible beep cue on Windows if `winsound` is available."""
        if winsound is None:
            return
        try:
            winsound.Beep(frequency, duration)
        except Exception:
            pass

    def create_tray_image(self, color: str = "green") -> Image.Image:
        """Render the 64x64 system tray icon in the given state color."""
        width = 64
        height = 64
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.ellipse((8, 8, width - 8, height - 8), fill=color)
        return image

    def update_tray_icon(self, state: str) -> None:
        """Update the system tray icon color and tooltip to reflect app state."""
        if not self.icon:
            return
        colors = {
            "idle": "green",
            "recording": "red",
            "processing": "orange",
        }
        color = colors.get(state, "green")
        self.icon.icon = self.create_tray_image(color)
        spec = get_model_spec(self.llm_client.model_name)
        self.icon.title = f"Dictating App ({state.capitalize()}) - {spec.display_name}"

    def start_session(self, mode: str) -> None:
        """Begin a push-to-talk recording session for the specified mode."""
        if self.is_recording:
            return

        self.is_recording = True
        self.current_mode = mode
        active_model = self.llm_client.model_name
        active_family = self.llm_client.get_active_family()
        need_screenshot = self.llm_client.requires_visual_context(mode)

        logger.info(
            "Starting session | mode=%s | model=%s | family=%s | capture_screenshot=%s",
            mode,
            active_model,
            active_family,
            need_screenshot,
        )

        self.update_tray_icon("recording")
        self.play_sound(600, 100)

        def capture_ctx() -> None:
            title, screen = self.context_provider.get_context(
                include_screenshot=need_screenshot
            )
            self.context_data = {"title": title, "screen": screen}

        threading.Thread(target=capture_ctx, daemon=True).start()
        self.recorder.start_recording()

    def stop_session(self) -> None:
        """End the active recording session and dispatch audio processing."""
        if not self.is_recording:
            return

        logger.info("Stopping recording session (mode=%s)...", self.current_mode)
        self.is_recording = False
        self.update_tray_icon("processing")
        self.play_sound(400, 100)

        audio_path = self.recorder.stop_recording()
        if not audio_path:
            logger.warning("No audio recorded; returning to idle.")
            self.update_tray_icon("idle")
            return

        mode_to_run = self.current_mode or "dictation"
        threading.Thread(
            target=self.process_and_type,
            args=(audio_path, mode_to_run),
            daemon=True,
        ).start()

    def process_and_type(self, audio_path: str, mode: str) -> None:
        """Send captured audio/context to `GeminiClient` and paste the result."""
        time.sleep(0.1)
        window_title = self.context_data.get("title", "Unknown")
        screenshot_path = self.context_data.get("screen", None)

        result_text = self.llm_client.process_audio(
            audio_path=audio_path,
            image_path=screenshot_path,
            window_title=window_title,
            mode=mode,
        )

        if result_text:
            logger.info("Result ready (%d chars): %r", len(result_text), result_text[:200])

            if result_text == "IMAGE_COPIED_TO_CLIPBOARD":
                logger.info("Pasting generated image from clipboard...")
                if not self.dry_run and keyboard is not None:
                    time.sleep(0.2)
                    keyboard.send("ctrl+v")
                self.play_sound(1000, 150)
            else:
                if not self.dry_run and pyperclip is not None and keyboard is not None:
                    pyperclip.copy(result_text)
                    time.sleep(0.1)
                    keyboard.send("ctrl+v")
                self.play_sound(800, 100)
        else:
            logger.info("No text produced (silent audio or empty result).")
            self.play_sound(200, 300)

        self.update_tray_icon("idle")

        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
            if screenshot_path and os.path.exists(screenshot_path):
                os.remove(screenshot_path)
        except OSError:
            pass

    def setup_hotkeys(self) -> None:
        """Poll push-to-talk hotkeys (`F8`, `F9`, `Ctrl+F9`) in a background loop."""
        if keyboard is None:
            logger.error("`keyboard` module unavailable; hotkeys cannot be registered.")
            return

        logger.info(
            "Listening for hotkeys: %s (Dictation), %s (Thinking), %s (Debug)...",
            HOTKEY_DICTATION.upper(),
            HOTKEY_THINKING.upper(),
            HOTKEY_DEBUG.upper(),
        )
        while self.running:
            try:
                if keyboard.is_pressed(HOTKEY_DICTATION):
                    if not self.is_recording:
                        self.start_session("dictation")
                        while keyboard.is_pressed(HOTKEY_DICTATION) and self.running:
                            time.sleep(0.05)
                        self.stop_session()

                if keyboard.is_pressed(HOTKEY_THINKING):
                    if not self.is_recording:
                        if keyboard.is_pressed("ctrl"):
                            self.start_session("debug")
                        else:
                            self.start_session("thinking")
                        while keyboard.is_pressed(HOTKEY_THINKING) and self.running:
                            time.sleep(0.05)
                        self.stop_session()

                time.sleep(0.05)
            except Exception as exc:
                logger.error("Error in hotkey loop: %s", exc)
                time.sleep(1.0)

    def restart_app(self, icon: Any, item: Any) -> None:
        """Restart the application process from the system tray."""
        logger.info("Restarting application...")
        self.running = False
        if self.icon:
            self.icon.stop()
        os.execl(sys.executable, sys.executable, *sys.argv)

    def quit_app(self, icon: Any, item: Any) -> None:
        """Gracefully stop the system tray icon and exit the process."""
        logger.info("Quitting application...")
        self.running = False
        if self.icon:
            self.icon.stop()
        os._exit(0)

    def set_microphone_handler(self, index: int, name: str) -> Callable[[Any, Any], None]:
        """Create a tray menu callback that selects and persists a microphone."""
        def handler(icon: Any, item: Any) -> None:
            self.recorder.set_device(index)
            self.save_config_updates({"microphone": name})
        return handler

    def set_model_handler(self, model_id: str) -> Callable[[Any, Any], None]:
        """Create a tray menu callback that selects and persists a dictation model."""
        def handler(icon: Any, item: Any) -> None:
            self.llm_client.set_model(model_id)
            self.save_config_updates({"model_name": model_id})
            self.update_tray_icon("idle")
        return handler

    def set_transcribe_mode_handler(self, mode_key: str) -> Callable[[Any, Any], None]:
        """Create a tray menu callback that selects SMART vs VERBATIM transcribe mode."""
        def handler(icon: Any, item: Any) -> None:
            self.llm_client.set_transcribe_mode(mode_key)
            self.save_config_updates({"transcribe_mode": mode_key})
        return handler

    def _build_model_menu_items(self) -> List[Any]:
        """Build radio menu items for the system tray 'Model' selector."""
        items: List[Any] = []
        specs = list(AVAILABLE_MODELS)
        if self.llm_client.model_name not in MODEL_REGISTRY:
            specs.insert(0, get_model_spec(self.llm_client.model_name))

        for spec in specs:
            m_id = spec.model_id
            items.append(
                pystray.MenuItem(
                    spec.display_name,
                    self.set_model_handler(m_id),
                    checked=lambda item, target=m_id: self.llm_client.model_name == target,
                    radio=True,
                )
            )
        return items

    def _build_transcribe_mode_menu_items(self) -> List[Any]:
        """Build radio menu items for the 'Transcribe Mode' submenu (`SMART` vs `VERBATIM`)."""
        items: List[Any] = []
        for mode_key, label in TRANSCRIBE_MODES.items():
            items.append(
                pystray.MenuItem(
                    label,
                    self.set_transcribe_mode_handler(mode_key),
                    checked=lambda item, target=mode_key: self.llm_client.transcribe_mode == target,
                    radio=True,
                )
            )
        return items

    def run(self) -> None:
        """Start the hotkey polling thread and launch the system tray icon loop."""
        if pystray is None:
            raise RuntimeError("`pystray` is required to run the desktop tray interface.")

        hotkey_thread = threading.Thread(target=self.setup_hotkeys, daemon=True)
        hotkey_thread.start()

        devices = self.recorder.get_input_devices()
        mic_items = [
            pystray.MenuItem(
                name,
                self.set_microphone_handler(idx, name),
                checked=lambda item, idx=idx: self.recorder.device_index == idx,
                radio=True,
            )
            for idx, name in devices.items()
        ]
        if not mic_items:
            mic_items.append(pystray.MenuItem("Default Microphone", lambda icon, item: None, enabled=False))

        model_items = self._build_model_menu_items()
        transcribe_mode_items = self._build_transcribe_mode_menu_items()

        menu = pystray.Menu(
            pystray.MenuItem("Model", pystray.Menu(*model_items)),
            pystray.MenuItem("Transcribe Mode (ASR)", pystray.Menu(*transcribe_mode_items)),
            pystray.MenuItem("Microphone", pystray.Menu(*mic_items)),
            pystray.MenuItem(
                "Start with Windows",
                self.toggle_startup,
                checked=lambda item: self.is_in_startup(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Restart", self.restart_app),
            pystray.MenuItem("Quit", self.quit_app),
        )

        spec = get_model_spec(self.llm_client.model_name)
        self.icon = pystray.Icon(
            "DictatingApp",
            self.create_tray_image("green"),
            f"Dictating App (Idle) - {spec.display_name}",
            menu,
        )
        logger.info(
            "Application started | active_model=%s (%s) | transcribe_mode=%s",
            self.llm_client.model_name,
            self.llm_client.get_active_family(),
            self.llm_client.transcribe_mode,
        )
        self.icon.run()


def _create_temp_silent_wav(path: str) -> str:
    """Create a 1-second silent WAV file in `/tmp` for `--dry-run` when no audio is passed."""
    import wave

    sample_rate = 16000
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * sample_rate)
    return path


def run_cli_dry_run(args: argparse.Namespace) -> int:
    """Execute a non-interactive `--dry-run` test of `GeminiClient` across model families.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Exit code (`0` on success, `1` on failure).
    """
    client = GeminiClient(
        model_name=args.model,
        transcribe_mode=args.transcribe_mode,
        dry_run=True,
    )

    audio_path = args.audio
    created_temp_audio = False
    if not audio_path:
        audio_path = "/tmp/dictating_app_dry_run_silence.wav"
        _create_temp_silent_wav(audio_path)
        created_temp_audio = True

    try:
        logger.info(
            "[DRY-RUN] Testing model=%s (family=%s, transcribe_mode=%s) | mode=%s | audio=%s | window=%r",
            client.model_name,
            client.get_active_family(),
            client.transcribe_mode,
            args.mode,
            audio_path,
            args.window_title,
        )
        output = client.process_audio(
            audio_path=audio_path,
            image_path=args.screenshot,
            window_title=args.window_title,
            mode=args.mode,
        )
        print(f"\n--- DRY-RUN RESULT ({client.model_name} | family={client.get_active_family()}) ---")
        print(output if output is not None else "<None>")
        print("-------------------------------------------------------------------")
        return 0
    finally:
        if created_temp_audio and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except OSError:
                pass


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for Dictating-app."""
    parser = argparse.ArgumentParser(
        description="Windows AI Voice Dictation & Multimodal Assistant (Transcribe & Gemini)."
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Model ID to use (default from config.json or {DEFAULT_DICTATION_MODEL}).",
    )
    parser.add_argument(
        "--transcribe-mode",
        type=str,
        choices=list(TRANSCRIBE_MODES.keys()),
        default=None,
        help=f"Transcription mode for gemini-3.5-transcribe (default: {DEFAULT_TRANSCRIBE_MODE}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run a single non-interactive test transcription without starting the tray or mutating clipboard.",
    )
    parser.add_argument(
        "--audio",
        type=str,
        default=None,
        help="Path to an input WAV file for --dry-run testing.",
    )
    parser.add_argument(
        "--screenshot",
        type=str,
        default=None,
        help="Optional path to a PNG screenshot for --dry-run testing.",
    )
    parser.add_argument(
        "--window-title",
        type=str,
        default="Dictating-app - main.py - Visual Studio Code",
        help="Simulated active window title for --dry-run testing.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["dictation", "thinking", "debug"],
        default="dictation",
        help="Operation mode to test in --dry-run.",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List all built-in models and their families and exit.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    cli_args = parse_args()

    if cli_args.list_models:
        print("Available Models in Dictating-app:")
        for spec in AVAILABLE_MODELS:
            print(
                f"  - {spec.model_id:<30} | family={spec.family:<16} | {spec.display_name}"
            )
        sys.exit(0)

    if cli_args.dry_run:
        sys.exit(run_cli_dry_run(cli_args))

    app = DictatingApp(
        model_override=cli_args.model,
        transcribe_mode_override=cli_args.transcribe_mode,
    )
    app.run()
