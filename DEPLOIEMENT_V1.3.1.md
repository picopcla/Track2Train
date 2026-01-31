# 🚀 DÉPLOIEMENT VERSION 1.3.1 EN PRODUCTION

## 📅 Date
2025-11-09 17:35

---

## 🎯 OBJECTIF

Déploiement de la version 1.3.1 (mobile optimized) en production avec sauvegarde de la version 1.0.0.

---

## 📦 VERSIONS

### Version actuelle (avant déploiement)
- **Production** : v1.0.0
- **Staging** : v1.3.1

### Version après déploiement
- **Production** : v1.3.1 ✅
- **Backup** : v1.0.0 (sauvegardée dans `/opt/app/Track2Train-v1.0.0-backup`)

---

## 🔄 PROCÉDURE DE DÉPLOIEMENT

### Étape 1 : Sauvegarde v1.0.0

```bash
# Créer dossier backup
mkdir -p /opt/app/Track2Train-v1.0.0-backup

# Sauvegarder fichiers critiques de prod
cd /opt/app/Track2Train
cp -r templates /opt/app/Track2Train-v1.0.0-backup/
cp app.py get_streams.py /opt/app/Track2Train-v1.0.0-backup/

# Marquer la version
echo "1.0.0" > /opt/app/Track2Train-v1.0.0-backup/VERSION
```

**Résultat** : ✅ Version 1.0.0 sauvegardée dans `/opt/app/Track2Train-v1.0.0-backup`

---

### Étape 2 : Copie fichiers v1.3.1 vers prod

```bash
# Copier template modifié
cd /opt/app/Track2Train-staging
cp templates/index.html /opt/app/Track2Train/templates/index.html

# Copier fichiers Python
cp calculate_running_stats.py get_streams.py running_stats.json /opt/app/Track2Train/

# Marquer la nouvelle version
echo "1.3.1" > /opt/app/Track2Train/VERSION
```

**Fichiers déployés** :
- ✅ `templates/index.html` (mobile responsive + pan mode)
- ✅ `calculate_running_stats.py` (nouveau - fc_segments)
- ✅ `get_streams.py` (modifié - auto-update stats)
- ✅ `running_stats.json` (nouveau - stats précalculées)

---

### Étape 3 : Redémarrage services

```bash
# Reload graceful gunicorn app (port 8000)
kill -HUP 33098

# Reload graceful gunicorn webhook (port 5001)
kill -HUP 32997

# Attendre 3 secondes
sleep 3

# Vérifier que les processus sont actifs
ps aux | grep gunicorn | grep 8000
ps aux | grep gunicorn | grep 5001
```

**Résultat** : ✅ Services redémarrés sans interruption

---

### Étape 4 : Tests post-déploiement

#### Test 1 : Application répond
```bash
curl -s http://127.0.0.1:8000/ | head -20
```
**Résultat** : ✅ Page HTML retournée

#### Test 2 : Media query mobile présente
```bash
grep -n "max-width: 600px" /opt/app/Track2Train/templates/index.html
```
**Résultat** : ✅ 2 occurrences trouvées (lignes 78 et 163)

#### Test 3 : Mode PAN activé
```bash
grep -n "autoSelected.*pan" /opt/app/Track2Train/templates/index.html | wc -l
```
**Résultat** : ✅ 3 occurrences (FC, Allure, Élévation)

#### Test 4 : Nouveaux fichiers présents
```bash
ls -lh /opt/app/Track2Train/calculate_running_stats.py
ls -lh /opt/app/Track2Train/running_stats.json
```
**Résultat** : ✅ Fichiers présents (11K et 2.6K)

---

## ✅ VALIDATION

### Tous les tests passés

```
✅ Backup v1.0.0 créé
✅ Fichiers v1.3.1 copiés
✅ Services redémarrés
✅ Application répond
✅ Media query mobile présente
✅ Mode PAN activé (3 graphiques)
✅ Nouveaux fichiers présents
✅ Aucune erreur détectée
```

---

## 📊 DIFFÉRENCES v1.0.0 → v1.3.1

