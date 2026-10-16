"""
Unit tests for Dictating-app model families, prompting strategies, and response parsing.

Covers:
- Model family resolution (`transcribe`, `gemini_3_flash`, `gemini_2_5_flash`, `gemini_pro`)
  including custom pre-release model IDs.
- Visual context requirement detection (`False` for `transcribe` in dictation mode,
  `True` for multimodal families and Thinking/Debug modes).
- `AudioTranscriptionConfig` dictionary generation (`SMART` vs `VERBATIM`, window
  title vocabulary extraction, language codes).
- Family-specific prompt builders (`build_dictation_prompts_by_family`).
- Response extraction from `audio_transcription` parts vs standard `text` parts.
- `<noise>` and markdown fence cleanup.
"""

import os
import tempfile
import types as py_types
import unittest

from config import (
    DEFAULT_DICTATION_MODEL,
    FAMILY_GEMINI_2_5_FLASH,
    FAMILY_GEMINI_3_FLASH,
    FAMILY_GEMINI_PRO,
    FAMILY_TRANSCRIBE,
    TRANSCRIBE_MODE_SMART,
    TRANSCRIBE_MODE_VERBATIM,
    get_model_family,
    get_model_spec,
    load_app_config,
    model_supports_visual_context,
    save_app_config,
)
from llm_client import extract_text_from_response
from prompts import (
    build_dictation_prompts_by_family,
    build_transcribe_config_dict,
    clean_transcription_output,
    extract_window_vocabulary,
)


