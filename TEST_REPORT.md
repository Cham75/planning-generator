# Rapport de validation — Streamlit v5

## Contrôles techniques

- compilation Python de `app.py`, `web_store.py` et du moteur : réussie ;
- démarrage du serveur Streamlit en mode headless : réussi ;
- tests unitaires : 4 réussis ;
- persistance d'un rôle et d'une exclusion entre deux sessions simulées : validée ;
- suppression d'un agent initial sans réapparition automatique : validée ;
- suppression de toute la liste puis restauration explicite : validée ;
- sauvegarde/restauration JSON : validée.

## Fonctions v5 vérifiées dans le code

- fenêtre Streamlit `st.dialog` pour les agents sans rôle ;
- listes déroulantes pour renseigner les rôles ;
- ajout d'un agent dans une fenêtre dédiée ;
- sélection de plusieurs agents et confirmation avant suppression ;
- stockage uniquement dans le navigateur, sans Supabase.

## Formats d'entrée testés

| Fichier | Intervalles | Affectations | Manques |
|---|---:|---:|---:|
| Extraction brute.xlsx | 549 | 192 | 0 |
| report (18).xlsx | 494 | 189 | 3 |
| raport S15.xlsx | 404 | 159 | 1 |
| raport S10.xlsx | 560 | 192 | 0 |
| report S41.xlsx | 491 | 192 | 0 |
| raport S30.xlsx | 546 | 192 | 0 |
| report S51 2.xlsx | 503 | 192 | 0 |
| Extraction brute (1).xlsx | 404 | 159 | 1 |
| report S51 2(1).xlsx | 503 | 192 | 0 |

Les manques correspondent aux disponibilités réelles des fichiers concernés.
