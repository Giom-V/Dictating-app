"""
Family-specific prompt templates and transcription config builders for Dictating-app.

Implements distinct prompting strategies tailored to each model family:
- `transcribe` (`gemini-3.5-transcribe`): Builds `AudioTranscriptionConfig` with
  `mode` ('SMART' or 'VERBATIM'), optional `language_codes`, and dynamic
  `custom_vocabulary` extracted from the active window title and user config.
- `gemini_3_flash` (`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite-preview`,
  `gemini-3.5-flash`, `gemini-3-flash-preview`): Concise XML-structured system
  instructions with `thinking_level="MINIMAL"`, supporting inline voice commands,
  live translation, and cursor-aware visual context.
- `gemini_2_5_flash` (`gemini-2.5-flash-lite`): Imperative guardrail-heavy system
  instructions designed to prevent screenshot OCR hallucinations on smaller 2.5
  models.
- `gemini_pro` (`gemini-3.1-pro-preview`, `gemini-3-pro-preview`): Semantic
  dictation and structural editing instructions with `thinking_level="LOW"`, plus
  Thinking Mode (`F9`) and Debug Mode (`Ctrl+F9`) prompts.
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from config import (
    DEFAULT_TRANSCRIBE_MODE,
    FAMILY_GEMINI_2_5_FLASH,
    FAMILY_GEMINI_3_FLASH,
    FAMILY_GEMINI_PRO,
    FAMILY_TRANSCRIBE,
    SYSTEM_INSTRUCTION_PATH,
    TRANSCRIBE_MODE_SMART,
)

# Common generic window title words that should not pollute ASR custom_vocabulary
_WINDOW_STOPWORDS = {
    "google",
    "chrome",
    "mozilla",
    "firefox",
    "microsoft",
    "edge",
    "visual",
    "studio",
    "code",
    "untitled",
    "window",
    "unknown",
    "application",
    "personal",
    "work",
    "profile",
    "tab",
    "new",
    "the",
    "and",
    "for",
    "with",
}

MAX_CUSTOM_VOCABULARY_TERMS = 100


def load_base_user_instruction(path: str = SYSTEM_INSTRUCTION_PATH) -> str:
    """Load the user's base instruction file (`system_instruction.txt`) if present.

    Args:
        path: Path to `system_instruction.txt`.

    Returns:
        Text content of `system_instruction.txt`, or default French instruction.
    """
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except OSError:
            pass
    return (
        "Tu es un assistant vocal invisible pour Windows.\n"
        "L'utilisateur va te dicter du texte ou une commande.\n"
        "Ta tâche est de produire EXACTEMENT le texte que l'utilisateur veut écrire."
    )


def extract_window_vocabulary(
    window_title: Optional[str],
    user_vocabulary: Optional[List[str]] = None,
    max_terms: int = MAX_CUSTOM_VOCABULARY_TERMS,
) -> List[str]:
    """Extract domain terms, identifiers, and proper nouns from the active window title.

    Used by `gemini-3.5-transcribe` to bias speech recognition toward filenames,
    project names, people, or technical identifiers visible in the active window
    title, merged with the user's static `custom_vocabulary`.

    Args:
        window_title: Title of the currently focused application window.
        user_vocabulary: Static list of custom vocabulary terms from config.
        max_terms: Maximum number of vocabulary terms to return (recommended <= 100).

    Returns:
        Deduplicated list of vocabulary strings preserving order.
    """
    seen = set()
    vocab: List[str] = []

    def _add_term(term: str) -> None:
        cleaned = term.strip()
        if not cleaned or len(cleaned) < 2 or len(cleaned) > 60:
            return
        lower = cleaned.lower()
        if lower in _WINDOW_STOPWORDS or lower in seen:
            return
        seen.add(lower)
        vocab.append(cleaned)

    for item in user_vocabulary or []:
        if isinstance(item, str):
            _add_term(item)

    if window_title:
        # Split on separators like " - ", " | ", " — ", "/", "\"
        segments = re.split(r"[\-\|—/\\•:]+", window_title)
        for seg in segments:
            seg_clean = seg.strip()
            # Keep compact multi-word titles or filenames (e.g. "llm_client.py")
            tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_.\-#]+", seg_clean)
            for tok in tokens:
                if tok.isdigit():
                    continue
                _add_term(tok)

    return vocab[:max_terms]


def build_transcribe_config_dict(
    window_title: Optional[str],
    transcribe_mode: str = DEFAULT_TRANSCRIBE_MODE,
    user_vocabulary: Optional[List[str]] = None,
    language_codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build the `AudioTranscriptionConfig` dictionary for `gemini-3.5-transcribe`.

    Note: `gemini-3.5-transcribe` does NOT accept `system_instruction` or image
    inputs. Instead, its behavior is controlled via `AudioTranscriptionConfig`:
    - `mode`: 'SMART' (Voice Vibe Typing: removes hesitations/fillers, resolves
      inline self-corrections, formats lists/punctuation) or 'VERBATIM'.
    - `custom_vocabulary`: Domain/context biasing terms.
    - `language_codes`: Optional BCP-47 language codes.

    Args:
        window_title: Active window title used to extract contextual vocabulary.
        transcribe_mode: Either 'SMART' or 'VERBATIM'.
        user_vocabulary: Static custom vocabulary list from `config.json`.
        language_codes: Optional list of BCP-47 language codes.

    Returns:
        Dictionary suitable for `types.AudioTranscriptionConfig(**result)`.
    """
    normalized_mode = (transcribe_mode or DEFAULT_TRANSCRIBE_MODE).upper().strip()
    if normalized_mode not in ("SMART", "VERBATIM"):
        normalized_mode = TRANSCRIBE_MODE_SMART

    vocab = extract_window_vocabulary(window_title, user_vocabulary)
    cfg: Dict[str, Any] = {"mode": normalized_mode}
    if vocab:
        cfg["custom_vocabulary"] = vocab
    if language_codes:
        cfg["language_codes"] = [str(code).strip() for code in language_codes if str(code).strip()]
    return cfg


