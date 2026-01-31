#!/bin/bash

CLIENT_ID="${STRAVA_CLIENT_ID:-162245}"
CLIENT_SECRET="${STRAVA_CLIENT_SECRET:-0552c0e87d83493d7f6667d0570de1e8ac9e9a68}"
CALLBACK_URL="https://app.track2train.fr/webhook"
VERIFY_TOKEN="STRAVA"

# Utiliser l'IP de api.strava.com (résolution manuelle)
API_HOST="api.strava.com"

echo "🔍 Vérification des subscriptions existantes..."
curl --resolve $API_HOST:443:34.117.186.192 \
  -G https://$API_HOST/api/v3/push_subscriptions \
  -d client_id=$CLIENT_ID \
  -d client_secret=$CLIENT_SECRET

echo -e "\n\n📝 Création de la subscription webhook..."
curl --resolve $API_HOST:443:34.117.186.192 \
  -X POST https://$API_HOST/api/v3/push_subscriptions \
  -F client_id=$CLIENT_ID \
  -F client_secret=$CLIENT_SECRET \
  -F callback_url=$CALLBACK_URL \
  -F verify_token=$VERIFY_TOKEN

echo -e "\n✅ Done!"
