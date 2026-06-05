import argparse
from language_agent import check_language, translate_to_english
from relevance_agent import determine_relevant_domains
from intelligence_agents import generate_intelligence_report

def main():
    parser = argparse.ArgumentParser(description="Intelligence Article Analyzer")
    parser.add_argument("file", help="Path to the article text file")
    args = parser.parse_args()

    with open(args.file, 'r', encoding='utf-8') as f:
        article = f.read()

    lang = check_language(article)
    if lang != 'en':
        print(f"[INFO] Detected language: {lang}. Translating to English...")
        article = translate_to_english(article)
    else:
        print("[INFO] Article already in English.")

    domains = determine_relevant_domains(article)
    if not domains:
        print("[INFO] No relevant domains found.")
        return

    print(f"[INFO] Relevant domains: {', '.join(domains)}")
    for domain in domains:
        report = generate_intelligence_report(domain, article)
        print("\n" + "="*100 + "\n")
        print(report)

if __name__ == "__main__":
    main()