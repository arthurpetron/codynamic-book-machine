# scripts/outline_agent.py

import yaml
from pathlib import Path
from datetime import datetime

OUTLINE_PATH = Path("book_data/codynamic_theory_book/outline/codynamic_theory.yaml")
LOG_PATH = Path("book_data/codynamic_theory_book/logs/outline_agent_log.txt")
PROPOSAL_PATH = Path("book_data/codynamic_theory_book/proposals/outline_proposal.yaml")

REQUIRED_KEYS = ["title", "summary", "intent", "chapters"]
REQUIRED_INTENT_KEYS = ["audience", "writing_style", "author_persona", "reader_takeaway", "genre"]
REQUIRED_CHAPTER_KEYS = ["id", "title", "goal", "summary", "sections"]
REQUIRED_SECTION_KEYS = ["id", "title", "content_summary"]


def load_outline():
    with open(OUTLINE_PATH, "r") as f:
        return yaml.safe_load(f)["outline"]


def check_outline_keys(outline):
    log = []
    for key in REQUIRED_KEYS:
        if key not in outline:
            log.append(f"Missing top-level key: {key}")

    for ikey in REQUIRED_INTENT_KEYS:
        if ikey not in outline.get("intent", {}):
            log.append(f"Missing intent key: {ikey}")

    for chapter in outline.get("chapters", []):
        for ckey in REQUIRED_CHAPTER_KEYS:
            if ckey not in chapter:
                log.append(f"Chapter {chapter.get('id', '[unknown]')} missing key: {ckey}")
        for section in chapter.get("sections", []):
            for skey in REQUIRED_SECTION_KEYS:
                if skey not in section:
                    log.append(f"Section {section.get('id', '[unknown]')} missing key: {skey}")

    return log


def propose_outline_edits(outline):
    """
    This is a stub function simulating an LLM-based analysis of the current outline,
    returning proposed edits or additions to improve structure or flow.
    """
    title = outline.get("title", "Untitled")
    summary = outline.get("summary", "")
    intent = outline.get("intent", {})

    existing_ids = [ch["id"] for ch in outline.get("chapters", [])]
    proposal = {
        "proposed_additions": [
            {
                "id": "ch99",
                "title": "Conclusion: Codynamic Futures",
                "goal": "Synthesize key themes and suggest next research paths",
                "summary": "Wraps up the ideas and proposes practical applications.",
                "sections": [
                    {
                        "id": "ch99_sec01",
                        "title": "Final Synthesis",
                        "content_summary": "A final integration of codynamic principles."
                    },
                    {
                        "id": "ch99_sec02",
                        "title": "Looking Ahead",
                        "content_summary": "Challenges, opportunities, and open questions."
                    }
                ]
            }
        ],
        "mid_document_insert": {
            "insert_after": "ch01",
            "proposal": {
                "id": "ch01b",
                "title": "Embodied Interactions",
                "goal": "Bridge theory of codynamic recursion to embodied systems",
                "summary": "This chapter introduces how structural learning manifests in real environments.",
                "sections": [
                    {
                        "id": "ch01b_sec01",
                        "title": "Agents in Context",
                        "content_summary": "An overview of agency within mutable environments."
                    },
                    {
                        "id": "ch01b_sec02",
                        "title": "Structural Modulation",
                        "content_summary": "How codynamic systems shape and are shaped by embodiment."
                    }
                ]
            }
        }
    }
    return proposal


def write_log(log_messages):
    with open(LOG_PATH, "a") as f:
        f.write(f"\n[Outline Agent Run: {datetime.now().isoformat()}]\n")
        for line in log_messages:
            f.write(f"{line}\n")


def write_proposal(proposal):
    PROPOSAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROPOSAL_PATH, "w") as f:
        yaml.dump(proposal, f)
    print(f"[Outline Agent] Wrote proposal to: {PROPOSAL_PATH}")


def run_outline_agent():
    outline = load_outline()
    messages = check_outline_keys(outline)
    if messages:
        print("[Outline Agent] Issues found:")
        for m in messages:
            print(f"- {m}")
        write_log(messages)
    else:
        print("[Outline Agent] Outline structure is valid.")

    proposal = propose_outline_edits(outline)
    write_proposal(proposal)


if __name__ == "__main__":
    run_outline_agent()