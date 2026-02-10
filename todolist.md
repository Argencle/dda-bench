## Architecture générale

* **Rendre le framework agnostique des codes**
  → Supprimer toute logique codée en dur ADDA/IFDDA/DDSCAT et introduire un système d’“engines” configurables via fichier config.

* **Séparer logique générique et cas spéciaux**
  → Implémenter des plugins/adapters pour les comparaisons spéciales (force, champ interne, etc.) sans polluer le cœur du framework.

---

## Extraction et quantités

* **Généraliser la définition des quantités**
  → Décrire les regex/patterns d’extraction dans la config plutôt que dans le code.

* **Gérer les occurrences multiples**
  → Permettre de choisir first/last/all/reduce lorsqu’une quantité apparaît plusieurs fois dans un fichier.

---

## Comparaisons

* **Externaliser les comparateurs spéciaux**
  → Déplacer les logiques spécifiques (force, champ interne, résidus) dans des modules dédiés.

* **Tolérance définie au niveau du cas**
  → Permettre de spécifier les attentes numériques par groupe/case via métadonnées.

---

## Nettoyage

* **Structure d’arborescence claire**
  → Séparer runner / extractors / comparators / config pour une maintenance plus simple.