def build_dictation_prompts_by_family(
    model_family: str,
    window_title: Optional[str],
    has_image: bool = True,
    base_instruction_path: str = SYSTEM_INSTRUCTION_PATH,
) -> Tuple[Optional[str], Optional[str]]:
    """Return `(system_instruction, user_prompt)` tailored to the given model family.

    - `transcribe`: Returns `(None, None)` because `gemini-3.5-transcribe` is
      configured via `AudioTranscriptionConfig` and rejects `system_instruction`.
    - `gemini_2_5_flash`: Uses strict imperative negative guardrails to prevent
      2.5 Flash-Lite from OCR-ing screenshot text when audio is brief/silent.
    - `gemini_3_flash`: Uses concise XML-structured tags optimized for Gemini 3.x
      instruction following (`<role>`, `<voice_commands>`, `<visual_context>`,
      `<output_contract>`).
    - `gemini_pro`: Uses a rich semantic dictation and structural editing prompt
      leveraging deep multimodal context around the cursor.

    Args:
        model_family: Resolved family identifier (`transcribe`, `gemini_3_flash`,
            `gemini_2_5_flash`, or `gemini_pro`).
        window_title: Title of the active application window.
        has_image: Whether a screenshot with cursor highlight is attached.
        base_instruction_path: Path to `system_instruction.txt`.

    Returns:
        Tuple of `(system_instruction, user_prompt)`.
    """
    if model_family == FAMILY_TRANSCRIBE:
        return None, None

    base_instruction = load_base_user_instruction(base_instruction_path)
    win_ctx = window_title or "Unknown Window"

    if model_family == FAMILY_GEMINI_2_5_FLASH:
        # Legacy Gemini 2.5 Flash-Lite: requires explicit anti-OCR negative rules
        system_instruction = (
            f"{base_instruction}\n\n"
            "CRITICAL RULES FOR GEMINI 2.5:\n"
            "1. PRIMARY SOURCE IS AUDIO: Your ONLY job is to transcribe or execute "
            "what is spoken in the AUDIO file.\n"
            "2. DO NOT TRANSCRIBE THE SCREENSHOT: Never copy or read out text from "
            "the attached screenshot unless the speaker explicitly asks to reference it.\n"
            "3. SILENCE / NOISE: If the audio contains only silence, breathing, or "
            "background noise with no intelligible speech, output NOTHING (empty string).\n"
            "4. SELF-CORRECTION & CLEANUP: Remove filler words ('euh', 'um', 'uh'), "
            "stutters, and false starts. If the speaker corrects themselves, keep only "
            "the final intended phrasing.\n"
            "5. VISUAL CONTEXT FOR SPELLING & TONE ONLY: Use the window title and the "
            "area near the red circle (cursor) solely to spell proper nouns/technical "
            "terms accurately and match capitalization/formatting.\n"
            "6. RAW OUTPUT ONLY: Output ONLY the final text to paste. Never wrap in "
            "quotes, never add 'Voici le texte', and never use ```markdown``` fences "
            "unless dictating code inside an IDE."
        )
        user_prompt = (
            f"Active Window Title: {win_ctx}\n"
            "Task: Transcribe or execute the spoken audio command above. "
            "Remember: DO NOT transcribe text from the screenshot."
        )
        return system_instruction, user_prompt

    if model_family == FAMILY_GEMINI_3_FLASH:
        # Gemini 3.x Flash / Flash-Lite: XML-structured, concise, low-latency instruction
        visual_clause = (
            "An image of the active screen is attached with a translucent red circle "
            "marking the user's cursor. Use the visual context and window title ONLY "
            "to infer proper noun spelling, technical identifiers, and register (e.g., "
            "chat vs. email vs. code editor). Never OCR or transcribe screen text "
            "unless explicitly instructed by voice."
            if has_image
            else "Use the active window title to infer proper noun spelling and register."
        )
        system_instruction = (
            "<role>\n"
            f"{base_instruction}\n"
            "</role>\n\n"
            "<audio_processing_rules>\n"
            "- Listen to the attached audio recording as the sole source of content.\n"
            "- If the audio is silent or contains no speech, return an empty string.\n"
            "- Strip disfluencies ('euh', 'um', 'uh', 'du coup' when used as filler), "
            "false starts, and inline self-corrections.\n"
            "- If the speaker gives a direct voice command (e.g., 'écris un mail pour...', "
            "'translate this to English', 'format as a bulleted list'), execute the "
            "command and output only the resulting text.\n"
            "</audio_processing_rules>\n\n"
            "<visual_context>\n"
            f"{visual_clause}\n"
            "</visual_context>\n\n"
            "<output_contract>\n"
            "Return ONLY the exact text to be pasted at the cursor. No conversational "
            "preamble, no surrounding quotes, and no outer markdown code fences.\n"
            "</output_contract>"
        )
        user_prompt = (
            f"<context window_title={win_ctx!r} />\n"
            "Process the attached audio according to <audio_processing_rules> and "
            "return only the text required by <output_contract>."
        )
        return system_instruction, user_prompt

    # FAMILY_GEMINI_PRO (`gemini-3.1-pro-preview`, `gemini-3-pro-preview`)
    system_instruction = (
        "<role>\n"
        f"{base_instruction}\n"
        "You are operating in high-precision Pro dictation & semantic editing mode.\n"
        "</role>\n\n"
        "<capabilities>\n"
        "1. Smart Dictation: Produce publication-ready text from the user's speech, "
        "resolving complex self-corrections, structural edits, and spoken punctuation.\n"
        "2. Context-Aware Drafting & Code: Use the active window title and the screenshot "
        "(where the red circle marks the cursor) to resolve variable names, file names, "
        "recipient names, and formatting conventions of the target app.\n"
        "3. Voice Instructions: If the user states a high-level instruction (e.g., "
        "'réponds à ce message en acceptant la réunion de jeudi', 'refactor this function "
        "to be async'), synthesize the exact response or code snippet ready to be pasted.\n"
        "4. Silence Guardrail: If no intelligible speech is present in the audio, return "
        "an empty string.\n"
        "</capabilities>\n\n"
        "<output_contract>\n"
        "Output ONLY the raw text or code to be inserted at the cursor. Never include "
        "conversational filler, explanations, or outer ``` fences unless the target app "
        "is a Markdown editor.\n"
        "</output_contract>"
    )
    user_prompt = (
        f"<context window_title={win_ctx!r} />\n"
        "Execute the spoken dictation or instruction from the audio using the visual context."
    )
    return system_instruction, user_prompt


