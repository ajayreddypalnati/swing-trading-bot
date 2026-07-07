import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
            
            /* GLOBAL AESTHETICS */
            html { zoom: 1; } 
            html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
            #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
            div[data-testid="stStatusWidget"] { visibility: hidden; }
            .stApp { background-color: #F4F1E1 !important; }
            h1, h2, h3, h4, h5, h6, p, span { color: #0B1D30; }
            
            /* EXTREME COMPACT MODE (Reduced Whitespace) */
            .block-container { 
                padding-top: 1.5rem !important; 
                padding-bottom: 0rem !important; 
                max-width: 98% !important; 
                gap: 0.5rem !important;
            }
            
            /* ABSOLUTE POSITION NATIVE TOGGLE INSIDE PREMIUM HEADER */
            div[data-testid="stToggle"] {
                position: absolute;
                top: 40px;
                right: 220px;
                z-index: 10;
                background: rgba(255, 255, 255, 0.95);
                padding: 4px 12px;
                border-radius: 8px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.1);
                border: 1px solid rgba(11,29,48,0.1);
            }
            @media (max-width: 768px) {
                div[data-testid="stToggle"] { top: 15px; right: 15px; }
            }

            /* PREMIUM CUSTOM HEADER */
            .premium-header {
                background: linear-gradient(135deg, #0B1D30 0%, #162C46 100%); 
                border-radius: 12px;
                padding: 20px 30px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: relative;
                overflow: hidden;
                margin-bottom: 15px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                box-shadow: 0 8px 20px rgba(11, 29, 48, 0.2);
            }
            .premium-header::after {
                content: ''; position: absolute; top: -50px; right: -50px; width: 350px; height: 200%;
                background: #F4F1E1; transform: rotate(20deg); z-index: 1;
                box-shadow: -15px 0 35px rgba(0,0,0,0.4); border-left: 2px solid rgba(255, 255, 255, 0.4);
            }
            .header-left { position: relative; z-index: 2; }
            .header-title { color: #FFFFFF !important; margin: 0; font-size: 1.8rem; font-weight: 800; letter-spacing: -0.5px;}
            .header-subtitle { color: #FFFFFF !important; margin: 2px 0 0 0; font-size: 0.9rem; opacity: 0.9; }
            .header-right { position: relative; z-index: 2; text-align: right; padding-right: 10px;}
            .header-right .live-status { font-size: 0.75rem; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: #0B1D30;}
            .header-right .time { font-size: 1.4rem; font-weight: 800; margin: 0; color: #0B1D30; line-height: 1.2;}
            .header-right .date { font-size: 0.85rem; font-weight: 600; color: #3A4A5A;}
            
            /* ANIMATIONS */
            @keyframes pulse-green {
                0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(39, 174, 96, 0.7); }
                70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(39, 174, 96, 0); }
                100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(39, 174, 96, 0); }
            }
            @keyframes pulse-logo {
                0% { transform: scale(1); opacity: 0.6; }
                50% { transform: scale(1.3); opacity: 1; text-shadow: 0 0 20px #FFD700; }
                100% { transform: scale(1); opacity: 0.6; }
            }
            .blob.green { background: rgba(39, 174, 96, 1); border-radius: 50%; margin: 0 0 0 5px; height: 10px; width: 10px; animation: pulse-green 2s infinite; display: inline-block; }

            /* SAAS NAVIGATION TABS - COMPACT */
            div[data-baseweb="tab-list"] { 
                display: flex !important; width: 100% !important; gap: 10px !important; margin-bottom: 15px !important; border-bottom: none !important; padding-top: 5px !important;
            }
            div[data-baseweb="tab"] { flex: 1 !important; padding: 0 !important; background: transparent !important; }
            button[role="tab"] {
                width: 100% !important; background: linear-gradient(135deg, #0B1D30 0%, #162C46 100%) !important;
                border-radius: 8px !important; padding: 12px 5px !important; border: 1px solid rgba(255, 255, 255, 0.1) !important;
                box-shadow: 0 4px 10px rgba(11, 29, 48, 0.15) !important; transform: translateY(0) !important; transition: all 0.2s !important;
            }
            button[role="tab"]:hover { transform: translateY(-3px) !important; background: linear-gradient(135deg, #0f2640 0%, #1d3a5a 100%) !important; }
            button[role="tab"][aria-selected="true"] {
                background: #FFFFFF !important; border: 1px solid #0B1D30 !important; border-top: 5px solid #0B1D30 !important; transform: translateY(-3px) !important; box-shadow: 0 8px 15px rgba(11, 29, 48, 0.1) !important;
            }
            button[role="tab"] p { font-size: 1.15rem !important; font-weight: 800 !important; color: #FFFFFF !important; margin: 0 !important; white-space: nowrap !important; }
            button[role="tab"][aria-selected="true"] p { color: #0B1D30 !important; }
            div[data-baseweb="tab-highlight"] { display: none !important; }

            /* TABLES (Sleek & Compact) */
            .scrollable-table-container { width: 100%; margin-bottom: 0.5rem; overflow-x: auto; border-radius: 8px; border: 1px solid #0B1D30; background: #FFFFFF;}
            .scrollable-table-container table { width: 100%; border-collapse: collapse; background: #FFFFFF; overflow: hidden; font-size: 0.9rem !important;}
            .scrollable-table-container th { background-color: #0B1D30 !important; color: #F4F1E1 !important; text-align: center !important; vertical-align: middle !important; padding: 8px 4px !important; font-weight: 700 !important;}
            .scrollable-table-container td { color: #111827 !important; text-align: center !important; vertical-align: middle !important; padding: 6px 4px !important; border-bottom: 1px solid rgba(11, 29, 48, 0.05) !important; }
            
            .sleek-table-wrapper { width: 100%; border: 1px solid #0B1D30; border-radius: 8px; overflow-x: auto; background: #FFFFFF; }
            .sleek-table { width: 100%; border-collapse: collapse; font-size: 0.9rem !important; }
            .sleek-table th { background-color: #0B1D30 !important; color: #F4F1E1 !important; text-align: center; padding: 8px 4px; font-weight: 700 !important; }
            .sleek-table td { color: #111827 !important; text-align: center; padding: 6px 4px; border-bottom: 1px solid rgba(11, 29, 48, 0.05); }

            /* FORMS & WIDGETS COMPACT MODE */
            div[data-testid="stSelectbox"] > div { min-height: 2.2rem !important; border-radius: 6px !important; }
            div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input {
                background-color: #FFFFFF !important; color: #0B1D30 !important; border: 1px solid #0B1D30 !important; padding: 0.4rem !important; font-size: 0.95rem !important;
            }
            div[data-testid="stButton"] button {
                background-color: #FFFFFF !important; color: #0B1D30 !important; border: 2px solid #0B1D30 !important; border-radius: 6px !important; font-weight: 700 !important; padding: 0.25rem 0.5rem !important; height: auto !important; min-height: 38px !important;
            }
            div[data-testid="stButton"] button:hover { background-color: #F4F1E1 !important; }
            div[role="radiogroup"] label { color: #0B1D30 !important; font-size: 0.9rem !important; }
            
            /* FILE UPLOAD COMPACT */
            div[data-testid="stFileUploader"] { background-color: #FFFFFF !important; border: 1px dashed #0B1D30 !important; border-radius: 6px !important; padding: 10px !important; }
            div[data-testid="stFileUploader"] span { font-weight: 600 !important; }

            /* GRAPHS */
            div.stPlotlyChart { background-color: #FFFFFF !important; border: 1px solid #0B1D30 !important; border-radius: 8px !important; box-shadow: 0 4px 10px rgba(11, 29, 48, 0.05) !important; padding: 10px !important; }
            @media (max-width: 768px) { div.stPlotlyChart svg text { font-size: 10px !important; } div.stPlotlyChart svg g.textpoint { transform: translateY(-15px); } }
        </style>
    """, unsafe_allow_html=True)
