from langdetect import detect
from deep_translator import GoogleTranslator

def check_language(article_text):
    try:
        lang = detect(article_text)
        return lang
    except Exception:
        return "unknown"

def translate_to_english(article_text):
    return GoogleTranslator(source='auto', target='en').translate(article_text)