def build_thinking_router_prompt(
    window_title: Optional[str],
    transcribed_instruction: Optional[str] = None,
) -> Tuple[str, str]:
    """Build `(system_instruction, user_prompt)` for Step 1 of Thinking Mode (`F9`).

    Args:
        window_title: Title of the active window.
        transcribed_instruction: Optional pre-transcribed text if `gemini-3.5-transcribe`
            was used to transcribe the user's spoken request first.

    Returns:
        Tuple of `(system_instruction, user_prompt)`.
    """
    system_instruction = (
        "You are an intelligent multimodal routing agent.\n"
        "Analyze the user's voice request (and pre-transcribed text if provided) "
        "alongside the screenshot of their active screen (the red circle indicates "
        "their cursor position).\n\n"
        "Determinewhether the user wants to:\n"
        "1. Generate an IMAGE (e.g., 'create an image of...', 'draw a diagram...', "
        "'generate a picture...').\n"
        "2. Generate TEXT or CODE (e.g., 'write an email...', 'summarize this page...', "
        "'reply to this message...', 'write a Python function...').\n\n"
        "Respond ONLY with a valid JSON object matching this schema:\n"
        "{\n"
        '  "type": "image" | "text",\n'
        '  "refined_prompt": "Detailed, self-contained instructions incorporating '
        'all relevant context from the screen and audio so the downstream generator '
        'can fulfill the request without seeing the original audio."\n'
        "}"
    )
    transcript_block = (
        f"\nPre-transcribed voice command: {transcribed_instruction!r}\n"
        if transcribed_instruction
        else ""
    )
    user_prompt = (
        f"Active Window: {window_title or 'Unknown'}\n"
        f"{transcript_block}"
        "Analyze the request and screen context, and output the routing JSON."
    )
    return system_instruction, user_prompt


