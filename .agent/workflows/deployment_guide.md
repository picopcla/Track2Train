---
description: Procédure de transfert propre entre Local et VM
---

Pour éviter de "casser" l'environnement (notamment avec le dossier `venv` ou des écrasements de fichiers sensibles), voici la méthode recommandée :

### 1. Ce qu'il ne faut JAMAIS transférer
Certains dossiers sont spécifiques à votre système (Windows) et corrompent la VM (Linux).
- **`venv/`** : Toujours laisser chaque machine avoir son propre environnement.
- **`__pycache__/`** : Fichiers编译 temporaires.
- **`.env`** : Contient des chemins souvent différents (C:\ vs /opt/...).

### 2. Méthode recommandée : Le script de synchronisation (Linux/WSL)
Si vous utilisez un terminal Linux ou WSL sur votre PC, utilisez `rsync`. C'est l'outil standard qui ignore intelligemment ce que vous lui demandez :

```bash
# Exemple de commande depuis votre PC vers la VM
rsync -avz --exclude 'venv/' --exclude '__pycache__/' --exclude '.env' --exclude '.git/' ./ stravacoach@ip_vm:/opt/app/Track2Train-staging/
```

### 3. Méthode simplifiée : Archivage (Zip/Tar)
Si vous copiez manuellement les fichiers :
1. Créez un Zip de votre code **SANS** le dossier `venv`.
2. Envoyez-le sur la VM.
3. Désarchivez-le dans le dossier cible.
4. Sur la VM, si une bibliothèque manque : `./venv/bin/pip install -r requirements.txt`.

### 4. Automatiser le redémarrage (Sur la VM)
Créez un petit script `deploy.sh` sur votre VM pour relancer l'app en un clin d'œil :
```bash
#!/bin/bash
cd /opt/app/Track2Train-staging
sudo pkill -9 python
./venv/bin/python app.py &
echo "Dashboard v2.15 relancé !"
```

### 5. Utiliser Git (Le Standard Industriel)
C'est la solution la plus propre :
1. **Local** : `git commit` et `git push` vers un dépôt (ex: GitHub privé).
2. **VM** : `git pull`. 
3. Les fichiers ignorés sont gérés automatiquement par un fichier `.gitignore`.
