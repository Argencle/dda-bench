## Architecture générale

* **Rendre le framework agnostique des codes**
  → Supprimer toute logique codée en dur ADDA/IFDDA/DDSCAT et introduire un système d’“engines” configurables via fichier config.

* **Introduire la notion d’engine instance**
  → Permettre de comparer deux versions du même code en définissant plusieurs exécutables distincts (ex : `adda_main` vs `adda_dev`).

* **Détection d’engine par prefix**
  → Identifier le code à lancer à partir du prefix de la ligne de commande au lieu d’un substring fragile.

* **Séparer logique générique et cas spéciaux**
  → Implémenter des plugins/adapters pour les comparaisons spéciales (force, champ interne, etc.) sans polluer le cœur du framework.

---

## Exécution et gestion des fichiers

* **Créer un working directory par commande**
  → Chaque run écrit dans son propre dossier pour éviter les collisions de fichiers (logs DDSCAT, ifdda.h5, runXXX…).

* **Collecte explicite des artefacts**
  → Copier les fichiers nécessaires (logs, HDF5, CSV…) dans le dossier du run et les passer explicitement aux extracteurs.

* **Éliminer les glob sur le dossier courant**
  → L’extraction doit lire uniquement les artefacts associés au run, pas l’état global du repo.

---

## Configuration

* **Remplacer les chemins hardcodés par une config runtime**
  → Définir les exécutables, variables d’environnement et options dans un fichier config portable.

* **Supprimer les effets de bord à l’import**
  → Appliquer les variables d’environnement via une fonction explicite au démarrage du programme.

---

## Extraction et quantités

* **Généraliser la définition des quantités**
  → Décrire les regex/patterns d’extraction dans la config plutôt que dans le code.

* **Gérer les occurrences multiples**
  → Permettre de choisir first/last/all/reduce lorsqu’une quantité apparaît plusieurs fois dans un fichier.

* **Support des quantités dérivées**
  → Calculer C à partir de Q (et inversement) en extrayant l’aire effective depuis la ligne de commande ou la config.

---

## Comparaisons

* **Externaliser les comparateurs spéciaux**
  → Déplacer les logiques spécifiques (force, champ interne, résidus) dans des modules dédiés.

* **Tolérance définie au niveau du cas**
  → Permettre de spécifier les attentes numériques par groupe/case via métadonnées.

---

## Output et traçabilité

* **Sauvegarder toutes les quantités extraites**
  → Produire un fichier structuré (CSV/JSON) contenant chaque valeur brute par run.

* **Sauvegarder les comparaisons**
  → Générer un fichier récapitulatif des erreurs relatives, digits, pass/fail.

* **Tracer la provenance**
  → Enregistrer pour chaque valeur : engine, commande, fichier source, temps CPU, mémoire.


## Nettoyage

* **Nettoyage centralisé des outputs**
  → Fournir une fonction unique qui supprime tous les artefacts temporaires en fin de run.

* **Structure d’arborescence claire**
  → Séparer runner / extractors / comparators / config pour une maintenance plus simple.

