"""
Logging configuration and strict LLM call traceability utilities for Dictating-app.

Provides centralized logger initialization (console + file output) and structured
logging helpers that record every Gemini / Transcribe API call with its model ID,
model family, configuration parameters, media payload sizes, prompt text, latency,
and response summary.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional

LOG_FILE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "dictating_app.log"
)
MAX_PROMPT_LOG_CHARS = 1200


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Initialize and return the root application logger.

    Configures both a stream handler (stdout) and a rotating file handler
    (`dictating_app.log`, up to 5 MB with 2 backups) if not already attached.

    Args:
        level: Logging verbosity level (defaults to logging.INFO).

    Returns:
        Configured logging.Logger instance for 'dictating_app'.
    """
    logger = logging.getLogger("dictating_app")
    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s.%(funcName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        file_handler = RotatingFileHandler(
            LOG_FILE_PATH,
            maxBytes=5 * 1024 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning("Could not initialize log file at %s: %s", LOG_FILE_PATH, exc)

    return logger


def truncate_text(text: Optional[str], max_chars: int = MAX_PROMPT_LOG_CHARS) -> str:
    """Shorten long text strings for readable log entries while preserving length info.

    Args:
        text: Input string to format for logging.
        max_chars: Maximum character threshold before truncating.

    Returns:
        String representation with character count metadata if truncated.
    """
    if text is None:
        return "<None>"
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars]}... [truncated, total={len(cleaned)} chars]"


def log_llm_request(
    logger: logging.Logger,
    model_name: str,
    model_family: str,
    mode: str,
    config_summary: Dict[str, Any],
    prompt_text: Optional[str],
    system_instruction: Optional[str],
    media_summary: List[str],
) -> None:
    """Log full metadata and prompt parameters before executing a Gemini API request.

    Args:
        logger: Active logger instance.
        model_name: Target Gemini or Transcribe model identifier.
        model_family: Resolved model family ('transcribe', 'gemini_3_flash', etc.).
        mode: Operation mode ('dictation', 'thinking', 'debug', etc.).
        config_summary: Dictionary of generation / transcription parameters.
        prompt_text: User/context text prompt sent (or None for pure ASR).
        system_instruction: System instruction sent (or None if disabled for ASR).
        media_summary: Descriptions and byte sizes of attached binary parts.
    """
    logger.info(
        "[LLM REQUEST] model=%s | family=%s | mode=%s | config=%s | media=%s | "
        "system_instruction=%r | prompt=%r",
        model_name,
        model_family,
        mode,
        config_summary,
        media_summary,
        truncate_text(system_instruction, 400),
        truncate_text(prompt_text, 600),
    )


def log_llm_response(
    logger: logging.Logger,
    model_name: str,
    model_family: str,
    mode: str,
    elapsed_ms: float,
    response_text: Optional[str],
    extra_info: Optional[str] = None,
) -> None:
    """Log the response received from a Gemini or Transcribe API call.

    Args:
        logger: Active logger instance.
        model_name: Model identifier that produced the response.
        model_family: Resolved model family.
        mode: Operation mode.
        elapsed_ms: Round-trip request duration in milliseconds.
        response_text: Extracted transcript or generated text output.
        extra_info: Optional metadata (e.g., inline image bytes, JSON routing info).
    """
    char_count = len(response_text) if response_text else 0
    logger.info(
        "[LLM RESPONSE] model=%s | family=%s | mode=%s | latency=%.1fms | "
        "chars=%d | extra=%s | output=%r",
        model_name,
        model_family,
        mode,
        elapsed_ms,
        char_count,
        extra_info or "none",
        truncate_text(response_text, 800),
    )
