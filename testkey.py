import os
from pathlib import Path
from dotenv import load_dotenv, dotenv_values

dotenv_path = Path(r"C:\StravaSecurity\main.env")

print("Fichier existe ?", dotenv_path.exists())

config = dotenv_values(str(dotenv_path))
print("Contenu dotenv_values :", config)

loaded = load_dotenv(dotenv_path)
print("dotenv chargé :", loaded)

def mask_secret(val):
    if val is None:
        return None
    s = str(val)
    if len(s) <= 8:
        return s[0] + "*" * (len(s) - 1)
    return s[:4] + "*" * (len(s) - 8) + s[-4:]

print("OPENAI_API_KEY =", mask_secret(os.getenv("OPENAI_API_KEY")))
print("GOOGLE_SERVICE_ACCOUNT_FILE =", mask_secret(os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")))