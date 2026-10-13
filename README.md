# BIAT - Salle des marches dashboard

Dashboard Streamlit de consultation des indicateurs agreges d'appels Cisco
UCCX/CUIC.

## Lancer localement

```powershell
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploiement Streamlit Community Cloud

1. Selectionner `streamlit_app.py` comme fichier principal.
2. Dans les secrets de l'application, ajouter :

```toml
GEMINI_API_KEY = "votre_nouvelle_cle"
```

La cle ne doit jamais etre committee. L'application utilise uniquement le
JSON de KPI agreges et ne contient pas les CSV ni le pipeline interne.
