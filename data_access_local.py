# data_access_local.py — Version locale optimisée (backup Drive optionnel)
from __future__ import annotations
import json
import os
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime

# Import de l'ancien module Drive pour backup optionnel
try:
    from data_access import (
        save_activities_to_drive as _save_to_drive,
        load_activities_from_drive as _load_from_drive,
        DriveUnavailableError
    )
    DRIVE_AVAILABLE = True
except ImportError:
    DRIVE_AVAILABLE = False
    DriveUnavailableError = RuntimeError

# Chemins locaux
BASE_DIR = Path(__file__).parent
ACTIVITIES_FILE = BASE_DIR / "activities.json"
PROFILE_FILE = BASE_DIR / "profile.json"
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# Fichier de tracking du dernier backup Drive
LAST_BACKUP_FILE = BASE_DIR / ".last_drive_backup"

# Debug
DEBUG = os.getenv("SC_DEBUG") == "1"
def _dbg(msg: str) -> None:
    if DEBUG:
        print(f"[DA_LOCAL] {msg}")


# ========== ACTIVITIES ==========

def load_activities_local() -> List[Dict[str, Any]]:
    """Charge activities.json depuis le disque local."""
    if not ACTIVITIES_FILE.exists():
        _dbg(f"{ACTIVITIES_FILE} inexistant, retourne []")
        return []

    try:
        with open(ACTIVITIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f"{ACTIVITIES_FILE} n'est pas une liste JSON")
        _dbg(f"activities loaded from local: {len(data)}")
        return data
    except Exception as e:
        raise RuntimeError(f"Erreur lecture {ACTIVITIES_FILE}: {e}") from e


def save_activities_local(activities: List[Dict[str, Any]]) -> None:
    """Sauvegarde activities.json sur le disque local."""
    try:
        with open(ACTIVITIES_FILE, "w", encoding="utf-8") as f:
            json.dump(activities, f, ensure_ascii=False, indent=2)
        _dbg(f"activities saved to local: {len(activities)}")
    except Exception as e:
        raise RuntimeError(f"Erreur écriture {ACTIVITIES_FILE}: {e}") from e


def backup_activities_to_drive(activities: List[Dict[str, Any]], force: bool = False) -> bool:
    """
    Backup optionnel vers Drive (1x par jour max sauf si force=True).
    Retourne True si backup effectué, False sinon.
    """
    if not DRIVE_AVAILABLE:
        _dbg("Drive backup non disponible (module manquant)")
        return False

    # Vérifier la date du dernier backup
    if not force and LAST_BACKUP_FILE.exists():
        try:
            with open(LAST_BACKUP_FILE, "r") as f:
                last_backup_str = f.read().strip()
            last_backup = datetime.fromisoformat(last_backup_str)
            hours_since = (datetime.now() - last_backup).total_seconds() / 3600
            if hours_since < 24:
                _dbg(f"Drive backup skipped (dernier: il y a {hours_since:.1f}h)")
                return False
        except Exception:
            pass

    # Effectuer le backup
    try:
        _save_to_drive(activities)
        # Marquer la date du backup
        with open(LAST_BACKUP_FILE, "w") as f:
            f.write(datetime.now().isoformat())
        _dbg(f"Drive backup effectué: {len(activities)} activités")
        return True
    except Exception as e:
        _dbg(f"Drive backup échoué: {e}")
        return False


def restore_activities_from_drive() -> List[Dict[str, Any]]:
    """Restaure activities.json depuis Drive (en cas de perte du fichier local)."""
    if not DRIVE_AVAILABLE:
        raise RuntimeError("Drive non disponible pour restauration")

    try:
        activities = _load_from_drive()
        save_activities_local(activities)
        _dbg(f"Restauration depuis Drive: {len(activities)} activités")
        return activities
    except Exception as e:
        raise RuntimeError(f"Restauration Drive échouée: {e}") from e


# ========== PROFILE ==========

def load_profile_local() -> Dict[str, Any]:
    """Charge profile.json depuis le disque local."""
    if not PROFILE_FILE.exists():
        _dbg(f"{PROFILE_FILE} inexistant, retourne {{}}")
        return {"birth_date": "", "weight": 0, "events": []}

    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"{PROFILE_FILE} n'est pas un objet JSON")
        _dbg(f"profile loaded from local")
        return data
    except Exception as e:
        raise RuntimeError(f"Erreur lecture {PROFILE_FILE}: {e}") from e


def save_profile_local(profile: Dict[str, Any]) -> None:
    """Sauvegarde profile.json sur le disque local."""
    try:
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        _dbg(f"profile saved to local")
    except Exception as e:
        raise RuntimeError(f"Erreur écriture {PROFILE_FILE}: {e}") from e


# ========== OUTPUTS (analysis, predictions, weekly_plan, etc.) ==========

def read_output_json_local(filename: str) -> Optional[Any]:
    """Lit un JSON de sortie depuis outputs/."""
    filepath = OUTPUTS_DIR / filename
    if not filepath.exists():
        _dbg(f"{filepath} inexistant, retourne None")
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        _dbg(f"{filename} read ok")
        return data
    except Exception as e:
        raise RuntimeError(f"Erreur lecture {filepath}: {e}") from e


def write_output_json_local(filename: str, data: Any) -> None:
    """Écrit un JSON de sortie dans outputs/."""
    filepath = OUTPUTS_DIR / filename
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _dbg(f"{filename} write ok")
    except Exception as e:
        raise RuntimeError(f"Erreur écriture {filepath}: {e}") from e


# ========== HELPERS COMPATIBILITÉ ==========

# Aliases pour garder la compatibilité avec l'ancien code
load_activities_from_drive = load_activities_local
save_activities_to_drive = save_activities_local
load_profile_from_drive = load_profile_local
read_output_json = read_output_json_local
write_output_json = write_output_json_local
