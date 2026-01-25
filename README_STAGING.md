# 🚧 ENVIRONNEMENT DE STAGING

Ce dossier est pour le DÉVELOPPEMENT uniquement.

## Ports
- App principale : http://localhost:5002
- Webhook : http://localhost:5003

## Lancer l'app en staging
cd /opt/app/Track2Train-staging
python app.py

## PRODUCTION (NE PAS TOUCHER)
- Dossier : /opt/app/Track2Train
- Ports : 5000 (app) + 5001 (webhook)

## Utiliser Claude Code
cd /opt/app/Track2Train-staging
claude-code

⚠️ TOUJOURS vérifier qu'on est dans Track2Train-staging avant de coder !
