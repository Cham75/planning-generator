# Rapport de validation — Streamlit v4

## Sauvegarde navigateur

- écriture des agents dans un stockage navigateur simulé ;
- rechargement avec un nouvel état de session Streamlit ;
- conservation du rôle et de l'exclusion validée ;
- export puis réimport JSON validé ;
- composant de stockage écrit avec l’API native `st.components.v2` ;
- aucun projet Supabase, secret, package de stockage tiers ou fichier serveur requis.

## Tests automatisés

```text
2 passed
```

## Tests des formats NICE

| Fichier | Intervalles | Affectations | Manques |
|---|---:|---:|---:|
| Extraction brute.xlsx | 549 | 192 | 0 |
| report (18).xlsx | 494 | 189 | 3 |
| raport S15.xlsx | 404 | 159 | 1 |
| raport S10.xlsx | 560 | 192 | 0 |
| raport S30.xlsx | 546 | 192 | 0 |
| report S41.xlsx | 491 | 192 | 0 |
| report S51 2.xlsx | 503 | 192 | 0 |
| Extraction brute (1).xlsx | 404 | 159 | 1 |
| report S51 2(1).xlsx | 503 | 192 | 0 |

Les manques signalés correspondent à une capacité réelle insuffisante sur les créneaux concernés et ne bloquent pas la génération du reste du planning.

## Démarrage

- compilation syntaxique Python : réussie ;
- serveur Streamlit démarré en mode headless ;
- réponse HTTP 200 reçue sur la page principale.
