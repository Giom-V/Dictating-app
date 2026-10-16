"""
Gemini and Transcribe API client for Dictating-app.

Handles audio transcription, multimodal context-aware dictation, Thinking Mode
(`F9`), and Debug Mode (`Ctrl+F9`). Dynamically adapts request payloads,
generation configs, and prompts based on the active model's family:
- `transcribe` (`gemini-3.5-transcribe`): Audio-only payload with
  `AudioTranscriptionConfig` (`SMART` or `VERBATIM` mode + contextual
  `custom_vocabulary` extracted from the active window title).
- `gemini_3_flash` (`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite-preview`,
  `gemini-3.5-flash`, `gemini-3-flash-preview`): Multimodal payload (audio +
  cursor-highlighted screenshot) with XML-structured prompts and
  `thinking_level="MINIMAL"`.
- `gemini_2_5_flash` (`gemini-2.5-flash-lite`): Multimodal payload with strict
  imperative anti-OCR guardrails.
- `gemini_pro` (`gemini-3.1-pro-preview`, `gemini-3-pro-preview`): Multimodal
  payload with semantic editing instructions and `thinking_level="LOW"`.
"""

import io
import json
import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:  # type: ignore
        return False
from google import genai
from google.genai import types
from PIL import Image

from config import (
    DEFAULT_DICTATION_MODEL,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_THINKING_MODEL,
    DEFAULT_TRANSCRIBE_MODE,
    FAMILY_TRANSCRIBE,
    TRANSCRIBE_MODES,
    get_model_family,
    get_model_spec,
    load_app_config,
    model_supports_visual_context,
)
from logger_setup import log_llm_request, log_llm_response, setup_logging
from prompts import (
    build_debug_prompt,
    build_dictation_prompts_by_family,
    build_thinking_router_prompt,
    build_transcribe_config_dict,
    clean_transcription_output,
)

load_dotenv()
logger = setup_logging()


def extract_text_from_response(response: Any) -> str:
    """Extract text from either `audio_transcription` parts or standard `text` parts.

    `gemini-3.5-transcribe` returns its transcript inside
    `candidate.content.parts[].audio_transcription.text` rather than `part.text`,
    causing `response.text` to return `None` and emit a SDK warning. Inspecting
    `parts` directly supports both ASR and standard Gemini LLMs without warnings.

    Args:
        response: `GenerateContentResponse` returned by `google-genai`.

    Returns:
        Concatenated transcript or text response string (empty string if none).
    """
    if response is None:
        return ""

    collected: List[str] = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            # 1. Check `audio_transcription` (used by gemini-3.5-transcribe)
            audio_trans = getattr(part, "audio_transcription", None)
            if audio_trans is not None:
                trans_text = getattr(audio_trans, "text", None)
                if trans_text:
                    collected.append(trans_text)
                    continue

            # 2. Check standard `text` part (skip internal thought parts if flagged)
            if getattr(part, "thought", False):
                continue
            part_text = getattr(part, "text", None)
            if part_text:
                collected.append(part_text)

    if collected:
        return "".join(collected)

    # Fallback for mock objects or non-standard responses
    fallback_text = getattr(response, "text", None)
    return fallback_text if isinstance(fallback_text, str) else ""


