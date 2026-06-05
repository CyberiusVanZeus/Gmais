from openai import OpenAI
import os
import re
from dotenv import load_dotenv

load_dotenv()

# Do NOT pass any proxies or extra arguments
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def ask_openai(prompt, model="gpt-4o-mini", temperature=0.5):
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a Master National Security Intelligence Analyst Agent.\n"
                    "Your job is to extract, filter, and rewrite articles based on intelligence relevance.\n"
                    "You must detect relevant domains, and only for each relevant domain, output an intelligence brief following the specified structure."
                )
            },
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()


def build_full_prompt(article_text):
    return f"""
MASTER NATIONAL SECURITY INTELLIGENCE AGENT TASKING PROTOCOL

ARTICLE SOURCE (FOR EVALUATION):
--------------------
{article_text}
--------------------

INSTRUCTION SET:

PART 1: LANGUAGE DETECTION & TRANSLATION
Check whether the article is in English. If not, translate it into fluent English internally. Do not output this step.

PART 2: DOMAIN RELEVANCE IDENTIFICATION
Use the following 32 intelligence domains to determine relevance. From the identified relevant domains, select up to 5 that are the most critical to national security, geopolitical stability, or institutional response needs. Choose only those where the content presents a direct, actionable, or contextual implication. Do not output this step. Use this internal relevance map to guide Part 3 generation.
Select UP TO 5 most relevant domains ONLY. If fewer than 5 are highly relevant, use fewer.

INTELLIGENCE DOMAINS:
1. Political, 2. Security, 3. Economy, 4. Environment, 5. Health, 6. Technology, 7. Innovation,
8. Trafficking, 9. Agriculture, 10. Medical, 11. Terrorism, 12. Diplomacy, 13. Treaties, 14. Agreements,
15. Education, 16. Energy, 17. Science, 18. Espionage, 19. Subversion, 20. Psychological Operations,
21. United Nations, 22. ECOWAS, 23. AES, 24. Intelligence, 25. Propaganda, 26. Finance,
27. African Union, 28. Gulf of Guinea, 29. Piracy, 30. Food and Drugs, 31. Defense, 32. Migration, 

PART 3: INTELLIGENCE REPORT GENERATION (FOR EACH RELEVANT DOMAIN ONLY)

BRIEF TYPE:
If one country is mentioned, the brief type is internal.
If two countries are mentioned, the brief type is bilateral.
If more than two countries or multilateral orgs are mentioned, the brief type is multilateral.

COUNTRY:
If one country or place is mentioned in the {article_text}, use the country where that place is located and append the country name e.g. IRAN.
If two countries are mentioned in the {article_text}, append the two names of the countries e.g. IRAN/ISRAEL.
if it is morethan two countries in the {article_text}, append the names of the countries e.g. IRAN/ISRAEL/US...
Else, if it is morethan two countries in the {article_text} and involve a multerlateral organizations, append the name of the organization e.g. UN.


HEADLINE:
Generate an alarming headline reflecting national security relevance.


== FORMAT PER DOMAIN ==

## COUNTRY/BRIEF TYPE/INTELLIGENCE DOMAIN: HEADLINE

[Two-paragraph rewritten intelligence brief: 
- Paragraph 1: Must answer When, Who, Where and What.
- Paragraph 2: How.]
[Word Repetition: 
- The: Must NOT use morethan two to start a sentence.
- Exagerations: Must NOT exagerate or emphasize the event.]

## ANALYSIS

[Two-paragraph analysis:
- Paragraph 1: Open with the perfect primer and Connects event to past developments/systemic trends. Discuss Why the event happpened drawing an domain expert opinion on the main cause and highlight the role played by individuals/states/organizations in the cause of event. Acknowledge the arguments revelations both for and against the matter and use it without mentioning names to further justify and buttress the cause analysis.
- Paragraph 2: Outlines country/regional bodies (with names)/global impact informing on the risks as it affects the country, or opportunities presented by the event justified with expert and institutional recommendations for the specific MDAs (Ministries, Departments, Agencies) names that has the mandate to act upon. Use conjuction like "Therefore" initiate the call-to-action.]
[Word Repetition: 
- The: Must NOT use morethan two to start a sentence.
- Exagerations: Must NOT exagerate or emphasize the event.]
== END FORMAT ==

MANDATORY OUTPUT RULES:
- Output ONLY Part 3
- Each domain’s brief must be separate and complete
- Headline MUST all be BLOCK LETTERS
- Write like a human analyst.
- DO write the intelligence brief as if you owned the report.
- Maintain fluency, neutrality, and analytical structure
- Do NOT use "Historically" to start the analysis.
- Do NOT fabricate or speculate beyond article content.
- Do NOT use “The” more than two times to start sentences or paragraphs.
- Use strong transition phrases: “Therefore” or “Consequently” relevant MDAs such as the names, to instigate recommendations where appropriate.
- Use references like “It can be recalled” and “It is pertinent” when referring to history and importance, respectively.
- Use "Hence" or "Thus" to start the country/regional/global impplications, respectively.
- For each domain, repeat the full brief and analysis structure independently.
BEGIN NOW.
"""



def parse_multiple_outputs(response_text):
    pattern = r"##\s*([A-Z\/]+:.*?)\n+(.*?)(?=\n##\s*ANALYSIS\s*\n+|$)"  # Extract brief blocks
    analysis_pattern = r"##\s*ANALYSIS\s*\n+(.*?)(?=\n##\s|$)"  # Extract analysis blocks

    headlines_briefs = re.findall(pattern, response_text, re.DOTALL)
    analyses = re.findall(analysis_pattern, response_text, re.DOTALL)

    if not headlines_briefs or not analyses or len(headlines_briefs) != len(analyses):
        raise ValueError("Mismatch in extracted briefs and analyses. Please check output formatting.")

    output = []
    for (headline, brief), analysis in zip(headlines_briefs, analyses):
        output.append({
            "headline": headline.strip(),
            "brief": brief.strip(),
            "analysis": analysis.strip()
        })

    return output