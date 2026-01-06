import streamlit as st

def apply_custom_style():
    """Aplica o estilo customizado azul escuro ao Streamlit"""
    
    st.markdown("""
    <style>
    /* Configurações gerais */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* Cores do tema */
    :root {
        --primary-color: #002B5B;
        --secondary-color: #004A8D;
        --accent-color: #EAF0F6;
        --background-color: #F8FAFC;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background-color: #002B5B;
    }
    
    .css-1d391kg .css-17eq0hr {
        color: #EAF0F6;
    }
    
    /* Botões */
    .stButton > button {
        background-color: #004A8D;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background-color: #003A7A;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0, 43, 91, 0.3);
    }
    
    /* Inputs */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div > select {
        border: 2px solid #EAF0F6;
        border-radius: 8px;
        padding: 0.5rem;
    }
    
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus,
    .stSelectbox > div > div > select:focus {
        border-color: #004A8D;
        box-shadow: 0 0 0 3px rgba(0, 74, 141, 0.1);
    }
    
    /* Cards e containers */
    .metric-card {
        background-color: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0, 43, 91, 0.1);
        border-left: 4px solid #004A8D;
        margin-bottom: 1rem;
    }
    
    /* Tabelas */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0, 43, 91, 0.1);
    }
    
    /* Alertas */
    .stAlert {
        border-radius: 8px;
        border-left: 4px solid;
    }
    
    /* Expanders */
    .streamlit-expanderHeader {
        background-color: #EAF0F6;
        border-radius: 8px 8px 0 0;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: #EAF0F6;
        border-radius: 8px 8px 0 0;
        color: #002B5B;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #004A8D;
        color: white;
    }
    
    /* Custom classes */
    .header-title {
        color: #002B5B;
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        margin-bottom: 1rem;
    }
    
    .subtitle {
        color: #004A8D;
        font-size: 1.2rem;
        text-align: center;
        margin-bottom: 2rem;
    }
    
    .section-title {
        color: #002B5B;
        font-size: 1.5rem;
        font-weight: bold;
        margin-top: 2rem;
        margin-bottom: 1rem;
        border-bottom: 2px solid #EAF0F6;
        padding-bottom: 0.5rem;
    }
    
    .info-box {
        background-color: #EAF0F6;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #004A8D;
        margin: 1rem 0;
    }
    
    .success-box {
        background-color: #E8F5E8;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #28A745;
        margin: 1rem 0;
    }
    
    .error-box {
        background-color: #FFE8E8;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #DC3545;
        margin: 1rem 0;
    }
    
    /* Responsividade */
    @media (max-width: 768px) {
        .header-title {
            font-size: 2rem;
        }
        
        .subtitle {
            font-size: 1rem;
        }
        
        .section-title {
            font-size: 1.3rem;
        }
    }
    </style>
    """, unsafe_allow_html=True)
