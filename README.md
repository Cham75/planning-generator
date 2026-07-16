# Planning Assistance — Streamlit

Application web simple :

1. importer une ou plusieurs extractions NICE `.xlsx` ;
2. vérifier les rôles et exclusions ;
3. générer puis télécharger le planning Excel au format quotidien.

## Lancer en local

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

## Mettre en ligne sur Streamlit Community Cloud

1. Créer un dépôt GitHub et y déposer tout le contenu de ce dossier.
2. Ouvrir Streamlit Community Cloud et choisir **Deploy an app**.
3. Sélectionner le dépôt, la branche principale et `app.py` comme fichier d'entrée.
4. Déployer puis partager l'adresse `https://...streamlit.app`.

Les mises à jour sont faites en modifiant le dépôt GitHub : l'application en ligne reprend ensuite la nouvelle version.

## Données des agents

Le serveur ne conserve pas durablement les rôles. Après une modification, utiliser **Télécharger la liste des rôles** pour récupérer `agents.json`, puis le réimporter lors de la prochaine utilisation.

## Confidentialité

Les fichiers Excel sont traités par l'instance Streamlit pendant l'utilisation. Avant un usage professionnel réel, vérifier que l'entreprise autorise l'envoi de ces données vers un service cloud externe.
