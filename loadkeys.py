import os
import platform
from pathlib import Path
from dotenv import load_dotenv

# ----------------------------
# Configuration universelle
# ----------------------------

# Choix du dossier de sécurité par défaut selon la plateforme
_default_sec_dir = r"C:\StravaSecurity" if platform.system() == "Windows" else "/opt/app/StravaSecurity"
SEC_DIR = Path(os.getenv("STRAVA_SECURITY_DIR") or _default_sec_dir)
SEC_DIR = Path(os.path.expanduser(os.path.expandvars(str(SEC_DIR))))

# Chemin vers le main.env (peut être surchargé par STRAVA_SECURITY_PATH)
env_path_env = os.getenv("STRAVA_SECURITY_PATH")
ENV_FILE = Path(os.path.expanduser(os.path.expandvars(env_path_env))) if env_path_env else (SEC_DIR / "main.env")

# 1) Charge le .env du projet (si présent) — laisse les variables d'environnement existantes si non précisées
load_dotenv()

# 2) Charge le main.env du dossier sécurité (si présent) et écrase les variables existantes
if ENV_FILE.exists():
    load_dotenv(dotenv_path=str(ENV_FILE), override=True)
    print(f"✅ main.env chargé depuis {ENV_FILE}")
else:
    print(f"⚠️ main.env introuvable : {ENV_FILE}")

# 3) Définit le chemin vers le fichier de credentials Google s’il n’est pas déjà dans l’environnement
gac = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if not gac:
    cred_path = SEC_DIR / "services.json"
    if cred_path.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(cred_path)
        print(f"✅ services.json détecté et configuré : {cred_path}")
    else:
        print(f"⚠️ services.json manquant : {cred_path}")
else:
    # si la variable est définie, vérifie l'existence du fichier (si c'est un chemin)
    try:
        gac_path = Path(os.path.expanduser(os.path.expandvars(gac)))
        if gac_path.exists():
            print(f"✅ GOOGLE_APPLICATION_CREDENTIALS défini : {gac} (fichier trouvé)")
        else:
            print(f"⚠️ GOOGLE_APPLICATION_CREDENTIALS défini mais fichier introuvable : {gac}")
    except Exception:
        print(f"ℹ️ GOOGLE_APPLICATION_CREDENTIALS défini : {gac}")

# 4) Vérifie les variables essentielles (masque la clé OpenAI pour la sécurité)
def _mask_key(k):
    if not k:
        return "❌ non défini"
    s = str(k)
    if len(s) <= 8:
        return "****"
    return f"{s[:4]}...{s[-4:]}"

openai_key = os.getenv("OPENAI_API_KEY")
folder_id = os.getenv("FOLDER_ID")
gac_final = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

print("OPENAI_API_KEY =", _mask_key(openai_key))
print("FOLDER_ID =", folder_id if folder_id else "❌ non défini")
if gac_final:
    gac_p = Path(os.path.expanduser(os.path.expandvars(gac_final)))
    exists_msg = "fichier trouvé" if gac_p.exists() else "fichier introuvable"
    print(f"GOOGLE_APPLICATION_CREDENTIALS = {gac_final} ({exists_msg})")
else:
    print("GOOGLE_APPLICATION_CREDENTIALS = ❌ non défini")

# Ce module ne lance plus rien, il se contente de préparer les variables.