import os
import re
import openai
from getpass import getpass

# IMPORTANT: Ne jamais stocker la clé API en dur dans le fichier.
# Assure-toi d'exporter OPENAI_API_KEY dans ton environnement :
# export OPENAI_API_KEY="sk-..."

# Récupère la clé depuis la variable d'environnement, sinon demande-la en entrée sécurisée
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    openai.api_key = getpass("Entrez votre OpenAI API key (ne sera pas affichée) : ").strip()

# Dossier du projet Flask
PROJECT_PATH = "/opt/app/Track2Train-staging"

# Extensions à prendre en compte
INCLUDE_EXT = [".py", ".html", ".css", ".js"]

def load_project(path):
    project_files = {}
    for root, dirs, files in os.walk(path):
        for file in files:
            if any(file.endswith(ext) for ext in INCLUDE_EXT):
                full_path = os.path.join(root, file)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        rel_path = os.path.relpath(full_path, PROJECT_PATH)
                        project_files[rel_path] = f.read()
                except Exception:
                    # Ignore files qui poseraient problème à la lecture
                    continue
    return project_files

# Charger projet
project_files = load_project(PROJECT_PATH)

# Instruction utilisateur (entrée)
print("Écris l'instruction pour GPT (ex: 'optimise le projet Flask', ou 'corrige HTML/CSS').")
instruction = input(">> ").strip()

# Construire le prompt : on force le format de sortie demandé au modèle
full_prompt = "Voici le projet Flask complet :\n\n"
for filename, content in project_files.items():
    full_prompt += f"--- {filename} ---\n{content}\n\n"

full_prompt += f"Instruction : {instruction}\n\n"
full_prompt += (
    "IMPORTANT : Retourne uniquement le contenu des fichiers modifiés. "
    "Pour chaque fichier modifié, fournis exactement le bloc suivant sans rien d'autre :\n\n"
    "--- path/to/file.ext ---\n"
    "<contenu du fichier>\n\n"
    "Ne fournis aucune explication, aucun diff, aucune numérotation de lignes, "
    "et aucun texte en dehors des blocs de fichiers au format ci-dessus. "
    "Si aucun fichier n'est modifié, réponds par une chaîne vide.\n"
)

# Appel API GPT
response = openai.ChatCompletion.create(
    model="gpt-5-mini",
    messages=[
        {"role": "system", "content": "Tu es un assistant expert en code Python/Flask/HTML/CSS/JS."},
        {"role": "user", "content": full_prompt}
    ],
    temperature=0,
    max_tokens=16000
)

modified_text = response['choices'][0]['message']['content'].strip()

# Afficher uniquement le contenu modifié (tel que demandé).
# Conformément à l'instruction, on imprime directement la réponse du modèle (qui doit être au format attendu).
# Si tu veux ensuite appliquer automatiquement les changements sur le disque, adapte ce script pour parser
# les blocs et écrire les fichiers — ici on se contente de retourner STRICTEMENT le texte modifié.
print(modified_text)