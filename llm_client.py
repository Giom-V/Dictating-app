from google import genai
from google.genai import types
import os
import json
import subprocess
import tempfile
import ctypes
import time
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

load_dotenv(override=True)

class GeminiClient:
    def __init__(self):
        # Try to get from env, else fallback (dev mode)
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        
        # Fallback if empty
        if not api_key:
            raise ValueError("GEMINI_API_KEY introuvable dans l'env")
        
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
                "Ta tâche est de produire EXACTEMENT le texte que l'utilisateur veut écrire. Il est très important de bien écouter l'utilisateur, les captures d'écran n'étant là que pour le contexte."
                "N'ajoute jamais de guillemets ou de blabla. Fais bien attention à la ponctuation par contre."
            )
        self.model_name = "gemini-2.5-flash-lite" # Optimized for low latency

    def _generate_with_retry(self, model_name, contents, config):
        """
        Wraps generate_content with retry logic (backoff 1s, 2s, 5s) 
        and model fallback on 503 errors.
        """
        delays = [1, 2, 5]
        
        # Fallback map
        fallback_models = {
            "gemini-2.5-flash-lite": "gemini-3-flash-preview",
            "gemini-3-pro-preview": "gemini-2.5-pro",
        }

        current_model = model_name
        
        for attempt, delay in enumerate(delays + [None]): # None means last attempt or fallback
            try:
                print(f"[DEBUG] Generating with {current_model} (Attempt {attempt + 1})")
                response = self.client.models.generate_content(
                    model=current_model,
                    contents=contents,
                    config=config
                )
                return response
            
            except Exception as e:
                error_str = str(e)
                # Check for 503 or Overloaded
                if "503" in error_str or "overloaded" in error_str.lower():
                    print(f"[WARN] Gemini 503/Overloaded: {e}")
                    
                    if delay is not None:
                        # Backoff
                        print(f"[RETRY] Waiting {delay}s before retry...")
                        time.sleep(delay)
                        continue
                    else:
                        # Retries exhausted, try fallback if available
                        if current_model in fallback_models:
                            new_model = fallback_models[current_model]
                            print(f"[FALLBACK] Retries failed. Switching model: {current_model} -> {new_model}")
                            current_model = new_model
                            # Try ONE more time with new model (or could loop again, but let's do one try)
                            try:
                                print(f"[DEBUG] Generating with fallback {current_model}")
                                response = self.client.models.generate_content(
                                    model=current_model,
                                    contents=contents,
                                    config=config
                                )
                                return response
                            except Exception as e2:
                                print(f"[ERROR] Fallback failed: {e2}")
                                raise e2
                        else:
                            # No fallback available
                            print(f"[ERROR] Retries exhausted, no fallback for {current_model}.")
                            raise e
                else:
                    # Non-retriable error (e.g. 400, 403)
                    raise e

    def _copy_image_to_clipboard_native(self, image_path: str):
        """Copies an image at the given path to the Windows clipboard using ctypes."""
        try:
            image = Image.open(image_path)
            output = BytesIO()
            # Convert to RGB to ensure compatibility
            image.convert("RGB").save(output, "BMP")
            data = output.getvalue()[14:]  # Remove the 14-byte BMP header to get DIB
            output.close()

            # Define clipboard constants
            CF_DIB = 8
            GMEM_MOVEABLE = 0x0002
            
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            
            # Open Clipboard
            if not user32.OpenClipboard(0):
               raise Exception("Could not open clipboard")
               
            try:
                user32.EmptyClipboard()
                
                # Allocate global memory
                h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                if not h_global:
                    raise Exception("GlobalAlloc failed")
                
                # Lock memory and copy data
                ptr = kernel32.GlobalLock(h_global)
                if not ptr:
                     kernel32.GlobalFree(h_global)
                     raise Exception("GlobalLock failed")
                     
                ctypes.memmove(ptr, data, len(data))
                kernel32.GlobalUnlock(h_global)
                
                # Set clipboard data
                if not user32.SetClipboardData(CF_DIB, h_global):
                     kernel32.GlobalFree(h_global) # Free if set failed? Actually system owns it if Set succeeds
                     raise Exception("SetClipboardData failed")
                     
            finally:
                user32.CloseClipboard()
                
            print("[INFO] Native Copy to Clipboard success.")
            
        except Exception as e:
            print(f"[ERROR] Native Clipboard Copy failed: {e}")
            raise e

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
                "6. Je vais te fournir des captures d'écran pour t'aider à comprendre le contexte (quelle app est utilisée, dans quelle langue est la discussion actuelle, etc). C'est juste du contexte.\n"
                "7. Ne recopie pas ce qui est dans la capture d'écran, c'est ce qui est dit à l'oral qui est important."
            )
            prompt_text = (
                "Instructions: Écoute l'audio et tape exactement le texte."
#                "\nIMPORTANT: Priorise l'audio sur le texte visible à l'écran. N'utilise le contexte visuel que pour les noms propres ou références ambigües."
            )

        # 1. Add Text Context
        if window_title:
            prompt_text += f"\nContexte Fenêtre: '{window_title}'."
        if image_path:
            prompt_text += "\nContexte Visuel: Une capture d'écran est fournie pour le contexte."
            
        # 0. Construct List - ORDER MATTERS for Gemini Focus
        # We put Audio FIRST to prioritize listening in Dictation Mode
        if audio_path and os.path.exists(audio_path):
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            contents.append(types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"))
            print("[INFO] Audio file added to contents.")

        # Then Text Prompt
        contents.append(prompt_text)

        # Finally Image (so text doesn't get buried)
        # RESTORING IMAGE with logic constraints:
        # We lowered resolution to 'LOW' in config to discourage OCR heavy lifting vs Audio
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
                contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))
            except Exception as e:
                print(f"[WARN] Impossible de lire l'image: {e}")

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
            response = self._generate_with_retry(
                model_name=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0 if mode == "dictation" else 0.7, # Creative for thinking/debug, strict for dictation
                    # Lower resolution for dictation to rely less on OCR details
                    media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW if mode == "dictation" else types.MediaResolution.MEDIA_RESOLUTION_HIGH
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
            "\n4. **ROUTING (CRITIQUE)** : Evalue la complexité."
            "   - 'COMPLEX' : Code, Raisonnement logique complexe, Créativité longue, ou demande explicite de 'Pro'."
            "   - 'SIMPLE' : Email rapide, chat, correction, courte phrase."
            "   - 'IMAGE_GENERATION' : L'utilisateur demande explicitement de générer ou dessiner une image/graphique."
            "\nSORTIE ATTENDUE :"
            "Tu dois répondre UNIQUEMENT en JSON avec la structure suivante :"
            "{"
            "  \"context_analysis\": \"Analyse visuelle et contextuelle\","
            "  \"intent\": \"Ce que veut l'utilisateur (Pour IMAGE_GENERATION: le prompt de l'image)\","
            "  \"language\": \"Langue détectée (ex: 'fr', 'en')\","
            "  \"tone\": \"Ton suggéré\","
            "  \"complexity\": \"SIMPLE\" OU \"COMPLEX\" OU \"IMAGE_GENERATION\","
            "  \"model_reasoning\": \"Pourquoi c'est simple, complexe ou une image\","
            "  \"step_by_step_plan\": \"Plan de rédaction\""
            "}"
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
            response_1 = self._generate_with_retry(
                model_name=self.model_name,
                contents=contents_step1,
                config=types.GenerateContentConfig(
                    system_instruction=analysis_system_instruction,
                    temperature=0.7,
                    response_mime_type="application/json"
                )
            )
            analysis_text = response_1.text.strip() if response_1.text else "{}"
            print(f"[STEP 1 RAW JSON]:\n{analysis_text}\n")
            
            # Parse JSON
            try:
                analysis_json = json.loads(analysis_text)
            except json.JSONDecodeError:
                print("[WARN] JSON Parsing failed, falling back to simple text analysis.")
                analysis_json = {"complexity": "SIMPLE", "context_analysis": analysis_text}

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
        # Create a nice summary for the drafter
        prompt_text_2 = (
            f"CONTEXTE ANALYSÉ :\n{json.dumps(analysis_json, indent=2, ensure_ascii=False)}\n\n"
            "Instructions: Rédige maintenant le texte final en suivant STRICTEMENT ce plan."
        )
        
        contents_step2.append(prompt_text_2)
        # We include the image again for visual context/grounding in the drafting phase if available
        if img_part: 
            contents_step2.append(img_part)
        
        # Determine Model for Step 2
        step2_model = self.model_name # Default to Lite
        try:
            complexity = analysis_json.get("complexity", "SIMPLE").upper()
        except:
            complexity = "SIMPLE"
        
        if complexity == "COMPLEX":
            step2_model = "gemini-3-pro-preview"
            print(f"[ROUTING] Task judged COMPLEX ({analysis_json.get('model_reasoning')}). Switching to {step2_model}.")
        elif complexity == "IMAGE_GENERATION":
             # New Image Mode
             print(f"[ROUTING] Task judged IMAGE_GENERATION. Switching to Image Generation Flow.")
             return self._generate_and_copy_image(analysis_json.get("intent")) # Use intent as prompt
        else:
            print(f"[ROUTING] Task judged SIMPLE. Staying on {step2_model}.")

        try:
            response_2 = self._generate_with_retry(
                model_name=step2_model,
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

    def _generate_and_copy_image(self, prompt: str) -> str:
        """Generates an image using Gemini and copies it to the clipboard using native ctypes."""
        print(f"\n>> GENERATING IMAGE for prompt: '{prompt}'...")
        
        try:
            # 1. Generate Image
            response = self._generate_with_retry(
                model_name="gemini-3-pro-image-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=['Image'],
                    tools=[{"google_search": {}}] # Enable search for grounding (weather, etc)
                )
            )
            
            # 2. Extract and Save Image
            image_saved = False
            temp_path = None
            
            for part in response.parts:
                if image := part.as_image():
                     # Create temp file
                     fd, temp_path = tempfile.mkstemp(suffix=".png")
                     os.close(fd)
                     image.save(temp_path)
                     print(f"[INFO] Image saved to {temp_path}")
                     image_saved = True
                     break
            
            if not image_saved:
                print("[ERROR] No image returned by Gemini.")
                return ""

            # 3. Copy to Clipboard (Native Code)
            print("[INFO] Copying to clipboard (Native)...")
            self._copy_image_to_clipboard_native(temp_path)
            
            return "___IMAGE_GENERATED___"

        except Exception as e:
            print(f"[ERROR] Image Generation failed: {e}")
            return ""
