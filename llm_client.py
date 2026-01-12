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

    def process_audio(self, audio_path: str, image_path: str = None, window_title: str = None, mode: str = "dictation") -> str:
        """Uploads audio/image bytes and gets the response text."""
        print(f"Envoi des données à Gemini... (Mode: {mode}, Audio: {audio_path}, Image: {image_path})")
        
        contents = []
        
        # 0. Define Prompts based on mode
        if mode == "thinking":
            # Reflection/Contextual mode
            system_instruction = (
                "Tu es un expert en communication contextuelle et un développeur senior. "
                "Ta mission est de générer du contenu qui s'intègre PARFAITEMENT dans l'application ouverte devant l'utilisateur. "
                "\n\n"
                "RÈGLES D'ANALYSE VISUELLE CRITIQUES :"
                "1. **FOCUS VISUEL (RÈGLE SUPRÊME)** :"
                "   - Regarde OÙ est le curseur (cercle ROUGE semi-transparent)."
                "   - L'application active est CELLE SOUS LE CURSEUR. Ignore les autres fenêtres en arrière-plan."
                "   - Le texte pertinent est celui à proximité immédiate du curseur."
                "\n"
                "2. **Détecte la Langue du Contexte (PRIORITÉ ABSOLUE)** :"
                "   - Regarde le texte DÉJÀ PRÉSENT sous le curseur."
                "   - Si le contexte est en ANGLAIS -> TU DOIS RÉPONDRE EN ANGLAIS."
                "\n"
                "3. **Identifie la Structure** :"
                "   - Chat vs Email vs Code : Déduit-le de la zone pointée par le curseur."
                "\n"
                "4. **Identifie l'Application** :"
                "   - **IDE** : Si le curseur est dans le code -> Code pur. Si dans le chat -> Conversation."
                "   - **Email/Messagerie** : Adapte le ton."
                "\n"
                "5. **Pas de Bavardage** : Envoie UNIQUEMENT le texte final à taper."
            )
            prompt_text = "Instructions: Regarde SOUS le curseur rouge, analyse le contexte (app, langue) et exécute ma demande."
        elif mode == "debug":
            # Debug/Analysis mode
            system_instruction = (
                "Tu es un diagnostiqueur visuel. "
                "Ta tâche est de DÉCRIRE ce qui se passe SOUS LE CURSEUR ROUGE. "
                "1. Quelle application est directement sous le curseur ? "
                "2. Quel texte lis-tu PROCHE du curseur ? "
                "3. Le curseur pointe-t-il sur du code, un champ texte, ou un bouton ?"
                "4. Ignore les fenêtres en arrière-plan."
            )
            prompt_text = "Instructions: Focus sur le cercle rouge. Décris le contexte immédiat."
        else:
            # Dictation mode (Default)
            # We strictly reinforce the "Don't chat" rule here
            system_instruction = (
                "Tu es un moteur de dictée pur. "
                "TA SEULE ET UNIQUE TÂCHE est de transcrire ce que dit l'utilisateur pour qu'il puisse l'insérer dans un document. "
                "RÈGLES CRITIQUES :\n"
                "1. Si l'utilisateur donne une instruction de formatage ou de langue (ex: 'écris en anglais', 'traduis ça'), NE L'ÉCRIS PAS. APPLIQUE-LA.\n"
                "2. Ne dis JAMAIS 'Voici le texte', 'D'accord', ou 'Bien sûr'.\n"
                "3. N'ajoute pas de guillemets au début ou à la fin.\n"
                "4. Si l'utilisateur hésite (euh...), ignore les hésitations.\n"
                "5. Le texte final doit être prêt à être collé."
            )
            prompt_text = "Instructions: Écoute l'audio et tape exactement le texte, en appliquant les transformations demandées (traduction, style) sans bavardage. "

        # 1. Add Text Context
        if window_title:
            prompt_text += f"\nContexte Fenêtre: '{window_title}'."
        if image_path:
            prompt_text += "\nContexte Visuel: Une capture d'écran est fournie."
            
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
        print(f"Model: {self.model_name} | Mode: {mode}")
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
                    system_instruction=system_instruction,
                    temperature=0.0 if mode == "dictation" else 0.7, # Creative for thinking/debug, strict for dictation
                    media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH
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
