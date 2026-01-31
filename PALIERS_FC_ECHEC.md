# ❌ ÉCHEC - Tentative Paliers FC

## 📅 Date
2025-11-09

---

## 🎯 OBJECTIF

Afficher des lignes horizontales FC par segments en escalier sur le graphique.

---

## ❌ RÉSULTAT

**ÉCHEC** - Les graphiques ne s'affichaient plus du tout.

---

## 🔍 PROBLÈME IDENTIFIÉ

L'approche avec séries multiples (`fcSeries{{ loop.index0 }}`) causait un plantage JavaScript qui empêchait l'affichage de tous les graphiques.

**Symptôme** : Page blanche ou graphiques absents.

---

## 🔄 ROLLBACK EFFECTUÉ

Retour immédiat à la **VERSION 1.2 STABLE** :

```javascript
// Version 1.2 - Fonctionne
const optionsFC{{ loop.index0 }} = {
    series: [{
        name: 'FC',
        data: fc{{ loop.index0 }}.map((val, idx) => ({
            x: labels{{ loop.index0 }}[idx],
            y: val
        }))
    }],
    stroke: {
        width: 2,
        curve: 'smooth'
    },
    colors: ['#ef4444']
};
```

---

## 📝 LEÇON APPRISE

Les séries multiples avec ApexCharts nécessitent une approche différente. La génération dynamique via Jinja2 de tableaux de styles peut causer des erreurs JavaScript subtiles.

---

## ✅ VERSION STABLE ACTUELLE

**Version 1.2** :
- ✅ Courbe FC rouge pleine
- ✅ Courbe Allure vert lime épaisse
- ✅ /km en noir
- ✅ Pas de ligne FC max
- ✅ Graphiques fonctionnels

---

## 🚫 ABANDON PALIERS FC

Les paliers FC par segments sont **abandonnés** pour le moment.

**Raison** : Complexité technique vs bénéfice utilisateur incertain.

---

**Date d'échec** : 2025-11-09
**Rollback effectué** : Oui
**Version actuelle** : 1.2 (stable)
