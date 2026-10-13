from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_JSON = PROJECT_DIR / "output" / "kpi_resume.json"


@st.cache_data
def load_report(path: str, modified_at: float) -> dict:
    del modified_at
    with Path(path).open(encoding="utf-8") as report_file:
        return json.load(report_file)


def percentage(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def get_gemini_key() -> str | None:
    """Read the deployment secret without displaying it in the UI."""
    try:
        secret = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        secret = None
    return secret or os.environ.get("GEMINI_API_KEY")


def generate_ai_summary(report: dict) -> str:
    """Generate a summary from aggregated KPIs only."""
    api_key = get_gemini_key()
    if not api_key:
        return "Aucune clé Gemini n'est configurée pour cette application."

    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=(
            "Tu es un analyste BIAT. Rédige une synthèse managériale concise en "
            "français avec constats, alertes et recommandations. Utilise uniquement "
            "les indicateurs agrégés fournis; n'invente aucun chiffre et ne demande "
            "pas de données personnelles.\n\n"
            f"{json.dumps(report, ensure_ascii=False)}"
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini a renvoyé une réponse vide.")
    return text


def main() -> None:
    st.set_page_config(
        page_title="BIAT - Salle des marchés",
        page_icon="📞",
        layout="wide",
    )

    st.title("📞 BIAT — Salle des marchés")
    st.caption("Tableau de bord des exports Cisco UCCX/CUIC")

    with st.sidebar:
        st.header("Rapport")
        report_path = st.text_input("Fichier JSON", str(DEFAULT_JSON))
        report_file = Path(report_path).expanduser()
        if not report_file.exists():
            st.error(f"Fichier introuvable : {report_file}")
            st.stop()
        if st.button("Rafraîchir les données"):
            st.cache_data.clear()
            st.rerun()

    report = load_report(str(report_file), report_file.stat().st_mtime)
    meta = report["meta"]
    summary = report["resume_global"]
    daily = pd.DataFrame(report.get("detail_par_jour", []))
    hourly = pd.DataFrame(report.get("detail_par_heure", []))
    sensitivity = pd.DataFrame(report.get("sensibilite_fenetre_reconciliation", []))

    st.caption(
        f"Dernière génération : {meta.get('generated_at', 'N/A')} · "
        f"Source : {meta.get('source', 'N/A')}"
    )

    if summary.get("taux_abandon_global") is not None and summary["taux_abandon_global"] > 0.30:
        st.warning(
            f"⚠️ Taux d'abandon élevé : "
            f"{percentage(summary['taux_abandon_global'])} (seuil : 30%)."
        )

    kpi_columns = st.columns(5)
    kpi_columns[0].metric("Appels reçus", f"{summary['total_received']:,}")
    kpi_columns[1].metric("Appels perdus", f"{summary['total_missed_reellement_perdu']:,}")
    kpi_columns[2].metric("Taux d'abandon", percentage(summary["taux_abandon_global"]))
    kpi_columns[3].metric("AHT", f"{summary['aht_global_seconds']:.2f} s")
    kpi_columns[4].metric("Ring time", f"{summary['ringtime_moyen_global_seconds']:.2f} s")

    st.subheader("Évolution quotidienne")
    if daily.empty:
        st.info("Aucune donnée quotidienne disponible.")
    else:
        daily["jour"] = pd.to_datetime(daily["jour"])
        daily_chart = daily.set_index("jour")[
            ["volume_received", "volume_missed_reellement_perdu", "volume_initiated"]
        ]
        st.bar_chart(daily_chart)
        rate_chart = daily.set_index("jour")[["taux_abandon"]].dropna() * 100
        st.line_chart(rate_chart)
        st.dataframe(
            daily.assign(
                taux_abandon=daily["taux_abandon"].map(
                    lambda value: percentage(value) if pd.notna(value) else "N/A"
                )
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Profil horaire")
    if hourly.empty:
        st.info("Aucune donnée horaire disponible.")
    else:
        hourly_chart = hourly.set_index("heure")[
            ["volume_received", "volume_missed_reellement_perdu"]
        ]
        st.bar_chart(hourly_chart)
        st.dataframe(
            hourly.assign(
                taux_abandon=hourly["taux_abandon"].map(
                    lambda value: percentage(value) if pd.notna(value) else "N/A"
                )
            ),
            use_container_width=True,
            hide_index=True,
        )

    left, right = st.columns(2)
    with left:
        st.subheader("Qualité du nettoyage")
        dedup = meta["dedoublonnage_missed"]
        reconciliation = meta["reconciliation_missed_vs_received"]
        st.metric("Doublons supprimés", f"{dedup['removed_duplicates']:,}")
        st.metric("Réduction des doublons", f"{dedup['reduction_rate']:.2f}%")
        st.metric("Faux abandons réconciliés", f"{reconciliation['missed_reconcilies']:,}")
        st.caption(
            f"Fenêtre de réconciliation : {reconciliation['tolerance_minutes']} minutes"
        )
    with right:
        st.subheader("Sensibilité de la fenêtre")
        if sensitivity.empty:
            st.info("Aucune analyse de sensibilité disponible.")
        else:
            sensitivity_chart = sensitivity.set_index("tolerance_minutes")[["taux_abandon"]] * 100
            st.line_chart(sensitivity_chart)
            st.dataframe(
                sensitivity.assign(
                    taux_abandon=sensitivity["taux_abandon"].map(
                        lambda value: percentage(value) if pd.notna(value) else "N/A"
                    )
                ),
                use_container_width=True,
                hide_index=True,
            )

    st.subheader("Synthèse managériale")
    if "ai_summary" not in st.session_state:
        st.session_state["ai_summary"] = report.get(
            "synthese_ia", "Aucune synthèse disponible."
        )
    if st.button("Générer une nouvelle synthèse avec Gemini"):
        with st.spinner("Gemini analyse les indicateurs agrégés..."):
            try:
                st.session_state["ai_summary"] = generate_ai_summary(report)
                st.success("Synthèse Gemini générée.")
            except Exception as exc:
                st.error(f"Gemini n'est pas disponible : {exc}")
    st.markdown(st.session_state["ai_summary"])
    st.caption(
        "Les KPI sont calculés localement. La synthèse peut être générée par Gemini "
        "ou par le mode local de secours. Aucune ligne d'appel brute n'est envoyée."
    )


if __name__ == "__main__":
    main()
