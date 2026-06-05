def generate_intelligence_report(domain, article):
    header = f"### TUNISIA/MULTILATERAL/{domain.upper()}: STRATEGIC DEVELOPMENTS IN {domain.upper()}"

    brief = (
        f"In June 2025, a regional workshop in Tunis convened experts to address shifts in the {domain.lower()} sector. "
        f"Hosted by the Arab Fertilizer Union and the Tunisian chemical complex, the event aimed to develop a strategic "
        f"roadmap to address global pressures including climate, food security, and resource efficiency.\n\n"
        f"From a {domain.lower()} standpoint, the roadmap outlines a structured adaptation framework targeting resilience, "
        f"coordination, and innovation. It serves as a blueprint for how Arab states plan to modernize systems under sectoral pressure."
    )

    analysis = (
        "## ANALYSIS\n"
        f"It is pertinent that this roadmap indicates a recalibration of regional {domain.lower()} policy in response to global system stress. "
        f"Historical dependency on conventional practices has created fragilities now exposed by overlapping crises. "
        f"This multilateral collaboration offers a template for sectoral transformation.\n\n"
        f"Hence, regional ministries must align policy instruments with strategic priorities identified in the roadmap. "
        f"International bodies and institutional partners should synchronize assistance efforts and infrastructure investment toward achieving the 2050 objectives. "
        f"The roadmap may define a new axis of global sectoral leadership if implemented efficiently."
    )

    return f"{header}\n\n{brief}\n\n{analysis}\n"