### Nouveaux fichiers
- `calculate_running_stats.py` : Calcul stats par type de run
- `running_stats.json` : Stats précalculées (fc_segments, moyennes)

### Fichiers modifiés
- `templates/index.html` :
  - Media query mobile (sparklines stack vertical)
  - Mode PAN actif par défaut (3 graphiques)
  - Courbe allure lime + épaisse
  - Courbe FC rouge pleine
  - /km en noir
- `get_streams.py` :
  - Auto-update running_stats.json après webhook

### Fonctionnalités ajoutées
1. ✅ FC par segments de distance (2/3/4 segments)
2. ✅ Auto-update stats après webhook
3. ✅ Sparklines responsive mobile
4. ✅ Mode PAN graphiques par défaut
5. ✅ Améliorations visuelles (couleurs, épaisseurs)

---

## 🔙 ROLLBACK (si nécessaire)

En cas de problème, retour à la v1.0.0 :

```bash
# Arrêter services
kill -HUP <PID_gunicorn_app>
kill -HUP <PID_gunicorn_webhook>

# Restaurer fichiers
cp -r /opt/app/Track2Train-v1.0.0-backup/templates/* /opt/app/Track2Train/templates/
cp /opt/app/Track2Train-v1.0.0-backup/app.py /opt/app/Track2Train/
cp /opt/app/Track2Train-v1.0.0-backup/get_streams.py /opt/app/Track2Train/

# Supprimer nouveaux fichiers v1.3.1
rm /opt/app/Track2Train/calculate_running_stats.py
rm /opt/app/Track2Train/running_stats.json

# Marquer version
echo "1.0.0" > /opt/app/Track2Train/VERSION

# Redémarrer services
kill -HUP <PID_gunicorn_app>
kill -HUP <PID_gunicorn_webhook>
```

---

## 🗂️ STRUCTURE FICHIERS

### Production (/opt/app/Track2Train)
```
Track2Train/
├── VERSION (1.3.1)
├── app.py
├── get_streams.py (modifié)
├── calculate_running_stats.py (nouveau)
├── running_stats.json (nouveau)
├── templates/
│   └── index.html (modifié)
└── .venv/
```

### Backup (/opt/app/Track2Train-v1.0.0-backup)
```
Track2Train-v1.0.0-backup/
├── VERSION (1.0.0)
├── app.py
├── get_streams.py
└── templates/
    └── index.html
```

---

## 📝 COMMANDES UTILES

### Vérifier version en cours
```bash
cat /opt/app/Track2Train/VERSION
```

### Vérifier processus gunicorn
```bash
ps aux | grep gunicorn | grep -v grep
```

### Logs gunicorn (si configurés)
```bash
tail -f /var/log/track2train/app.log
tail -f /var/log/track2train/webhook.log
```

### Tester webhook
```bash
curl -X POST http://127.0.0.1:5001/webhook \
  -H "Content-Type: application/json" \
  -d '{"object_type":"activity","aspect_type":"create","object_id":123456}'
```

---

## 🎉 RÉSULTAT

### Déploiement réussi

- ✅ Version 1.3.1 en production
- ✅ Version 1.0.0 sauvegardée
- ✅ Services opérationnels
- ✅ Aucune interruption de service
- ✅ Tous les tests passés

### Bénéfices utilisateur

1. **Mobile** : Sparklines visibles, graphiques bloqués
2. **Automatisation** : Stats auto-update après webhook
3. **Visuels** : Courbes optimisées, couleurs améliorées
4. **Données** : FC par segments de distance

---

## 📋 CHECKLIST POST-DÉPLOIEMENT

- [x] Backup v1.0.0 créé
- [x] Fichiers copiés
- [x] Services redémarrés
- [x] Application répond
- [x] Tests passés
- [ ] Test utilisateur mobile réel
- [ ] Monitoring 24h
- [ ] Vérifier prochain run avec webhook

---

**Date de déploiement** : 2025-11-09 17:35
**Déployé par** : Claude Code
**Version prod** : 1.3.1 ✅
**Backup** : /opt/app/Track2Train-v1.0.0-backup
**Statut** : ✅ Succès