def build_debug_prompt(
    window_title: Optional[str],
    transcribed_instruction: Optional[str] = None,
) -> Tuple[str, str]:
    """Build `(system_instruction, user_prompt)` for Debug Mode (`Ctrl+F9`).

    Args:
        window_title: Title of the active window.
        transcribed_instruction: Optional pre-transcribed text from `gemini-3.5-transcribe`.

    Returns:
        Tuple of `(system_instruction, user_prompt)`.
    """
    system_instruction = (
        "You are a diagnostic assistant for a Windows voice dictation & multimodal app.\n"
        "Analyze the provided audio (and/or pre-transcribed speech) and screenshot.\n"
        "Provide a concise diagnostic report covering:\n"
        "1. AUDIO: Intelligibility, language detected, transcription accuracy, and "
        "background noise level.\n"
        "2. VISUAL CONTEXT: Active application, what is under the red cursor circle, "
        "and relevant on-screen context.\n"
        "3. INTENT: What action the user is requesting."
    )
    transcript_block = (
        f"\nTranscribe Model Output: {transcribed_instruction!r}\n"
        if transcribed_instruction
        else ""
    )
    user_prompt = (
        f"Active Window: {window_title or 'Unknown'}\n"
        f"{transcript_block}"
        "Generate the diagnostic report."
    )
    return system_instruction, user_prompt


def clean_transcription_output(text: Optional[str]) -> str:
    """Clean raw model output by removing `<noise>` tags and outer markdown fences.

    Args:
        text: Raw string returned by Transcribe or Gemini model.

    Returns:
        Cleaned string ready to be pasted (or empty string if only noise/silence).
    """
    if not text:
        return ""

    cleaned = text.strip()
    # Strip <noise>, [noise], <silence> tokens emitted by ASR models on silent clips
    cleaned = re.sub(r"^(?:<noise>|\[noise\]|<silence>|\s)+$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*<noise>\s*", " ", cleaned, flags=re.IGNORECASE).strip()

    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 2:
            cleaned = "\n".join(lines[1:-1]).strip()

    return cleaned
