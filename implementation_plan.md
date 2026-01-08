# Plan d'implémentation : Assistant Vocal Windows avec Gemini

Ce projet vise à créer un assistant Windows invisible qui écoute une commande vocale via un raccourci clavier ("Push-to-Talk"), traite l'audio avec Gemini, et tape le résultat directement dans l'application active.

## Architecture

1.  **Entrée Audio (Recorder)** :
    *   Utilise `sounddevice` pour capturer le microphone.
    *   Enregistre tant que le raccourci est maintenu.
    *   Sauvegarde temporaire en fichier `.wav` (requis pour l'API Gemini).

2.  **Traitement IA (Gemini Client)** :
    *   Envoie le fichier audio à l'API Gemini (Flash ou Pro).
    *   **System Instruction (SI)** : "Tu es un assistant de rédaction. L'utilisateur va te dicter une commande ou un texte. Exécute la demande et retourne *uniquement* le texte résultat prêt à être envoyé. Pas de blabla, pas de guillemets, pas de préambule."

3.  **Interaction Système (Controller)** :
    *   Utilise la librairie `keyboard` pour détecter l'appui long sur le raccourci (ex: `F8` ou `Ctrl+Space`).
    *   Utilise `keyboard.write()` ou `pyperclip` + `Ctrl+V` pour insérer le texte généré.

4.  **Contexte Visuel (Context Provider)** :
    *   **Capture d'écran** : Utilise `Pillow` / `pyautogui` pour capturer l'écran au moment de l'activation.
    *   **Mise en évidence** : Dessine un cercle ou un indicateur autour de la position de la souris sur l'image.
    *   **Métadonnées** : Récupère le titre de la fenêtre active via `pygetwindow` pour donner du contexte à Gemini (ex: "Je suis dans VS Code").

## Étapes de développement

1.  **Configuration de l'environnement** : Création du `requirements.txt`.
2.  **Module d'enregistrement** : Script pour capturer l'audio vers un fichier WAV.
3.  **Module Gemini** : Script pour envoyer l'audio et récupérer le texte.
4.  **Main Application** : Boucle principale écoutant le clavier et orchestrant les appels.
