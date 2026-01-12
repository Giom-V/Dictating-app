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
        if mode == "thinking":
            return self._process_thinking_mode(audio_path, image_path, window_title)

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

    def _process_thinking_mode(self, audio_path: str, image_path: str, window_title: str) -> str:
        """Executes the two-step thinking process: Analysis -> Drafting."""
        print("\n=== [THINKING MODE STARTED] ===")
        
        # --- STEP 1: ANALYSIS ---
        print(">> STEP 1: ANALYZING CONTEXT & INTENT...")
        
        analysis_system_instruction = (
            "Tu es un expert en analyse de contexte et communication. "
            "Ta mission est d'analyser la situation (écran, audio) pour préparer la réponse parfaite."
            "\nNAVIGATEUR :"
            "1. **Analyse Visuelle** : Regarde sous le curseur rouge. Quelle est l'app ? Quel est le ton ?"
            "2. **Analyse Audio** : Que veut l'utilisateur ?"
            "3. **Stratégie** : Détermine la langue, le ton (Pro/Perso), et les points clés."
            "\nSORTIE ATTENDUE :"
            "Produis une analyse concise résumant : Contexte, Langue à utiliser, Ton visé, et Contenu à générer."
            "NE GÉNÈRE PAS LE TEXTE FINAL MAINTENANT."
        )
        
        contents_step1 = []
        prompt_text_1 = "Instructions: Analyse tout (Audio + Image) et donne-moi le plan de rédaction."
        
        if window_title:
            prompt_text_1 += f"\nContexte Fenêtre: '{window_title}'."
        
        contents_step1.append(prompt_text_1)
        
        # Helper to load files safely
        img_part = None
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    img_part = types.Part.from_bytes(data=f.read(), mime_type="image/png")
                    contents_step1.append(img_part)
            except Exception as e:
                print(f"[WARN] Failed to load image: {e}")

        if audio_path and os.path.exists(audio_path):
            try:
                with open(audio_path, "rb") as f:
                    audio_part = types.Part.from_bytes(data=f.read(), mime_type="audio/wav")
                    contents_step1.append(audio_part)
            except Exception as e:
                 print(f"[WARN] Failed to load audio: {e}")

        try:
            response_1 = self.client.models.generate_content(
                model=self.model_name,
                contents=contents_step1,
                config=types.GenerateContentConfig(
                    system_instruction=analysis_system_instruction,
                    temperature=0.7
                )
            )
            analysis_result = response_1.text.strip() if response_1.text else ""
            print(f"[STEP 1 ANALYSIS]:\n{analysis_result}\n")
        except Exception as e:
            print(f"[ERROR] Step 1 failed: {e}")
            return ""

        # --- STEP 2: DRAFTING ---
        print(">> STEP 2: GENERATING FINAL TEXT...")
        
        drafting_system_instruction = (
            "Tu es un rédacteur expert. "
            "En te basant sur l'ANALYSE fournie et le contexte visuel, rédige le texte final."
            "\nRÈGLES :"
            "1. Respecte scrupuleusement le ton et la langue identifiés."
            "2. Intègre-toi parfaitement au texte existant (sous le curseur)."
            "3. SORTIE : UNIQUEMENT le texte à écrire. Pas de guillemets, pas de commentaires."
        )
        
        contents_step2 = []
        prompt_text_2 = f"Voici l'ANALYSE de la situation :\n{analysis_result}\n\nInstructions: Rédige maintenant le texte final."
        
        contents_step2.append(prompt_text_2)
        # We include the image again for visual context/grounding in the drafting phase if available
        if img_part: 
            contents_step2.append(img_part)
        
        try:
            response_2 = self.client.models.generate_content(
                model=self.model_name,
                contents=contents_step2,
                config=types.GenerateContentConfig(
                    system_instruction=drafting_system_instruction,
                    temperature=0.7
                )
            )
            final_text = response_2.text.strip() if response_2.text else ""
            print(f"[STEP 2 OUTPUT]:\n{final_text}\n")
            print("=== [THINKING MODE COMPLETE] ===")
            return final_text
            
        except Exception as e:
            print(f"[ERROR] Step 2 failed: {e}")
            return ""
