"""
Centralized configuration, model catalog, and family resolution for Dictating-app.

Defines the supported dictation models across four distinct families:
1. `transcribe` (`gemini-3.5-transcribe`): Dedicated ASR model using
   `AudioTranscriptionConfig` (audio-only input, SMART or VERBATIM mode,
   custom vocabulary biasing, no `system_instruction` or image input).
2. `gemini_3_flash` (`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite-preview`,
   `gemini-3.5-flash`, `gemini-3-flash-preview`): Next-generation multimodal
   models using XML-structured prompts, visual screen context, and minimal
   thinking latency (`thinking_level="MINIMAL"`).
3. `gemini_2_5_flash` (`gemini-2.5-flash-lite`): Legacy ultra-fast multimodal
   model requiring strict negative constraints to avoid screenshot OCR leaks.
4. `gemini_pro` (`gemini-3.1-pro-preview`, `gemini-3-pro-preview`): Reasoning
   multimodal models for complex dictation, Thinking Mode (`F9`), and Debug
   Mode (`Ctrl+F9`).
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("dictating_app")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SYSTEM_INSTRUCTION_PATH = os.path.join(BASE_DIR, "system_instruction.txt")

# Hotkeys
HOTKEY_DICTATION = "f8"
HOTKEY_THINKING = "f9"
HOTKEY_DEBUG = "ctrl+f9"

# Model Family Identifiers
FAMILY_TRANSCRIBE = "transcribe"
FAMILY_GEMINI_3_FLASH = "gemini_3_flash"
FAMILY_GEMINI_2_5_FLASH = "gemini_2_5_flash"
FAMILY_GEMINI_PRO = "gemini_pro"

# Default Models
DEFAULT_DICTATION_MODEL = "gemini-3.5-transcribe"
DEFAULT_THINKING_MODEL = "gemini-3.1-pro-preview"
DEFAULT_IMAGE_MODEL = "gemini-3-pro-image-preview"

# Transcribe Modes for `gemini-3.5-transcribe`
TRANSCRIBE_MODE_SMART = "SMART"
TRANSCRIBE_MODE_VERBATIM = "VERBATIM"
DEFAULT_TRANSCRIBE_MODE = TRANSCRIBE_MODE_SMART

TRANSCRIBE_MODES: Dict[str, str] = {
    TRANSCRIBE_MODE_SMART: "Smart (Clean, Auto-Format & Self-Corrections)",
    TRANSCRIBE_MODE_VERBATIM: "Verbatim (Raw Word-for-Word)",
}


@dataclass(frozen=True)
class ModelSpec:
    """Metadata specification for a selectable model in Dictating-app."""

    model_id: str
    display_name: str
    family: str
    supports_image_input: bool
    supports_system_instruction: bool
    default_thinking_level: Optional[str] = None
    description: str = ""


AVAILABLE_MODELS: List[ModelSpec] = [
    ModelSpec(
        model_id="gemini-3.5-transcribe",
        display_name="Gemini 3.5 Transcribe [ASR Default]",
        family=FAMILY_TRANSCRIBE,
        supports_image_input=False,
        supports_system_instruction=False,
        default_thinking_level=None,
        description=(
            "Dedicated speech-to-text model with Smart VVT mode (filler removal, "
            "self-correction resolution, custom vocabulary biasing)."
        ),
    ),
    ModelSpec(
        model_id="gemini-3.5-flash-lite",
        display_name="Gemini 3.5 Flash-Lite [Gemini 3 Multimodal]",
        family=FAMILY_GEMINI_3_FLASH,
        supports_image_input=True,
        supports_system_instruction=True,
        default_thinking_level="MINIMAL",
        description="Fast Gemini 3.5 multimodal model with screen context and voice commands.",
    ),
    ModelSpec(
        model_id="gemini-3.1-flash-lite-preview",
        display_name="Gemini 3.1 Flash-Lite [Gemini 3 Multimodal]",
        family=FAMILY_GEMINI_3_FLASH,
        supports_image_input=True,
        supports_system_instruction=True,
        default_thinking_level="MINIMAL",
        description="Low-latency Gemini 3.1 Flash-Lite multimodal dictation.",
    ),
    ModelSpec(
        model_id="gemini-3.5-flash",
        display_name="Gemini 3.5 Flash [Gemini 3 Multimodal]",
        family=FAMILY_GEMINI_3_FLASH,
        supports_image_input=True,
        supports_system_instruction=True,
        default_thinking_level="MINIMAL",
        description="Balanced Gemini 3.5 Flash for context-aware dictation and translation.",
    ),
    ModelSpec(
        model_id="gemini-3-flash-preview",
        display_name="Gemini 3.0 Flash [Gemini 3 Multimodal]",
        family=FAMILY_GEMINI_3_FLASH,
        supports_image_input=True,
        supports_system_instruction=True,
        default_thinking_level="MINIMAL",
        description="Gemini 3.0 Flash multimodal model with screen awareness.",
    ),
    ModelSpec(
        model_id="gemini-2.5-flash-lite",
        display_name="Gemini 2.5 Flash-Lite [Legacy Multimodal]",
        family=FAMILY_GEMINI_2_5_FLASH,
        supports_image_input=True,
        supports_system_instruction=True,
        default_thinking_level=None,
        description="Legacy Gemini 2.5 Flash-Lite with strict anti-OCR guardrails.",
    ),
    ModelSpec(
        model_id="gemini-3.1-pro-preview",
        display_name="Gemini 3.1 Pro [Reasoning Multimodal]",
        family=FAMILY_GEMINI_PRO,
        supports_image_input=True,
        supports_system_instruction=True,
        default_thinking_level="LOW",
        description="High-intelligence Gemini 3.1 Pro for complex dictation & restructuring.",
    ),
]

MODEL_REGISTRY: Dict[str, ModelSpec] = {spec.model_id: spec for spec in AVAILABLE_MODELS}


def get_model_family(model_name: str) -> str:
    """Resolve the model family for any model identifier, including custom pre-release IDs.

    Follows Giom's pre-release model rule: never downgrades or rejects unknown model
    names; instead, classifies them into the appropriate prompting family by pattern.

    Args:
        model_name: Model ID string (e.g. 'gemini-3.5-transcribe', 'gemini-3.5-flash-lite').

    Returns:
        One of FAMILY_TRANSCRIBE, FAMILY_GEMINI_3_FLASH, FAMILY_GEMINI_2_5_FLASH,
        or FAMILY_GEMINI_PRO.
    """
    normalized = (model_name or DEFAULT_DICTATION_MODEL).strip().lower()
    if normalized in MODEL_REGISTRY:
        return MODEL_REGISTRY[normalized].family

    if "transcribe" in normalized:
        return FAMILY_TRANSCRIBE
    if "pro" in normalized:
        return FAMILY_GEMINI_PRO
    if "2.5" in normalized or "2.0" in normalized:
        return FAMILY_GEMINI_2_5_FLASH
    return FAMILY_GEMINI_3_FLASH


def get_model_spec(model_name: str) -> ModelSpec:
    """Retrieve or dynamically synthesize a ModelSpec for the given model ID.

    Args:
        model_name: Target model identifier.

    Returns:
        Matching ModelSpec from MODEL_REGISTRY, or a synthesized ModelSpec for
        custom/pre-release model IDs.
    """
    cleaned = (model_name or DEFAULT_DICTATION_MODEL).strip()
    if cleaned in MODEL_REGISTRY:
        return MODEL_REGISTRY[cleaned]

    family = get_model_family(cleaned)
    is_transcribe = family == FAMILY_TRANSCRIBE
    default_thinking: Optional[str] = None
    if family == FAMILY_GEMINI_3_FLASH:
        default_thinking = "MINIMAL"
    elif family == FAMILY_GEMINI_PRO:
        default_thinking = "LOW"

    return ModelSpec(
        model_id=cleaned,
        display_name=f"{cleaned} [Custom/{family}]",
        family=family,
        supports_image_input=not is_transcribe,
        supports_system_instruction=not is_transcribe,
        default_thinking_level=default_thinking,
        description=f"Custom model resolved to family '{family}'.",
    )


def model_supports_visual_context(model_name: str) -> bool:
    """Check whether the given model accepts screenshot image inputs in dictation mode.

    Args:
        model_name: Target model identifier.

    Returns:
        False for `transcribe` family models (which only accept AUDIO modality),
        True for multimodal Gemini families.
    """
    return get_model_spec(model_name).supports_image_input


def load_app_config(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Load persisted user configuration from disk with safe defaults.

    Args:
        config_path: Path to JSON config file.

    Returns:
        Dictionary with normalized configuration keys.
    """
    defaults: Dict[str, Any] = {
        "microphone": None,
        "model_name": os.environ.get("DICTATING_MODEL", DEFAULT_DICTATION_MODEL),
        "transcribe_mode": os.environ.get("DICTATING_TRANSCRIBE_MODE", DEFAULT_TRANSCRIBE_MODE),
        "thinking_model": os.environ.get("DICTATING_THINKING_MODEL", DEFAULT_THINKING_MODEL),
        "image_model": os.environ.get("DICTATING_IMAGE_MODEL", DEFAULT_IMAGE_MODEL),
        "custom_vocabulary": [],
        "language_codes": [],
    }
    if not os.path.exists(config_path):
        return defaults

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            merged = {**defaults, **loaded}
            if merged.get("transcribe_mode") not in TRANSCRIBE_MODES:
                merged["transcribe_mode"] = DEFAULT_TRANSCRIBE_MODE
            return merged
    except Exception as exc:
        logger.warning("Failed to load config from %s: %s", config_path, exc)

    return defaults


def save_app_config(
    config_data: Dict[str, Any],
    config_path: str = DEFAULT_CONFIG_PATH,
    dry_run: bool = False,
) -> bool:
    """Persist application configuration dictionary to `config.json`.

    Args:
        config_data: Dictionary of configuration settings to save.
        config_path: Destination JSON file path.
        dry_run: When True, logs the intended write without mutating disk.

    Returns:
        True if saved (or skipped in dry-run), False on error.
    """
    if dry_run:
        logger.info("[DRY-RUN] Skipping save_app_config to %s: %s", config_path, config_data)
        return True

    try:
        existing: Dict[str, Any] = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing.update(config_data)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        logger.info("Saved configuration to %s: %s", config_path, config_data)
        return True
    except Exception as exc:
        logger.error("Failed to save configuration to %s: %s", config_path, exc)
        return False
