# Gemini Dictating Agent (Windows)

A powerful, invisible AI assistant for Windows that allows you to dictate text and commands directly into any application. It captures your voice AND your screen context (window title + screenshot) to provide intelligent, context-aware responses using Google's **Gemini 2.5 Flash Lite** model.

## Features

*   🎤 **Push-to-Talk**: Hold a hotkey (default `F8`) to record commands or dictation.
*   👀 **Visual Context**: Automatically captures a screenshot and highlights your mouse cursor position to understand what you are referring to.
*   🧠 **Smart AI**: Uses `gemini-2.5-flash-lite` for ultra-low latency and high intelligence.
*   ⚡ **Direct Injection**: The generated text is automatically typed/pasted into your active application.
*   🌍 **Multilingual**: Dictate in any language, or ask for translations on the fly.

## Prerequisites

*   Windows 10/11
*   Python 3.10+
*   A microphone
*   A Google Gemini API Key (Get one [here](https://aistudio.google.com/app/apikey))

## Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/dictating-agent.git
    cd dictating-agent
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  Create a `.env` file in the root directory (based on the example below):
    ```env
    GEMINI_API_KEY=your_api_key_here
    HOTKEY=F8
    ```
2.  **GEMINI_API_KEY**: Paste your API key from Google AI Studio.
3.  **HOTKEY**: Choose your push-to-talk key (e.g., `F8`, `ctrl+space`, `alt+k`).

## Usage

1.  Run the application:
    ```bash
    python main.py
    ```
2.  Go to any application (Notepad, VS Code, Slack, Browser...).
3.  **Hold down** the configured hotkey (e.g., `F8`).
4.  **Speak** your command or text while holding the key.
    *   *Example:* "Explain this function" (while pointing at code).
    *   *Example:* "Write a reply saying I'm interested" (while looking at an email).
5.  **Release** the key.
6.  Watch the magic happen! 🪄

## Troubleshooting

*   **API Key Error**: Ensure your `.env` file is correct and the key is valid.
*   **Audio Issues**: Check your default Windows recording device.
*   **Permissions**: The app needs permission to record screen and audio. ensuring your terminal has necessary rights.

## License

MIT