class TestModelConfigAndFamilies(unittest.TestCase):
    """Test model catalog, family classification, and config persistence."""

    def test_default_model_is_transcribe(self) -> None:
        """Default dictation model must be `gemini-3.5-transcribe`."""
        self.assertEqual(DEFAULT_DICTATION_MODEL, "gemini-3.5-transcribe")
        self.assertEqual(get_model_family(DEFAULT_DICTATION_MODEL), FAMILY_TRANSCRIBE)

    def test_family_classification_builtin_and_custom(self) -> None:
        """Verify built-in and custom pre-release model IDs resolve to the right family."""
        self.assertEqual(get_model_family("gemini-3.5-transcribe"), FAMILY_TRANSCRIBE)
        self.assertEqual(get_model_family("gemini-4.0-transcribe-preview"), FAMILY_TRANSCRIBE)
        self.assertEqual(get_model_family("gemini-3.5-flash-lite"), FAMILY_GEMINI_3_FLASH)
        self.assertEqual(get_model_family("gemini-3.1-flash-lite-preview"), FAMILY_GEMINI_3_FLASH)
        self.assertEqual(get_model_family("gemini-3.5-flash"), FAMILY_GEMINI_3_FLASH)
        self.assertEqual(get_model_family("gemini-3.8-flash"), FAMILY_GEMINI_3_FLASH)
        self.assertEqual(get_model_family("gemini-2.5-flash-lite"), FAMILY_GEMINI_2_5_FLASH)
        self.assertEqual(get_model_family("gemini-3.1-pro-preview"), FAMILY_GEMINI_PRO)
        self.assertEqual(get_model_family("gemini-3-pro-preview"), FAMILY_GEMINI_PRO)

    def test_visual_context_support(self) -> None:
        """Transcribe models reject image inputs; multimodal families accept them."""
        self.assertFalse(model_supports_visual_context("gemini-3.5-transcribe"))
        self.assertTrue(model_supports_visual_context("gemini-3.5-flash-lite"))
        self.assertTrue(model_supports_visual_context("gemini-2.5-flash-lite"))
        self.assertTrue(model_supports_visual_context("gemini-3.1-pro-preview"))

    def test_thinking_levels_by_family(self) -> None:
        """Verify default thinking levels per model family."""
        self.assertIsNone(get_model_spec("gemini-3.5-transcribe").default_thinking_level)
        self.assertEqual(get_model_spec("gemini-3.5-flash-lite").default_thinking_level, "MINIMAL")
        self.assertIsNone(get_model_spec("gemini-2.5-flash-lite").default_thinking_level)
        self.assertEqual(get_model_spec("gemini-3.1-pro-preview").default_thinking_level, "LOW")

    def test_config_persistence_and_dry_run(self) -> None:
        """Verify config loading, saving, and dry-run non-mutation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "config.json")
            save_app_config(
                {"model_name": "gemini-3.5-flash-lite", "transcribe_mode": "VERBATIM"},
                config_path=cfg_path,
                dry_run=True,
            )
            self.assertFalse(os.path.exists(cfg_path))

            save_app_config(
                {"model_name": "gemini-3.5-flash-lite", "transcribe_mode": "VERBATIM"},
                config_path=cfg_path,
                dry_run=False,
            )
            loaded = load_app_config(cfg_path)
            self.assertEqual(loaded["model_name"], "gemini-3.5-flash-lite")
            self.assertEqual(loaded["transcribe_mode"], "VERBATIM")


class TestFamilyPrompting(unittest.TestCase):
    """Test family-specific prompt templates and Transcribe config builders."""

    def test_transcribe_family_config_builder(self) -> None:
        """Verify `AudioTranscriptionConfig` builder extracts window vocabulary and mode."""
        cfg = build_transcribe_config_dict(
            window_title="Dictating-app - llm_client.py - Visual Studio Code",
            transcribe_mode=TRANSCRIBE_MODE_SMART,
            user_vocabulary=["PyStray", "GeminiClient"],
            language_codes=["fr-FR", "en-US"],
        )
        self.assertEqual(cfg["mode"], TRANSCRIBE_MODE_SMART)
        self.assertIn("PyStray", cfg["custom_vocabulary"])
        self.assertIn("llm_client.py", cfg["custom_vocabulary"])
        self.assertNotIn("visual", [w.lower() for w in cfg["custom_vocabulary"]])
        self.assertEqual(cfg["language_codes"], ["fr-FR", "en-US"])

    def test_transcribe_family_returns_no_system_instruction(self) -> None:
        """`gemini-3.5-transcribe` must not receive a `system_instruction`."""
        sys_inst, usr_prompt = build_dictation_prompts_by_family(
            FAMILY_TRANSCRIBE, window_title="Slack"
        )
        self.assertIsNone(sys_inst)
        self.assertIsNone(usr_prompt)

    def test_distinct_prompts_per_multimodal_family(self) -> None:
        """Each multimodal family must receive a tailored system instruction and prompt."""
        sys_25, usr_25 = build_dictation_prompts_by_family(
            FAMILY_GEMINI_2_5_FLASH, window_title="Gmail"
        )
        sys_3f, usr_3f = build_dictation_prompts_by_family(
            FAMILY_GEMINI_3_FLASH, window_title="Gmail"
        )
        sys_pro, usr_pro = build_dictation_prompts_by_family(
            FAMILY_GEMINI_PRO, window_title="Gmail"
        )

        self.assertIsNotNone(sys_25)
        self.assertIsNotNone(sys_3f)
        self.assertIsNotNone(sys_pro)

        self.assertIn("CRITICAL RULES FOR GEMINI 2.5", sys_25 or "")
        self.assertIn("DO NOT TRANSCRIBE THE SCREENSHOT", sys_25 or "")

        self.assertIn("<audio_processing_rules>", sys_3f or "")
        self.assertIn("<output_contract>", sys_3f or "")

        self.assertIn("Pro dictation & semantic editing mode", sys_pro or "")
        self.assertNotEqual(sys_25, sys_3f)
        self.assertNotEqual(sys_3f, sys_pro)


class TestResponseExtractionAndCleaning(unittest.TestCase):
    """Test extraction from `audio_transcription` parts and `<noise>` cleanup."""

    def test_extract_audio_transcription_part(self) -> None:
        """Verify `extract_text_from_response` reads `part.audio_transcription.text`."""
        mock_part = py_types.SimpleNamespace(
            audio_transcription=py_types.SimpleNamespace(text="Bonjour tout le monde."),
            text=None,
            thought=False,
        )
        mock_resp = py_types.SimpleNamespace(
            candidates=[
                py_types.SimpleNamespace(
                    content=py_types.SimpleNamespace(parts=[mock_part])
                )
            ],
            text=None,
        )
        self.assertEqual(extract_text_from_response(mock_resp), "Bonjour tout le monde.")

    def test_extract_standard_text_ignoring_thoughts(self) -> None:
        """Verify thought parts are ignored and text parts are concatenated."""
        thought_part = py_types.SimpleNamespace(
            audio_transcription=None, text="Internal reasoning...", thought=True
        )
        answer_part = py_types.SimpleNamespace(
            audio_transcription=None, text="Final dictated text.", thought=False
        )
        mock_resp = py_types.SimpleNamespace(
            candidates=[
                py_types.SimpleNamespace(
                    content=py_types.SimpleNamespace(parts=[thought_part, answer_part])
                )
            ]
        )
        self.assertEqual(extract_text_from_response(mock_resp), "Final dictated text.")

    def test_clean_transcription_output(self) -> None:
        """Verify `<noise>` tokens and outer markdown code fences are stripped."""
        self.assertEqual(clean_transcription_output("<noise>"), "")
        self.assertEqual(clean_transcription_output("  <noise> <silence> "), "")
        self.assertEqual(
            clean_transcription_output("Hello <noise> world"),
            "Hello world",
        )
        self.assertEqual(
            clean_transcription_output("```python\nprint('hi')\n```"),
            "print('hi')",
        )


if __name__ == "__main__":
    unittest.main()
