#!/bin/bash

# Script de rollback vers version 2.7.0
# Usage: bash rollback.sh

set -e

BACKUP_DIR="/opt/app/Track2Train-staging/milestones/v2.8.0_20251221_200056"
APP_DIR="/opt/app/Track2Train-staging"

echo "🔄 Rollback Track2Train v2.8.0 → v2.7.0"
echo "========================================"
echo ""
echo "⚠️  Cette opération va restaurer les fichiers de la version 2.7.0"
echo ""
read -p "Continuer ? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "❌ Rollback annulé"
    exit 1
fi

echo ""
echo "📦 Restauration des fichiers..."

# Backup de la version actuelle avant rollback
CURRENT_BACKUP="$APP_DIR/milestones/pre-rollback_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$CURRENT_BACKUP"
cp "$APP_DIR/app.py" "$CURRENT_BACKUP/"
cp -r "$APP_DIR/templates" "$CURRENT_BACKUP/"
cp -r "$APP_DIR/prompts" "$CURRENT_BACKUP/"
cp "$APP_DIR/VERSION" "$CURRENT_BACKUP/"
echo "✅ Backup actuel créé dans: $CURRENT_BACKUP"

# Restauration
cd "$APP_DIR"
cp "$BACKUP_DIR/app.py" .
cp -r "$BACKUP_DIR/templates/"* templates/
cp -r "$BACKUP_DIR/prompts/"* prompts/
echo "2.7.0" > VERSION
sudo cp "$BACKUP_DIR/track2train-staging.service" /etc/systemd/system/

echo "✅ Fichiers restaurés"
echo ""
echo "🔄 Redémarrage du service..."

sudo systemctl daemon-reload
sudo systemctl restart track2train-staging

echo "✅ Service redémarré"
echo ""
echo "🎉 Rollback terminé vers version 2.7.0"
echo ""
echo "Pour vérifier: sudo systemctl status track2train-staging"
