import re

DOMAINS = {
    1: "Political", 2: "Security and Defense", 3: "Economy", 4: "Environment", 5: "Health",
    6: "Technology", 7: "Innovation", 8: "Trafficking", 9: "Agriculture", 10: "Medical",
    11: "Terrorism", 12: "Diplomacy", 13: "Treaties", 14: "Agreements", 15: "Education",
    16: "Energy", 17: "Science", 18: "Espionage", 19: "Subversion", 20: "Psychological Operations",
    21: "United Nations", 22: "ECOWAS", 23: "Sahel", 24: "Military Intelligence", 25: "Propaganda",
    26: "Finance", 27: "African Union", 28: "Gulf of Guinea", 29: "Piracy", 30: "Food and Drugs"
}

def determine_relevant_domains(article_text):
    relevant_domains = []

    if re.search(r'\bfertilizer\b|\bagriculture\b|\bcrop\b', article_text, re.IGNORECASE):
        relevant_domains.append(9)
    if re.search(r'\bclimate\b|\benvironment\b|\bgreen\b', article_text, re.IGNORECASE):
        relevant_domains.append(4)
    if re.search(r'\benergy\b|\bfuel\b|\bpower\b', article_text, re.IGNORECASE):
        relevant_domains.append(16)
    if re.search(r'\bfood security\b|\bhunger\b', article_text, re.IGNORECASE):
        relevant_domains.append(30)
    if re.search(r'\btechnology\b|\binnovation\b|\bdigital\b', article_text, re.IGNORECASE):
        relevant_domains.append(6)

    return [DOMAINS[i] for i in relevant_domains]