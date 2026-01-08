# Implementation Plan: Gemini Windows Voice Assistant

This project aims to create an invisible Windows assistant that listens for voice commands via a keyboard shortcut ("Push-to-Talk"), processes the audio with Gemini, and types the result directly into the active application.

## Architecture

1.  **Audio Input (Recorder)**:
    *   Uses `sounddevice` to capture microphone input.
    *   Records as long as the shortcut is held down.
    *   Temporarily saves as a `.wav` file (required for the Gemini API).

2.  **AI Processing (Gemini Client)**:
    *   Sends the audio file to the Gemini API (Flash-Lite).
    *   **System Instruction (SI)**: "You are an editorial assistant. The user will dictate a command or text. Execute the request and return *only* the resulting text ready to be sent. No filler, no quotes, no preamble."

3.  **System Interaction (Controller)**:
    *   Uses the `keyboard` library to detect long presses on the shortcut (e.g., `F8` or `Ctrl+Space`).
    *   Uses `keyboard.write()` or `pyperclip` + `Ctrl+V` to insert the generated text.

4.  **Visual Context (Context Provider)**:
    *   **Screenshot**: Uses `Pillow` / `pyautogui` to capture the screen at the moment of activation.
    *   **Highlighting**: Draws a circle or indicator around the mouse position on the image.
    *   **Metadata**: Retrieves the active window title via `pygetwindow` to provide context to Gemini (e.g., "I am in VS Code").

## Development Steps

1.  **Environment Setup**: Creation of `requirements.txt`.
2.  **Recording Module**: Script to capture audio to a WAV file.
3.  **Gemini Module**: Script to send audio and retrieve text.
4.  **Main Application**: Main loop listening to the keyboard and orchestrating calls, including System Tray integration.
