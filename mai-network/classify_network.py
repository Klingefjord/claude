#!/usr/bin/env python3
"""
Classify researchers in the MAI network by recommended engagement type.

Engagement types:
  1. Honorarium commission — postdocs, PhD students, institute/independent researchers
  2. Advisory — pre-tenure faculty, busy industry seniors (clearance limits)
  3. Buyout / sabbatical — tenured faculty only
  4. Embedded postdoc — grid-overlapping faculty willing to host
  5. Convene-only — very senior/peripheral figures, or low-fit
"""

import csv
import sys
from pathlib import Path

INDUSTRY_ORGS = {
    "deepmind", "meta", "openai", "anthropic", "cohere",
    "ae studio", "remesh", "cosmos institute",
    "the foundation for american innovation",
}

GOVT_OR_POLICY_ORGS = {
    "aria", "uk aisi", "govai",
    "oxford martin ai governance initiative",
    "ai and democracy foundation", "aoi", "cip",
}

# Researchers known to hold tenured/senior professor positions
KNOWN_TENURED = {
    "ruth chang", "vince conitzer", "gillian hadfield", "jakob foerster",
    "dylan hadfield-menell", "chris summerfield", "david duvenaud",
    "ariel procaccia", "joelle pineau", "seth lazar", "glen weyl",
    "edith elkind", "wes holliday", "allan dafoe", "david krueger",
    "marcus pivato", "georgios piliouras", "brad knox", "noam kolt",
    "martin wahlisch", "harvey lederman",
}

# Researchers known to be pre-tenure / assistant professor
KNOWN_PRE_TENURE = {
    "atoosa kasirzadeh", "atrisha sarkar", "serena booth",
    "sydney levine", "michiel bakker", "jobst heitzig",
    "david storrs-fox", "james ravi kirkpatrick", "philipp koralus",
}

# Internal team — skip classification
INTERNAL = {"oliver klingefjord", "ryan lowe", "joe edelman"}

# People known to be PhD students or postdocs based on context
KNOWN_POSTDOC_OR_PHD = {
    "tianyi qiu", "rachel calcott", "zhonghao he", "ryan kearns",
    "liam patell", "adam morris", "nick caputo", "andrew koh",
    "matija franklin", "fazl barez", "benjamin lang", "samuele marro",
    "sean moss", "vincent wang-mascianica", "bryce goodman",
    "andreas haupt", "sonja kraiczy", "logan walls", "joseph gubbels",
    "max kroner dale", "paul de font-reaulx", "daniel kilov",
    "roberto rafael maura rivero", "taylor sorensen",
}


def normalize(s: str) -> str:
    return s.strip().lower() if s else ""


def parse_excitement(val: str) -> int:
    if not val:
        return 0
    return val.count("🔥")


def is_industry(orgs_raw: str) -> bool:
    if not orgs_raw:
        return False
    orgs_lower = orgs_raw.lower()
    return any(ind in orgs_lower for ind in INDUSTRY_ORGS)


def is_university(orgs_raw: str) -> bool:
    if not orgs_raw:
        return False
    orgs_lower = orgs_raw.lower()
    uni_keywords = ["university", "mit", "cmu", "harvard", "princeton",
                    "yale", "stanford", "berkeley", "nyu", "brown",
                    "mcgill", "mila", "northwestern", "johns hopkins",
                    "hebrew university", "ghent university",
                    "ut austin", "panthéon-sorbonne", "alan turing"]
    return any(kw in orgs_lower for kw in uni_keywords)


def has_professor_role(role: str) -> bool:
    return "professor" in role.lower() if role else False


def has_executive_role(role: str) -> bool:
    return "executive" in role.lower() if role else False


