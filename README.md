# Gemini Dictating Agent (Windows)

A powerful, invisible AI assistant for Windows that allows you to dictate text and commands directly into any application. It captures your voice AND your screen context (window title + screenshot) to provide intelligent, context-aware responses using Google's **Gemini 2.5 Flash Lite** model.

## Features

*   🎤 **Push-to-Talk**: Hold a hotkey (default `F8`) to record commands or dictation.
*   👀 **Visual Context**: Automatically captures a screenshot and highlights your mouse cursor position to understand what you are referring to.
*   🧠 **Smart AI**: Uses `gemini-2.5-flash-lite` for ultra-low latency and high intelligence.
*   ⚡ **Direct Injection**: The generated text is automatically typed/pasted into your active application.
*   🌍 **Multilingual**: Dictate in any language, or ask for translations on the fly.
*   🖥️ **System Tray Integration**: Runs quietly in the background with a handy system tray icon.
*   🚀 **Auto-Start**: Right-click the icon to enable "Start with Windows" so it's always ready.

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
4.  **System Instructions**: You can modify the bot's behavior by editing the `system_instruction.txt` file.

## Usage

1.  Run the application:
    ```bash
    python main.py
    ```
    *The application will start in the background. Look for the blue microphone icon in your system tray (bottom right).*

2.  **Right-click** the tray icon to:
    *   Enable **"Start with Windows"**.
    *   **Quit** the application.

3.  **Microphone Selection** 🎙️:
    *   **Right-click** the tray icon.
    *   Navigate to the **"Microphone"** submenu.
    *   Select your preferred input device from the list.
    *   *Usage Tip: If your webcam light turns on when using F8, try selecting a different microphone (like your headset) to avoid triggering the webcam's hardware activity LED.*

4.  **Using the Agent (3 Modes)**:

    *   🎤 **Dictation Mode** (`F8`):
        *   **Action**: Hold `F8` and speak.
        *   **Goal**: Pure transcription.
        *   **Behavior**: Types exactly what you say. Follows formatting instructions immediately (e.g., "Write in English" -> Writes inside the document in English).

    *   🧠 **Thinking Mode** (`F9`):
        *   **Action**: Hold `F9`, point your cursor at something, and ask.
        *   **Goal**: Smart Assistant (Code generation, Email replies, complex analysis).
        *   **Behavior (2-Step Process)**:
            1.  **Analysis**: Scans screen/audio, determines language/context, and **routes** the request.
            2.  **Drafting**: Generates the final text.
                *   *Simple Task* -> Uses **Flash Lite** (Fast).
                *   *Complex Task* (Code/Pro) -> Uses **Gemini Pro** (Powerful).
        *   *Example*: Point at code -> "Optimise ça en Python" (Uses Pro).
        *   *Example*: Point at email -> "Réponds gentiment" (Uses Lite).

    *   🐞 **Debug Mode** (`Ctrl` + `F9`):
        *   **Action**: Press `Ctrl+F9` (No need to hold/speak).
        *   **Goal**: Diagnostic.
        *   **Behavior**: Takes a screenshot and prints a detailed report in the **terminal** describing exactly what the agent sees under the red cursor. Use this if you feel the context is wrong.

## Troubleshooting

*   **API Key Error**: Ensure your `.env` file is correct and the key is valid.
*   **Audio Issues**: Check your default Windows recording device.
*   **Permissions**: The app needs permission to record screen and audio. ensuring your terminal has necessary rights.

## License

MIT
