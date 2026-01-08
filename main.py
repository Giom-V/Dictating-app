import keyboard
import time
import os
import pyperclip
from dotenv import load_dotenv
from recorder import AudioRecorder
from llm_client import GeminiClient

from context_provider import ContextProvider

load_dotenv()

HOTKEY = os.getenv("HOTKEY", "F8")

def main():
    print(f"Initialisation de l'assistant...")
    print(f"Raccourci configuré : {HOTKEY}")
    print("Assurez-vous d'avoir rempli votre clé GEMINI_API_KEY dans le fichier .env")
    
    try:
        client = GeminiClient()
        recorder = AudioRecorder()
        context_provider = ContextProvider()
    except Exception as e:
        print(f"Erreur au démarrage : {e}")
        return

    print("Prêt ! Maintenez la touche pour parler.")

    while True:
        try:
            # Attendre l'appui sur la touche
            keyboard.wait(HOTKEY)
            print(f"\n[EVENT] Touche {HOTKEY} pressée. Enregistrement en cours...")
            
            # Démarrer l'enregistrement (priorité absolue pour ne rien rater)
            recorder.start()
            
            # Capturer le contexte immédiatement après
            print("[INFO] Capture du contexte...")
            start_time = time.time()
            window_title = context_provider.get_active_window_title()
            image_path = context_provider.capture_screen_with_cursor()
            print(f"[INFO] Contexte capturé en {time.time() - start_time:.2f}s")
            
            # Attendre le relâchement de la touche
            while keyboard.is_pressed(HOTKEY):
                time.sleep(0.05)
            
            print(f"[EVENT] Touche {HOTKEY} relâchée. Traitement...")

            # Arrêter l'enregistrement
            audio_path = recorder.stop()
            
            if not audio_path:
                print("Aucun audio enregistré.")
                # Nettoyage image si existe
                if image_path and os.path.exists(image_path):
                    os.remove(image_path)
                continue

            # Traitement
            try:
                text = client.process_audio(audio_path, image_path=image_path, window_title=window_title)
                print(f"Réponse Gemini : {text}")
                
                if text:
                    # Copier dans le presse-papier et coller
                    pyperclip.copy(text)
                    time.sleep(0.1) 
                    keyboard.send('ctrl+v')
            except Exception as e:
                print(f"Erreur lors du traitement Gemini : {e}")
            
            # Nettoyage des fichiers temporaires
            try:
                os.remove(audio_path)
                if image_path and os.path.exists(image_path):
                    os.remove(image_path)
            except:
                pass
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Erreur inattendue : {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
