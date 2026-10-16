# Gemini Dictating Agent (Windows)

An invisible push-to-talk AI dictation and multimodal assistant for Windows. Powered by default by **`gemini-3.5-transcribe`** (Google's dedicated speech-to-text model with Smart Voice Vibe Typing), with a live **Model Selector** in the system tray that adapts its prompting and payload architecture across four model families (`transcribe`, `gemini_3_flash`, `gemini_2_5_flash`, and `gemini_pro`).

## Features

* 🎤 **Push-to-Talk (`F8`)**: Hold `F8` to dictate text directly into any Windows application.
* ⚡ **Dedicated ASR by Default (`gemini-3.5-transcribe`)**: Uses `AudioTranscriptionConfig` in **`SMART`** mode (automatically strips filler words like *"euh"* / *"um"*, resolves inline self-corrections, and formats lists/punctuation) or **`VERBATIM`** mode, while extracting active window title keywords into `custom_vocabulary` for domain-accurate spelling.
* 🎛️ **Live Model Selector & Family-Specific Prompting**: Switch models anytime from the system tray (`Model` submenu). Each model family uses a dedicated payload & prompting strategy:
  * **`transcribe` (`gemini-3.5-transcribe`)**: Audio-only payload (`audio/wav`), skips screen capture for sub-second latency, uses `AudioTranscriptionConfig(mode="SMART" | "VERBATIM", custom_vocabulary=[...], language_codes=[...])`, and reads `part.audio_transcription.text`.
  * **`gemini_3_flash` (`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite-preview`, `gemini-3.5-flash`, `gemini-3-flash-preview`)**: Multimodal payload (audio + cursor-highlighted screenshot + window title) with XML-structured instructions (`<role>`, `<audio_processing_rules>`, `<visual_context>`, `<output_contract>`) and `thinking_level="MINIMAL"`.
  * **`gemini_2_5_flash` (`gemini-2.5-flash-lite`)**: Multimodal payload with strict negative anti-OCR guardrails to prevent screenshot text leaks on short audio clips.
  * **`gemini_pro` (`gemini-3.1-pro-preview`)**: High-autonomy semantic dictation and structural code/document editing with `thinking_level="LOW"`.
* 🧠 **Thinking Mode (`F9`)**: 2-step multimodal assistant (intent router + text/code drafting with `gemini-3.1-pro-preview` or image generation with `gemini-3-pro-image-preview` copied directly to the Windows clipboard).
* 🐞 **Debug Mode (`Ctrl+F9`)**: Generates a diagnostic report of audio intelligibility, transcription output, and visual cursor context.
* 📋 **Strict Traceability & Dry-Run Mode**: Logs every API request and response (model, family, config, media sizes, latency, and output) to console and `dictating_app.log`, and provides a `--dry-run` CLI mode for testing without touching the clipboard or Windows hooks.

## Prerequisites

* Windows 10/11 (or Linux/macOS for `--dry-run` CLI testing)
* Python 3.10+
* A microphone
* A Google Gemini API Key (`GEMINI_API_KEY` environment variable or `.env` file)

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Giom-V/Dictating-app.git
   cd Dictating-app
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *(Note: Ensure `google-genai >= 1.60.0` / `2.x` is installed for native `types.AudioTranscriptionConfig` support).*

## Configuration

Set `GEMINI_API_KEY` in your environment or in a `.env` file in the project root:

```env
GEMINI_API_KEY=your_api_key_here
```

Runtime preferences are automatically persisted in [`config.json`](config.json):

```json
{
  "microphone": "Microphone (Insta360 Link 2C)",
  "model_name": "gemini-3.5-transcribe",
  "transcribe_mode": "SMART",
  "thinking_model": "gemini-3.1-pro-preview",
  "image_model": "gemini-3-pro-image-preview",
  "custom_vocabulary": [],
  "language_codes": []
}
```

* **`model_name`**: Active dictation model ID (any built-in or custom pre-release Gemini model ID is supported).
* **`transcribe_mode`**: `"SMART"` (clean, auto-formatted transcription with self-correction resolution) or `"VERBATIM"` (raw word-for-word).
* **`custom_vocabulary`**: Optional list of custom terms, acronyms, or proper nouns to bias `gemini-3.5-transcribe` (merged automatically with tokens extracted from the active window title).
* **`language_codes`**: Optional list of BCP-47 language codes (e.g. `["fr-FR", "en-US"]`). Leave empty `[]` for automatic language detection and code-switching across 85+ languages.

## Usage

### 1. Desktop System Tray Application (Windows)

```bash
python main.py
```

Right-click the system tray icon to:
* **Model**: Switch between `Gemini 3.5 Transcribe`, `Gemini 3.5 Flash-Lite`, `Gemini 3.1 Flash-Lite`, `Gemini 3.5 Flash`, `Gemini 3.0 Flash`, `Gemini 2.5 Flash-Lite`, and `Gemini 3.1 Pro`.
* **Transcribe Mode (ASR)**: Toggle between `Smart (Clean, Auto-Format & Self-Corrections)` and `Verbatim (Raw Word-for-Word)`.
* **Microphone**: Select your preferred physical audio input device.
* **Start with Windows**: Toggle automatic startup on login.
* **Restart / Quit**.

### 2. CLI & `--dry-run` Testing

List all registered models and their families:

```bash
python main.py --list-models
```

Run a non-interactive `--dry-run` transcription test on a WAV file across different model families:

```bash
# Test with default gemini-3.5-transcribe (transcribe family)
python main.py --dry-run --audio sample.wav --model gemini-3.5-transcribe --transcribe-mode SMART

# Test with gemini-3.5-flash-lite (gemini_3_flash family)
python main.py --dry-run --audio sample.wav --model gemini-3.5-flash-lite

# Test with gemini-2.5-flash-lite (gemini_2_5_flash family)
python main.py --dry-run --audio sample.wav --model gemini-2.5-flash-lite

# Test with gemini-3.1-pro-preview (gemini_pro family)
python main.py --dry-run --audio sample.wav --model gemini-3.1-pro-preview
```

### 3. Running Unit Tests

```bash
python -m unittest discover -v
```

## Project Structure

* [`main.py`](main.py): Application entry point, push-to-talk hotkey loop, `pystray` system tray menus (`Model`, `Transcribe Mode`, `Microphone`), and `--dry-run` CLI runner.
* [`config.py`](config.py): Centralized model catalog (`AVAILABLE_MODELS`), model family resolution (`get_model_family`), and `config.json` persistence.
* [`prompts.py`](prompts.py): Family-specific prompt templates (`build_dictation_prompts_by_family`), `AudioTranscriptionConfig` builder (`build_transcribe_config_dict`), window-title vocabulary extractor (`extract_window_vocabulary`), and output sanitizer.
* [`llm_client.py`](llm_client.py): `GeminiClient` handling ASR (`gemini-3.5-transcribe`) and multimodal LLM calls, `part.audio_transcription.text` extraction, retry backoff, and Thinking/Debug modes.
* [`logger_setup.py`](logger_setup.py): Console and rotating file logger (`dictating_app.log`) with structured LLM request/response traceability.
* [`context_provider.py`](context_provider.py): Active window title inspection and cursor-highlighted monitor screenshot capture.
* [`recorder.py`](recorder.py): 44.1 kHz 16-bit mono WAV microphone recorder.

## License

MIT
