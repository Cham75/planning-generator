# Planning Assistance — Streamlit v4

Application web Streamlit autonome, sans Supabase, sans base de données et sans exécutable.

## Fonctionnement

- import d'une ou plusieurs extractions NICE `.xlsx` ;
- détection automatique des variantes de format et des feuilles disponibles ;
- sélection de la semaine avec une liste déroulante ;
- gestion interactive des agents, rôles, exclusions et notes ;
- mémorisation automatique des agents dans le stockage local du navigateur ;
- détection des nouveaux agents avec rôle à choisir dans un menu déroulant ;
- aperçu du planning par journée ;
- génération et téléchargement de l'Excel final.

## Conservation des agents

Les agents sont enregistrés dans le `localStorage` du navigateur par un composant natif Streamlit intégré au projet :

- ils restent disponibles après fermeture ou actualisation de la page ;
- ils restent disponibles après une mise à jour de l'application Streamlit ;
- aucune base de données n'est nécessaire ;
- les extractions NICE et les plannings générés ne sont pas enregistrés.

La conservation est liée au même ordinateur, au même profil de navigateur et à la même URL Streamlit. L'écran **Agents et rôles** permet d'exporter un fichier `agents.json` pour sauvegarder ou transférer la configuration vers un autre ordinateur.

## Déploiement

1. Déposer tout ce dossier dans le dépôt GitHub déjà relié à Streamlit Cloud.
2. Conserver `app.py` comme fichier principal.
3. Pousser les changements sur la branche déployée.
4. Streamlit redéploie l'application ; aucune configuration de secrets n'est nécessaire.

Pour conserver les agents déjà saisis, garder la même application et la même URL Streamlit. Ne pas créer une nouvelle application avec une autre adresse.

## Écrans

### Générer un planning

1. Importer un ou plusieurs fichiers NICE.
2. Choisir la ou les feuilles détectées.
3. Vérifier les rôles proposés.
4. Choisir le rôle de chaque nouvel agent dans la liste déroulante.
5. Enregistrer les rôles ou générer directement le planning.
6. Consulter l'aperçu par jour puis télécharger l'Excel.

### Agents et rôles

- recherche et filtres ;
- modification du rôle par liste déroulante ;
- exclusion ou réintégration ;
- notes ;
- ajout manuel ;
- export/import d'une sauvegarde JSON ;
- réinitialisation vers la liste initiale.

## Formats NICE couverts

Le parseur a été testé avec les exemples S10, S15, S18, S30, S41, S51 et les extractions brutes fournies. Il prend en charge :

- `Horaires d'agent` et `Horaires d’agent` ;
- feuilles renommées reconnues par leur structure ;
- colonne `Fin` placée à différents endroits ;
- fin d'activité absente et déduite du début suivant ;
- plusieurs feuilles dans un même classeur ;
- semaines de cinq ou six jours ;
- pauses à la demi-heure, congés, formations, réunions et jours libres.

## Lancement local facultatif

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
