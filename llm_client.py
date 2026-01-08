from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv(override=True)

class GeminiClient:
    def __init__(self):
        # Try to get from env, else fallback (dev mode)
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        
        # Fallback if empty
        if not api_key:
            raise ValueError("GEMINI_API_KEY introuvable dans lenv")
        
        print(f"[DEBUG] Using Key: {api_key[:5]}...{api_key[-4:]} (Length: {len(api_key)})")

        self.client = genai.Client(api_key=api_key)
        
        # System Instruction
        try:
            with open("system_instruction.txt", "r", encoding="utf-8") as f:
                self.system_instruction = f.read().strip()
        except FileNotFoundError:
            print("[WARN] Fichier system_instruction.txt introuvable. Utilisation des instructions par défaut.")
            self.system_instruction = (
                "Tu es un assistant vocal invisible pour Windows. "
                "Ta tâche est de produire EXACTEMENT le texte que l'utilisateur veut écrire. "
                "N'ajoute jamais de guillemets ou de blabla."
            )
        self.model_name = "gemini-2.5-flash-lite" # Optimized for low latency

    def process_audio(self, audio_path: str, image_path: str = None, window_title: str = None) -> str:
        """Uploads audio/image bytes and gets the response text."""
        print(f"Envoi des données à Gemini... (Audio: {audio_path}, Image: {image_path})")
        
        contents = []

        # 1. Add System Instruction / Context as Text
        prompt_text = "Instructions: Écoute l'audio et tape exactement le texte dicté. "
        if window_title:
            prompt_text += f"\nContexte Fenêtre: '{window_title}'."
        if image_path:
            prompt_text += "\nContexte Visuel: Une capture d'écran est fournie (curseur entouré en rouge)."
            
        contents.append(prompt_text)

        # 2. Add Image Bytes
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
                contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))
            except Exception as e:
                print(f"[WARN] Impossible de lire l'image: {e}")

        # 3. Add Audio Bytes
        if audio_path and os.path.exists(audio_path):
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            contents.append(types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"))

        # Logging
        print("\n--- [REQUEST SENT TO MODEL] ---")
        print(f"Model: {self.model_name}")
        for item in contents:
            if isinstance(item, str):
                print(f"Text: {item}")
            elif hasattr(item, 'mime_type'):
                print(f"Data Part: {item.mime_type} ({len(item.data)} bytes)")
        print("-------------------------------\n")
        
        # Generate
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.0
                )
            )
            
            text_response = response.text.strip() if response.text else ""
            print("\n--- [RESPONSE RECEIVED] ---")
            print(text_response)
            print("---------------------------\n")
            return text_response
            
        except Exception as e:
            # Better error logging
            print(f"\n[ERROR GEMINI]: {e}")
            if "API key expired" in str(e):
                 print("!!! VOTRE CLÉ API EST EXPIRÉE OU INVALIDE. VEUILLEZ VÉRIFIER LE FICHIER .ENV !!!")
            raise e
