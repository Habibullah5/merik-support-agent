"""Parse docs/merik-support-scenarios.md into data/*.json.

The pack is the single source of truth. Run this after the pack changes:
    python scripts/build_fixtures.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "docs" / "merik-support-scenarios.md"
DATA = ROOT / "data"


def _rows(section_text):
    rows = []
    for line in section_text.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)
    return rows[1:]  # drop header row


def _section(md, start, end=None):
    i = md.index(start)
    j = md.index(end, i + 1) if end else len(md)
    return md[i:j]


def main():
    md = PACK.read_text(encoding="utf-8")

    orders = {}
    for oid, customer, item, placed, status, total, notes in _rows(_section(md, "## 2. Orders", "## 3. Policies")):
        orders[oid] = {
            "id": oid, "customer": customer, "item": item, "placed": placed,
            "status": status, "total": total, "notes": notes,
        }

    policies = {}
    for m in re.finditer(r"\*\*(POL-\d+) · ([^*]+?)\.\*\* (.+)", _section(md, "## 3. Policies", "## 4. Scenarios")):
        pid, title, text = m.groups()
        policies[pid] = {"policy_id": pid, "title": title.strip(), "text": text.strip()}

    scenarios = []
    for num, sender, message, expect in _rows(_section(md, "## 4. Scenarios", "## 5.")):
        message = message.strip()
        if message.startswith("*(empty"):
            message = ""
        else:
            message = message.strip('"').strip("\u201c\u201d")
        scenarios.append({"id": int(num), "sender": sender, "message": message, "expect": expect})

    assert len(orders) == 8 and len(policies) == 6 and len(scenarios) == 20, (len(orders), len(policies), len(scenarios))
    for name, obj in (("orders", orders), ("policies", policies), ("scenarios", scenarios)):
        (DATA / f"{name}.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(orders)} orders, {len(policies)} policies, {len(scenarios)} scenarios")


if __name__ == "__main__":
    main()