class GeminiClient:
    """Client orchestrating Gemini Transcribe and Multimodal LLM calls."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        transcribe_mode: Optional[str] = None,
        config_data: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize the Gemini API client and model configuration.

        Args:
            model_name: Optional override for the active dictation model ID.
            transcribe_mode: Optional override for Transcribe mode ('SMART' or 'VERBATIM').
            config_data: Optional pre-loaded configuration dictionary.
            dry_run: When True, prevents clipboard/system mutations during tests.

        Raises:
            ValueError: If `GEMINI_API_KEY` is not set in the environment.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables.")

        self.client = genai.Client(api_key=api_key)
        self.dry_run = dry_run

        cfg = config_data if config_data is not None else load_app_config()
        self.model_name: str = (
            model_name or cfg.get("model_name") or DEFAULT_DICTATION_MODEL
        ).strip()
        self.transcribe_mode: str = (
            transcribe_mode or cfg.get("transcribe_mode") or DEFAULT_TRANSCRIBE_MODE
        ).upper()
        if self.transcribe_mode not in TRANSCRIBE_MODES:
            self.transcribe_mode = DEFAULT_TRANSCRIBE_MODE

        self.thinking_model: str = cfg.get("thinking_model") or DEFAULT_THINKING_MODEL
        self.image_model: str = cfg.get("image_model") or DEFAULT_IMAGE_MODEL
        self.custom_vocabulary: List[str] = list(cfg.get("custom_vocabulary") or [])
        self.language_codes: List[str] = list(cfg.get("language_codes") or [])

        logger.info(
            "Initialized GeminiClient | model=%s | family=%s | transcribe_mode=%s | "
            "thinking_model=%s | dry_run=%s",
            self.model_name,
            self.get_active_family(),
            self.transcribe_mode,
            self.thinking_model,
            self.dry_run,
        )

    def get_active_family(self) -> str:
        """Return the model family identifier for the currently selected model."""
        return get_model_family(self.model_name)

    def requires_visual_context(self, mode: str = "dictation") -> bool:
        """Determine whether a screenshot should be captured for the given mode.

        In standard `dictation` mode (`F8`), `transcribe`-family models
        (`gemini-3.5-transcribe`) only accept audio input and reject images,
        so skipping screenshot capture reduces latency and CPU usage.
        In `thinking` (`F9`) and `debug` (`Ctrl+F9`) modes, visual context is
        always captured.

        Args:
            mode: Operation mode ('dictation', 'thinking', or 'debug').

        Returns:
            True if a screenshot should be captured, False otherwise.
        """
        if mode in ("thinking", "debug"):
            return True
        return model_supports_visual_context(self.model_name)

    def set_model(self, model_name: str) -> None:
        """Switch the active dictation model at runtime.

        Args:
            model_name: Target Gemini or Transcribe model identifier.
        """
        cleaned = model_name.strip()
        old_model = self.model_name
        self.model_name = cleaned
        logger.info(
            "Switched dictation model: %s -> %s (family=%s)",
            old_model,
            self.model_name,
            self.get_active_family(),
        )

    def set_transcribe_mode(self, mode: str) -> None:
        """Switch the transcription mode ('SMART' or 'VERBATIM') for Transcribe models.

        Args:
            mode: Either 'SMART' or 'VERBATIM'.
        """
        normalized = mode.strip().upper()
        if normalized not in TRANSCRIBE_MODES:
            logger.warning("Ignored invalid transcribe_mode %r", mode)
            return
        old_mode = self.transcribe_mode
        self.transcribe_mode = normalized
        logger.info("Switched transcribe_mode: %s -> %s", old_mode, self.transcribe_mode)

    def _generate_with_retry(
        self,
        model: str,
        contents: List[Any],
        config: Any = None,
        retries: int = 3,
        delay: float = 1.5,
    ) -> Any:
        """Call `client.models.generate_content` with exponential backoff on transient errors.

        Args:
            model: Target model identifier.
            contents: List of `types.Part` and/or prompt strings.
            config: `types.GenerateContentConfig` or dict.
            retries: Maximum number of attempts.
            delay: Base retry delay in seconds.

        Returns:
            `GenerateContentResponse` from the Gemini API.

        Raises:
            Exception: Re-raises the last exception if all retries fail or if the
                error is a non-retryable client error.
        """
        for attempt in range(retries):
            try:
                kwargs: Dict[str, Any] = {"model": model, "contents": contents}
                if config is not None:
                    kwargs["config"] = config
                return self.client.models.generate_content(**kwargs)
            except Exception as exc:
                error_str = str(exc)
                is_transient = any(
                    code in error_str
                    for code in ("503", "429", "500", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded")
                )
                if is_transient and attempt < retries - 1:
                    wait_time = delay * (2**attempt)
                    logger.warning(
                        "Transient API error on model=%s (%s). Retrying in %.1fs (attempt %d/%d)...",
                        model,
                        error_str[:160],
                        wait_time,
                        attempt + 1,
                        retries,
                    )
                    time.sleep(wait_time)
                else:
                    raise

    def _load_audio_part(self, audio_path: str) -> Tuple[types.Part, int]:
        """Read an audio file from disk and wrap it in a `types.Part`."""
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")
        return part, len(audio_bytes)

    def _load_image_part(self, image_path: Optional[str]) -> Tuple[Optional[types.Part], int]:
        """Read an optional screenshot PNG from disk and wrap it in a `types.Part`."""
        if not image_path or not os.path.exists(image_path):
            return None, 0
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
            return part, len(image_bytes)
        except OSError as exc:
            logger.warning("Failed to load screenshot at %s: %s", image_path, exc)
            return None, 0

    def _transcribe_with_asr_model(
        self,
        model_name: str,
        audio_part: types.Part,
        audio_size: int,
        window_title: Optional[str],
        mode_label: str = "dictation",
    ) -> str:
        """Execute a transcription call using a `transcribe`-family ASR model.

        Configures `AudioTranscriptionConfig` (`SMART` or `VERBATIM` + dynamic
        window vocabulary) and extracts `part.audio_transcription.text`.

        Args:
            model_name: Transcribe model ID (e.g., `gemini-3.5-transcribe`).
            audio_part: `types.Part` containing WAV audio bytes.
            audio_size: Size of the audio payload in bytes.
            window_title: Active window title for custom vocabulary extraction.
            mode_label: Mode label for logging ('dictation', 'thinking-step0', etc.).

        Returns:
            Cleaned transcript string.
        """
        transcribe_cfg_dict = build_transcribe_config_dict(
            window_title=window_title,
            transcribe_mode=self.transcribe_mode,
            user_vocabulary=self.custom_vocabulary,
            language_codes=self.language_codes,
        )

        if hasattr(types, "AudioTranscriptionConfig"):
            gen_config: Any = types.GenerateContentConfig(
                audio_transcription_config=types.AudioTranscriptionConfig(
                    **transcribe_cfg_dict
                )
            )
        else:
            gen_config = {"audio_transcription_config": transcribe_cfg_dict}

        log_llm_request(
            logger=logger,
            model_name=model_name,
            model_family=FAMILY_TRANSCRIBE,
            mode=mode_label,
            config_summary={"audio_transcription_config": transcribe_cfg_dict},
            prompt_text=None,
            system_instruction=None,
            media_summary=[f"audio/wav ({audio_size} bytes)"],
        )

        t0 = time.perf_counter()
        response = self._generate_with_retry(
            model=model_name,
            contents=[audio_part],
            config=gen_config,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        raw_text = extract_text_from_response(response)
        cleaned_text = clean_transcription_output(raw_text)

        log_llm_response(
            logger=logger,
            model_name=model_name,
            model_family=FAMILY_TRANSCRIBE,
            mode=mode_label,
            elapsed_ms=elapsed_ms,
            response_text=cleaned_text,
            extra_info=f"raw_chars={len(raw_text)}",
        )
        return cleaned_text

    def _dictate_with_multimodal_family(
        self,
        model_name: str,
        audio_part: types.Part,
        audio_size: int,
        image_part: Optional[types.Part],
        image_size: int,
        window_title: Optional[str],
    ) -> str:
        """Execute context-aware dictation using a Gemini 2.5, 3.x Flash, or Pro model.

        Selects the family-specific prompt template and thinking configuration.

        Args:
            model_name: Multimodal Gemini model ID.
            audio_part: WAV audio part.
            audio_size: Audio size in bytes.
            image_part: Optional PNG screenshot part with cursor highlight.
            image_size: Image size in bytes.
            window_title: Title of the active application window.

        Returns:
            Cleaned text output ready to paste.
        """
        spec = get_model_spec(model_name)
        family = spec.family

        system_instruction, user_prompt = build_dictation_prompts_by_family(
            model_family=family,
            window_title=window_title,
            has_image=image_part is not None,
        )

        contents: List[Any] = [audio_part]
        if user_prompt:
            contents.append(user_prompt)
        if image_part is not None:
            contents.append(image_part)

        config_kwargs: Dict[str, Any] = {
            "system_instruction": system_instruction,
            "temperature": 0.0,
        }
        config_summary: Dict[str, Any] = {"temperature": 0.0}

        if spec.default_thinking_level and hasattr(types, "ThinkingConfig"):
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=spec.default_thinking_level
            )
            config_summary["thinking_level"] = spec.default_thinking_level

        gen_config = types.GenerateContentConfig(**config_kwargs)

        media_summary = [f"audio/wav ({audio_size} bytes)"]
        if image_part is not None:
            media_summary.append(f"image/png ({image_size} bytes)")

        log_llm_request(
            logger=logger,
            model_name=model_name,
            model_family=family,
            mode="dictation",
            config_summary=config_summary,
            prompt_text=user_prompt,
            system_instruction=system_instruction,
            media_summary=media_summary,
        )

        t0 = time.perf_counter()
        response = self._generate_with_retry(
            model=model_name,
            contents=contents,
            config=gen_config,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        raw_text = extract_text_from_response(response)
        cleaned_text = clean_transcription_output(raw_text)

        log_llm_response(
            logger=logger,
            model_name=model_name,
            model_family=family,
            mode="dictation",
            elapsed_ms=elapsed_ms,
            response_text=cleaned_text,
            extra_info=f"raw_chars={len(raw_text)}",
        )
        return cleaned_text

    def process_audio(
        self,
        audio_path: str,
        image_path: Optional[str] = None,
        window_title: Optional[str] = None,
        mode: str = "dictation",
    ) -> Optional[str]:
        """Process recorded audio according to the requested mode and active model family.

        Args:
            audio_path: Path to the recorded WAV file.
            image_path: Optional path to the active monitor screenshot PNG.
            window_title: Optional title of the currently focused window.
            mode: One of 'dictation' (`F8`), 'thinking' (`F9`), or 'debug' (`Ctrl+F9`).

        Returns:
            Text to be pasted (or `"IMAGE_COPIED_TO_CLIPBOARD"` if an image was
            generated in Thinking mode, or `None` on empty/error).
        """
        if not os.path.exists(audio_path):
            logger.error("Audio file not found: %s", audio_path)
            return None

        try:
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            audio_size = len(audio_bytes)
            audio_part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")

            image_part, image_size = self._load_image_part(image_path)
            active_family = self.get_active_family()

            if mode == "dictation":
                if active_family == FAMILY_TRANSCRIBE:
                    return self._transcribe_with_asr_model(
                        model_name=self.model_name,
                        audio_part=audio_part,
                        audio_size=audio_size,
                        window_title=window_title,
                        mode_label="dictation",
                    )
                return self._dictate_with_multimodal_family(
                    model_name=self.model_name,
                    audio_part=audio_part,
                    audio_size=audio_size,
                    image_part=image_part,
                    image_size=image_size,
                    window_title=window_title,
                )

            if mode == "thinking":
                return self._process_thinking_mode(
                    audio_part=audio_part,
                    audio_size=audio_size,
                    image_part=image_part,
                    image_size=image_size,
                    window_title=window_title,
                )

            if mode == "debug":
                return self._process_debug_mode(
                    audio_part=audio_part,
                    audio_size=audio_size,
                    image_part=image_part,
                    image_size=image_size,
                    window_title=window_title,
                )

            logger.error("Unsupported processing mode: %s", mode)
            return None

        except Exception as exc:
            logger.exception("Error processing audio in mode=%s: %s", mode, exc)
            return None

    def _process_thinking_mode(
        self,
        audio_part: types.Part,
        audio_size: int,
        image_part: Optional[types.Part],
        image_size: int,
        window_title: Optional[str],
    ) -> Optional[str]:
        """Handle 2-step Thinking Mode (`F9`): intent routing + text/image generation.

        If the active dictation model is in the `transcribe` family, first runs
        `gemini-3.5-transcribe` to obtain a high-accuracy transcript of the spoken
        command, then supplies that transcript alongside the audio and screenshot
        to the reasoning model (`self.thinking_model`).
        """
        transcribed_command: Optional[str] = None
        if self.get_active_family() == FAMILY_TRANSCRIBE:
            try:
                transcribed_command = self._transcribe_with_asr_model(
                    model_name=self.model_name,
                    audio_part=audio_part,
                    audio_size=audio_size,
                    window_title=window_title,
                    mode_label="thinking-transcribe",
                )
            except Exception as exc:
                logger.warning("Pre-transcription in thinking mode failed, continuing with audio: %s", exc)

        router_sys, router_prompt = build_thinking_router_prompt(
            window_title=window_title,
            transcribed_instruction=transcribed_command,
        )

        contents_step1: List[Any] = [audio_part, router_prompt]
        media_summary = [f"audio/wav ({audio_size} bytes)"]
        if image_part is not None:
            contents_step1.append(image_part)
            media_summary.append(f"image/png ({image_size} bytes)")

        router_family = get_model_family(self.thinking_model)
        step1_config = types.GenerateContentConfig(
            system_instruction=router_sys,
            response_mime_type="application/json",
            temperature=0.2,
        )

        log_llm_request(
            logger=logger,
            model_name=self.thinking_model,
            model_family=router_family,
            mode="thinking-step1-router",
            config_summary={"temperature": 0.2, "response_mime_type": "application/json"},
            prompt_text=router_prompt,
            system_instruction=router_sys,
            media_summary=media_summary,
        )

        t0 = time.perf_counter()
        response_step1 = self._generate_with_retry(
            model=self.thinking_model,
            contents=contents_step1,
            config=step1_config,
        )
        elapsed_step1 = (time.perf_counter() - t0) * 1000.0
        step1_text = extract_text_from_response(response_step1)

        log_llm_response(
            logger=logger,
            model_name=self.thinking_model,
            model_family=router_family,
            mode="thinking-step1-router",
            elapsed_ms=elapsed_step1,
            response_text=step1_text,
        )

        try:
            plan = json.loads(step1_text)
            request_type = plan.get("type", "text")
            refined_prompt = plan.get("refined_prompt", "")
        except json.JSONDecodeError:
            logger.warning("Failed to parse router JSON, falling back to raw text output.")
            return clean_transcription_output(step1_text)

        if request_type == "image":
            return self._generate_thinking_image(refined_prompt)

        # Step 2: Text / Code Drafting
        draft_sys = (
            "You are an expert writer and software engineer. Fulfill the user's "
            "request directly. Output ONLY the requested text or code ready to "
            "be pasted at the cursor, with no conversational intro or outro."
        )
        log_llm_request(
            logger=logger,
            model_name=self.thinking_model,
            model_family=router_family,
            mode="thinking-step2-draft",
            config_summary={"temperature": 0.7},
            prompt_text=refined_prompt,
            system_instruction=draft_sys,
            media_summary=[],
        )

        t1 = time.perf_counter()
        response_step2 = self._generate_with_retry(
            model=self.thinking_model,
            contents=[refined_prompt],
            config=types.GenerateContentConfig(
                system_instruction=draft_sys,
                temperature=0.7,
            ),
        )
        elapsed_step2 = (time.perf_counter() - t1) * 1000.0
        draft_text = clean_transcription_output(extract_text_from_response(response_step2))

        log_llm_response(
            logger=logger,
            model_name=self.thinking_model,
            model_family=router_family,
            mode="thinking-step2-draft",
            elapsed_ms=elapsed_step2,
            response_text=draft_text,
        )
        return draft_text

    def _generate_thinking_image(self, refined_prompt: str) -> str:
        """Generate an image in Step 2 of Thinking Mode and copy it to the clipboard."""
        image_family = get_model_family(self.image_model)
        log_llm_request(
            logger=logger,
            model_name=self.image_model,
            model_family=image_family,
            mode="thinking-step2-image",
            config_summary={},
            prompt_text=refined_prompt,
            system_instruction=None,
            media_summary=[],
        )

        t0 = time.perf_counter()
        try:
            response = self._generate_with_retry(
                model=self.image_model,
                contents=[refined_prompt],
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            candidates = getattr(response, "candidates", None) or []
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                for part in getattr(content, "parts", None) or []:
                    inline_data = getattr(part, "inline_data", None)
                    if inline_data and getattr(inline_data, "data", None):
                        img_bytes = inline_data.data
                        log_llm_response(
                            logger=logger,
                            model_name=self.image_model,
                            model_family=image_family,
                            mode="thinking-step2-image",
                            elapsed_ms=elapsed_ms,
                            response_text="<IMAGE_BYTES>",
                            extra_info=f"image_bytes={len(img_bytes)}",
                        )
                        if self.dry_run:
                            return "IMAGE_GENERATED_DRY_RUN"
                        img = Image.open(io.BytesIO(img_bytes))
                        if self._copy_image_to_clipboard_native(img):
                            return "IMAGE_COPIED_TO_CLIPBOARD"
                        return "Error: Failed to copy image to clipboard."

            return "Error: No image data returned by image model."
        except Exception as exc:
            logger.exception("Image generation failed: %s", exc)
            return f"Error generating image: {exc}"

    def _process_debug_mode(
        self,
        audio_part: types.Part,
        audio_size: int,
        image_part: Optional[types.Part],
        image_size: int,
        window_title: Optional[str],
    ) -> Optional[str]:
        """Run Debug Mode (`Ctrl+F9`), combining ASR transcript + multimodal diagnostics."""
        transcribed_text: Optional[str] = None
        if self.get_active_family() == FAMILY_TRANSCRIBE:
            try:
                transcribed_text = self._transcribe_with_asr_model(
                    model_name=self.model_name,
                    audio_part=audio_part,
                    audio_size=audio_size,
                    window_title=window_title,
                    mode_label="debug-transcribe",
                )
            except Exception as exc:
                logger.warning("Debug mode pre-transcription failed: %s", exc)

        # Use the selected model if multimodal, otherwise use thinking_model for visual debug
        diag_model = (
            self.thinking_model
            if self.get_active_family() == FAMILY_TRANSCRIBE
            else self.model_name
        )
        diag_family = get_model_family(diag_model)
        debug_sys, debug_prompt = build_debug_prompt(
            window_title=window_title,
            transcribed_instruction=transcribed_text,
        )

        contents: List[Any] = [audio_part, debug_prompt]
        media_summary = [f"audio/wav ({audio_size} bytes)"]
        if image_part is not None:
            contents.append(image_part)
            media_summary.append(f"image/png ({image_size} bytes)")

        log_llm_request(
            logger=logger,
            model_name=diag_model,
            model_family=diag_family,
            mode="debug",
            config_summary={"temperature": 0.4},
            prompt_text=debug_prompt,
            system_instruction=debug_sys,
            media_summary=media_summary,
        )

        t0 = time.perf_counter()
        response = self._generate_with_retry(
            model=diag_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=debug_sys,
                temperature=0.4,
            ),
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        report = clean_transcription_output(extract_text_from_response(response))

        log_llm_response(
            logger=logger,
            model_name=diag_model,
            model_family=diag_family,
            mode="debug",
            elapsed_ms=elapsed_ms,
            response_text=report,
        )
        return report

    def _copy_image_to_clipboard_native(self, image: Image.Image) -> bool:
        """Copy a PIL Image to the Windows clipboard via PowerShell."""
        temp_path = os.path.abspath("temp_clipboard.png")
        try:
            image.save(temp_path, "PNG")
            ps_command = (
                f"Add-Type -AssemblyName System.Windows.Forms; "
                f"Add-Type -AssemblyName System.Drawing; "
                f"$img = [System.Drawing.Image]::FromFile('{temp_path}'); "
                f"[System.Windows.Forms.Clipboard]::SetImage($img); "
                f"$img.Dispose();"
            )
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(
                ["powershell", "-Command", ps_command],
                check=True,
                creationflags=creationflags,
            )
            logger.info("Copied generated image to Windows clipboard via PowerShell.")
            return True
        except Exception as exc:
            logger.error("Failed to copy image to clipboard: %s", exc)
            return False
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

