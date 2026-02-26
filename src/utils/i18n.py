# utils/i18n.py

from deep_translator import GoogleTranslator
import streamlit as st

@st.cache_data(show_spinner=False)
def translate_text(text: str, target_lang: str) -> str:
    """
    Traduce una singola stringa.
    - Se target_lang == 'en' → ritorna testo originale
    - Cache automatica Streamlit
    """
    if not text or target_lang == "en":
        return text

    try:
        return GoogleTranslator(
            source="auto",
            target=target_lang
        ).translate(text)
    except Exception:
        return text
