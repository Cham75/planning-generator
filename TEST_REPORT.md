# Rapport de validation — Streamlit v6

## Contrôles techniques

- compilation Python de `app.py`, `web_store.py` et du moteur : réussie ;
- tests automatisés : **6 réussis** ;
- persistance navigateur, suppression durable et sauvegarde JSON : validées ;
- rotation équitable des superviseurs de 19h à 20h : validée sur un scénario synthétique de cinq jours ;
- un Morning Brief hebdomadaire de 15 minutes par superviseur, sans simultanéité : validé ;
- deux heures de Picking QVCA par superviseur : validées ;
- absence de chevauchement entre assistance, Morning Brief et Picking QVCA : validée ;
- présence des nouvelles activités dans l’Excel et dans le récapitulatif : validée.

## Formats d'entrée testés

| Fichier | Intervalles | Affectations assistance | Manques assistance |
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

Les manques correspondent aux disponibilités réelles des fichiers concernés. Lorsque moins de deux superviseurs terminant à 20h sont disponibles, l'outil conserve la couverture avec les autres agents éligibles lorsque possible et ajoute un avertissement dans l'onglet **Contrôles**.
