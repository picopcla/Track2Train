from flask import Flask, request, jsonify, Response
import subprocess
import os
import sys
import logging

app = Flask(__name__)

# Logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Chemin absolu du script get_streams.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GET_STREAMS_PATH = os.path.join(SCRIPT_DIR, "get_streams.py")
VENV_PYTHON = os.path.join(SCRIPT_DIR, ".venv", "bin", "python")

# Token de vérification (peut être défini via la variable d'environnement STRAVA_VERIFY_TOKEN)
VERIFY_TOKEN = os.environ.get("STRAVA_VERIFY_TOKEN", "STRAVA")


@app.route("/webhook", methods=["GET", "POST", "HEAD"])
def webhook():
    # HEAD est traité automatiquement comme GET sans body
    if request.method in ["GET", "HEAD"]:
        # Pour la validation du webhook par Strava
        mode = request.args.get("hub.mode")
        verify_token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        logger.info(f"🔍 Validation reçue: mode={mode}, token={verify_token}, challenge={challenge}")

        # Vérifications
        if not challenge:
            logger.warning("❌ Challenge manquant")
            return jsonify({"error": "hub.challenge is required"}), 400

        if mode != "subscribe":
            logger.warning(f"❌ Mode invalide: {mode}")
            return jsonify({"error": "hub.mode must be 'subscribe'"}), 400

        # Vérifie le token (pour plus de sécurité)
        if verify_token != VERIFY_TOKEN:
            logger.warning(f"❌ Token invalide: {verify_token}")
            return jsonify({"error": "Invalid verify_token"}), 403

        logger.info(f"✅ Validation réussie : challenge = {challenge}")
        # Strava attend la chaîne challenge en texte brut
        return Response(challenge, status=200, mimetype="text/plain")

    if request.method == "POST":
        # Pour recevoir les notifications Strava
        data = request.get_json(silent=True)
        logger.info("📩 Notification Strava reçue : %s", data)

        if not data:
            logger.warning("❌ Requête POST sans JSON")
            return jsonify({"error": "Invalid JSON"}), 400

        # Si c'est une nouvelle activité créée
        if data.get("object_type") == "activity" and data.get("aspect_type") == "create":
            activity_id = data.get("object_id")
            if not activity_id:
                logger.warning("❌ object_id manquant dans la notification")
                return jsonify({"error": "object_id is required"}), 400

            logger.info(f"🎯 Nouvelle activité détectée : {activity_id}")

            # Détermine quel binaire Python utiliser (venv si présent, sinon l'interpréteur courant)
            python_executable = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable
            if python_executable != VENV_PYTHON:
                logger.info(f"⚠️  .venv python introuvable, utilisation de {python_executable}")

            try:
                # Lance ton script get_streams.py en arrière-plan avec le bon python
                subprocess.Popen([python_executable, GET_STREAMS_PATH, str(activity_id)],
                                 cwd=SCRIPT_DIR,
                                 close_fds=True)
                logger.info("🚀 Script get_streams.py lancé en tâche de fond.")
            except Exception as e:
                logger.exception("❌ Erreur lors du lancement du script get_streams.py : %s", e)
                return jsonify({"error": "failed to launch background job"}), 500

        return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    # Expose le serveur sur le port 5003
    app.run(host="0.0.0.0", port=5003)