"""
Unit tests for `GeminiClient._generate_with_retry` transient error retry logic.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from llm_client import GeminiClient


class TestGenerateWithRetry(unittest.TestCase):
    """Verify retry behavior on transient 503/429 errors vs permanent 400 errors."""

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-dummy-key"})
    @patch("llm_client.genai.Client")
    def test_retries_on_503_then_succeeds(self, mock_client_cls: MagicMock) -> None:
        """Verify `_generate_with_retry` retries on 503 UNAVAILABLE and returns response."""
        mock_instance = mock_client_cls.return_value
        expected_resp = MagicMock()
        mock_instance.models.generate_content.side_effect = [
            RuntimeError("503 UNAVAILABLE: Model is overloaded"),
            expected_resp,
        ]

        client = GeminiClient(dry_run=True)
        res = client._generate_with_retry(
            model="gemini-3.5-transcribe",
            contents=["dummy"],
            retries=3,
            delay=0.01,
        )
        self.assertIs(res, expected_resp)
        self.assertEqual(mock_instance.models.generate_content.call_count, 2)

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-dummy-key"})
    @patch("llm_client.genai.Client")
    def test_does_not_retry_on_400_invalid_argument(self, mock_client_cls: MagicMock) -> None:
        """Verify `_generate_with_retry` raises immediately on non-transient 400 errors."""
        mock_instance = mock_client_cls.return_value
        mock_instance.models.generate_content.side_effect = RuntimeError(
            "400 INVALID_ARGUMENT: Developer instruction is not enabled"
        )

        client = GeminiClient(dry_run=True)
        with self.assertRaises(RuntimeError):
            client._generate_with_retry(
                model="gemini-3.5-transcribe",
                contents=["dummy"],
                retries=3,
                delay=0.01,
            )
        self.assertEqual(mock_instance.models.generate_content.call_count, 1)


if __name__ == "__main__":
    unittest.main()