def classify(row: dict) -> tuple[str, str, str]:
    """Returns (engagement_type, position_class, confidence)."""
    name = normalize(row.get("Name", ""))
    role = row.get("Role", "") or ""
    orgs = row.get("Org(s)", "") or ""
    excitement = parse_excitement(row.get("Our excitement level", ""))

    if name in INTERNAL:
        return "internal", "internal", "high"

    if not name:
        return "convene-only", "unknown", "low"

    # Position classification
    position_class = "unknown"
    if name in KNOWN_TENURED:
        position_class = "tenured-faculty"
    elif name in KNOWN_PRE_TENURE:
        position_class = "pre-tenure-faculty"
    elif name in KNOWN_POSTDOC_OR_PHD:
        position_class = "postdoc-or-phd"
    elif has_professor_role(role) and is_industry(orgs):
        position_class = "dual-industry-faculty"
    elif has_professor_role(role):
        position_class = "faculty-unknown-tenure"
    elif is_industry(orgs):
        position_class = "industry"
    elif orgs and any(g in orgs.lower() for g in ["govai", "aria", "aisi", "aoi", "cip"]):
        position_class = "policy-org"
    elif is_university(orgs):
        position_class = "university-researcher"
    elif not orgs:
        position_class = "independent-or-unknown"

    # Engagement classification
    engagement = classify_engagement(name, position_class, role, orgs, excitement)

    # Confidence
    confidence = "high"
    if position_class in ("unknown", "independent-or-unknown", "faculty-unknown-tenure"):
        confidence = "medium"
    if not orgs and not has_professor_role(role):
        confidence = "low"

    return engagement, position_class, confidence


def classify_engagement(name, position_class, role, orgs, excitement):
    # Tenured faculty → buyout/sabbatical if high excitement, else advisory
    if position_class == "tenured-faculty":
        if excitement >= 3:
            return "buyout-or-sabbatical"
        elif excitement >= 2:
            return "embedded-postdoc"
        else:
            return "advisory"

    # Pre-tenure faculty → advisory (career risk to do more)
    if position_class == "pre-tenure-faculty":
        return "advisory"

    # Dual industry+faculty → advisory (clearance + career complexity)
    if position_class == "dual-industry-faculty":
        return "advisory"

    # Faculty with unknown tenure status — guess based on excitement
    if position_class == "faculty-unknown-tenure":
        if excitement >= 3:
            return "buyout-or-sabbatical"
        else:
            return "advisory"

    # Industry researchers → advisory (clearance limits)
    if position_class == "industry":
        if excitement == 0 and not role:
            return "convene-only"
        return "advisory"

    # Postdocs, PhD students, institute researchers → honorarium commission
    if position_class in ("postdoc-or-phd", "university-researcher"):
        if excitement == 0:
            return "convene-only"
        return "honorarium-commission"

    # Policy org researchers
    if position_class == "policy-org":
        if excitement >= 2:
            return "honorarium-commission"
        return "advisory"

    # Executives → advisory or convene-only
    if has_executive_role(role):
        if excitement >= 2:
            return "advisory"
        return "convene-only"

    # Independent/unknown with excitement → honorarium if they seem engageable
    if excitement >= 2:
        return "honorarium-commission"
    elif excitement >= 1:
        return "advisory"

    return "convene-only"


def main():
    input_path = Path(__file__).parent / "The_Network.csv"
    output_path = Path(__file__).parent / "The_Network_Classified.csv"

    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_path = Path(sys.argv[2])

    with open(input_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames + ["Engagement Type", "Position Class", "Confidence"]
        rows = []
        for row in reader:
            engagement, position_class, confidence = classify(row)
            row["Engagement Type"] = engagement
            row["Position Class"] = position_class
            row["Confidence"] = confidence
            rows.append(row)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Print summary
    from collections import Counter
    eng_counts = Counter(r["Engagement Type"] for r in rows)
    pos_counts = Counter(r["Position Class"] for r in rows)
    conf_counts = Counter(r["Confidence"] for r in rows)

    print(f"\n{'='*60}")
    print(f"Classified {len(rows)} researchers → {output_path.name}")
    print(f"{'='*60}")

    print(f"\n--- Engagement Type Distribution ---")
    for eng, count in eng_counts.most_common():
        print(f"  {eng:<25} {count:>3}")

    print(f"\n--- Position Class Distribution ---")
    for pos, count in pos_counts.most_common():
        print(f"  {pos:<25} {count:>3}")

    print(f"\n--- Confidence Distribution ---")
    for conf, count in conf_counts.most_common():
        print(f"  {conf:<10} {count:>3}")

    # Flag high-excitement people landing in advisory
    print(f"\n--- Flag: High-excitement researchers in advisory/convene-only ---")
    flagged = [r for r in rows if parse_excitement(r.get("Our excitement level", "")) >= 3
               and r["Engagement Type"] in ("advisory", "convene-only")]
    if flagged:
        for r in flagged:
            print(f"  {r['Name']:<30} {r['Engagement Type']:<20} ({r['Position Class']})")
    else:
        print("  None")

    print()


if __name__ == "__main__":
    main()
