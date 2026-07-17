# Planning Assistance — Streamlit v6

Application web Streamlit sans base de données et sans installation sur le poste utilisateur.

## Nouveautés v6

- De 19h à 20h, les deux positions d’assistance sont attribuées en priorité à des superviseurs dont la vacation se termine à 20h. La rotation est équilibrée sur la semaine.
- L’heure obligatoire quotidienne reste prioritaire : si la règle 19h–20h entre en conflit avec une obligation réalisable, le moteur conserve d’abord les heures obligatoires et signale la rotation incomplète.
- Chaque superviseur actif reçoit un **Morning Brief de 15 minutes** sur l’ensemble de la semaine, du lundi au vendredi entre 11h30 et 15h30. Deux Morning Briefs ne sont jamais placés en même temps.
- Chaque superviseur actif reçoit **deux créneaux d’une heure de Picking QVCA** du lundi au vendredi. Les deux heures peuvent être consécutives.
- Les activités sont placées sans chevaucher l’assistance, les pauses ou une autre activité planifiée.
- Ordre de priorité appliqué : assistance obligatoire, rotation superviseurs 19h–20h, Morning Brief, Picking QVCA.
- Le planning Excel et l’aperçu Streamlit affichent directement `Morning Brief` et `Picking QVCA`.
- L’onglet **Récap Assistances** contient maintenant le total de Picking QVCA et le créneau de Morning Brief de chaque superviseur.

Les fonctions interactives v5 restent disponibles : fenêtre automatique pour les rôles manquants, listes déroulantes, ajout/suppression d’agents et stockage dans le navigateur.

## Conservation des agents

Les agents, rôles, exclusions et notes sont stockés dans le `localStorage` du navigateur :

- aucune base Supabase ;
- aucun compte supplémentaire ;
- aucune donnée d'agent enregistrée sur le serveur Streamlit ;
- conservation après fermeture du navigateur et redéploiement de l'application, tant que la même URL et le même profil Chrome/Edge sont utilisés.

L'écran **Agents et rôles** permet aussi d'exporter ou restaurer un fichier `agents.json`.

## Déploiement

1. Déposer le contenu de ce dossier dans le dépôt GitHub de l'application.
2. Conserver `app.py` comme fichier principal dans Streamlit Community Cloud.
3. Commit et push sur la branche utilisée par Streamlit.
4. Streamlit redéploie automatiquement la nouvelle version.

Aucun secret et aucune configuration externe ne sont nécessaires.

## Utilisation

### Générer un planning

1. Importer une ou plusieurs extractions NICE `.xlsx`.
2. Choisir les feuilles ou semaines dans la liste déroulante.
3. Si des rôles manquent, les renseigner dans la fenêtre qui s'ouvre.
4. Vérifier éventuellement l'ensemble des agents de l'extraction.
5. Cliquer sur **Générer le planning Excel**.
6. Consulter l'aperçu par journée et télécharger le fichier.

### Gérer les agents

Dans **Agents et rôles** :

- rechercher ou filtrer les agents ;
- modifier les rôles avec les listes déroulantes ;
- cocher plusieurs lignes puis cliquer sur **Supprimer la sélection** ;
- cliquer sur **Ajouter un agent** pour ouvrir le formulaire ;
- exporter une sauvegarde JSON.

## Formats NICE reconnus

Le parseur prend en charge les formats fournis S10, S15, S18, S30, S41, S51 et les différentes extractions brutes, notamment :

- `Horaires d'agent` et `Horaires d’agent` ;
- feuilles renommées avec structure NICE reconnue ;
- colonne `Fin` placée à différents endroits ;
- fin d'activité absente et déduite du début suivant ;
- plusieurs feuilles dans un même classeur ;
- semaines de cinq ou six jours ;
- pauses à la demi-heure, congés, formations, réunions et jours libres.

## Lancement local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
