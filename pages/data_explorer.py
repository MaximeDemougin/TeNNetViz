import streamlit as st
import pandas as pd
import pygwalker as pyg
from data import prepare_bets_data

st.set_page_config(
    layout="wide",
    page_icon="logo_TeNNet.png",
    page_title="Exploration de données - TeNNet",
)

# Style global pour le fond de page
st.markdown(
    """
    <style>
        /* Fond de page avec gradient élégant */
        [data-testid="stAppViewContainer"] {
            background: linear-gradient(180deg, 
                rgba(15,15,20,1) 0%, 
                rgba(20,20,25,1) 50%, 
                rgba(15,15,20,1) 100%);
        }
        
        /* Fond de la sidebar si présente */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, 
                rgba(20,20,25,0.95) 0%, 
                rgba(15,15,20,0.95) 100%);
        }
        
        /* Header */
        [data-testid="stHeader"] {
            background: transparent;
        }
        
        /* Titre principal */
        h1 {
            color: #e0e0e0 !important;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }
        
        /* Sous-titres */
        h2, h3 {
            color: #d1d5db !important;
        }

        /* PyGWalker container */
        .pygwalker-container {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            padding: 20px;
            margin-top: 20px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔍 Exploration de données interactive")

# Vérifier que l'utilisateur est connecté
if not st.session_state.get("logged_in", False):
    st.warning("⚠️ Veuillez vous connecter pour accéder à cette page.")
    st.stop()

# Options de sélection des données
st.sidebar.header("Options de données")

data_source = st.sidebar.radio(
    "Choisissez la source de données :",
    ["Paris terminés", "Paris en cours", "Les deux"],
)


# Charger les données selon la sélection
@st.cache_data(ttl=300)
def load_explorer_data(user_id, source):
    """Charge les données pour l'explorateur"""
    if source == "Paris terminés":
        df = prepare_bets_data(user_id, finished=True)
    elif source == "Paris en cours":
        df = prepare_bets_data(user_id, finished=False)
    else:  # Les deux
        df_finished = prepare_bets_data(user_id, finished=True)
        df_ongoing = prepare_bets_data(user_id, finished=False)
        # Ajouter une colonne pour distinguer
        df_finished["Statut"] = "Terminé"
        df_ongoing["Statut"] = "En cours"
        df = pd.concat([df_finished, df_ongoing], ignore_index=True)

    return df


try:
    # Charger les données
    with st.spinner("Chargement des données..."):
        df = load_explorer_data(st.session_state.ID_USER, data_source)

    if df is None or df.empty:
        st.info("📊 Aucune donnée disponible pour l'exploration.")
        st.stop()

    # Afficher des informations sur le jeu de données
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📊 Nombre de paris", len(df))
    with col2:
        st.metric("📈 Colonnes", len(df.columns))
    with col3:
        if "Gains net" in df.columns:
            total_gains = df["Gains net"].sum()
            st.metric("💰 Gains totaux", f"{total_gains:.2f}€")

    st.markdown("---")

    # Description
    st.markdown(
        """
    ### 💡 Guide d'utilisation
    
    **PyGWalker** vous permet de créer des visualisations interactives en glissant-déposant les colonnes :
    
    - **📊 Graphiques** : Créez des graphiques en glissant des colonnes vers les axes X et Y
    - **📋 Tableaux** : Visualisez vos données sous forme de tableau croisé dynamique
    - **🔍 Filtres** : Filtrez vos données en glissant des colonnes vers la zone de filtre
    - **🎨 Couleurs** : Ajoutez des dimensions supplémentaires avec la couleur
    - **💾 Export** : Sauvegardez vos visualisations
    
    Explorez vos paris par compétition, surface, niveau, et bien plus encore !
    """
    )

    # Options PyGWalker
    with st.expander("⚙️ Options avancées"):
        dark_mode = st.checkbox("Mode sombre", value=True)
        show_toolbar = st.checkbox("Afficher la barre d'outils", value=True)

    st.markdown("---")

    # Créer et afficher PyGWalker
    st.markdown('<div class="pygwalker-container">', unsafe_allow_html=True)

    # Configuration de PyGWalker
    walker_config = {
        "dark": "dark" if dark_mode else "light",
        "hideToolBar": not show_toolbar,
    }

    # Utiliser pyg.walk pour afficher l'interface interactive
    pyg.walk(
        df,
        env="Streamlit",
        spec_io_mode="rw",  # Permet de sauvegarder/charger les configurations
        use_kernel_calc=True,  # Optimisation des performances
        return_html=False,
        dark=walker_config["dark"],
        hideToolBar=walker_config["hideToolBar"],
    )

    st.markdown("</div>", unsafe_allow_html=True)

    # Section d'aide supplémentaire
    with st.expander("❓ Aide - Colonnes disponibles"):
        st.markdown(
            """
        **Colonnes disponibles dans vos données :**
        """
        )

        cols_info = {
            "Match": "Nom du match (Joueur 1 - Joueur 2)",
            "Date": "Date et heure du match",
            "Compétition": "Type de compétition (ATP, WTA, Doubles)",
            "Level": "Niveau du tournoi (Grand Chelem, Masters, etc.)",
            "Round": "Tour du tournoi",
            "Surface": "Surface de jeu (Dur, Gazon, Terre battue)",
            "Mise": "Montant misé",
            "Cote": "Cote réelle du pari",
            "Prédiction": "Cote prédite par le modèle",
            "Gains net": "Gains ou pertes du pari",
            "Marge attendue": "Marge théorique du pari",
            "Cumulative Gains": "Gains cumulés",
        }

        for col in df.columns:
            if col in cols_info:
                st.write(f"- **{col}** : {cols_info[col]}")
            else:
                st.write(f"- **{col}**")

except Exception as e:
    st.error(f"❌ Erreur lors du chargement des données : {str(e)}")
    st.info("Veuillez réessayer ou contacter le support si le problème persiste.")
