#!/usr/bin/env python3
"""Merge supplied FEC Form 3 reports into the general-election dataset."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import fitz


AMOUNT_RE = re.compile(r"^-?\(?\$?([\d,]+\.\d{2})\)?$")


def amount(value: str) -> float | None:
    match = AMOUNT_RE.match(value.strip())
    if not match:
        return None
    result = float(match.group(1).replace(",", ""))
    return -result if value.strip().startswith(("-", "(")) else result


def words_in(words, x0, y0, x1, y1):
    return [w for w in words if x0 <= w[0] and y0 <= w[1] and w[2] <= x1 and w[3] <= y1]


def numeric_near(words, x0, x1, target_y, tolerance=15):
    values = []
    for word in words:
        if x0 <= word[0] <= x1 and abs(word[1] - target_y) <= tolerance:
            parsed = amount(word[4])
            if parsed is not None:
                values.append((abs(word[1] - target_y), parsed))
    if not values:
        raise ValueError(f"No amount near y={target_y}")
    return min(values)[1]


def summary(pdf: Path) -> dict:
    doc = fitz.open(pdf)
    p2 = doc[1].get_text("words")
    p3 = doc[2].get_text("words")
    result = {
        "contributions": numeric_near(p2, 330, 390, 223, 18),
        "expenditures": numeric_near(p2, 330, 390, 354, 18),
        "endingBalance": numeric_near(p2, 330, 390, 463, 18),
        "candidateLoans": numeric_near(p3, 330, 390, 493, 20),
        "unitemized": numeric_near(p3, 330, 390, 275, 18),
    }
    doc.close()
    return result


def checked_memo(page, transaction_y: float) -> bool:
    clip = fitz.Rect(405, transaction_y + 68, 419, transaction_y + 86)
    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), colorspace=fitz.csGRAY, clip=clip, alpha=False)
    return sum(pixel < 100 for pixel in pix.samples) > 5


def schedule_a_category(page) -> str:
    boxes = {
        "11a": (402, 59), "11b": (438, 59), "11c": (475, 59), "11d": (511, 59),
        "12": (402, 75), "13a": (438, 75), "13b": (475, 75), "14": (511, 75), "15": (547, 75),
    }
    scores = {}
    for label, (x, y) in boxes.items():
        pix = page.get_pixmap(
            matrix=fitz.Matrix(3, 3), colorspace=fitz.csGRAY,
            clip=fitz.Rect(x, y, x + 14, y + 14), alpha=False,
        )
        scores[label] = sum(pixel < 100 for pixel in pix.samples)
    return max(scores, key=scores.get)


def display_name(raw: str) -> str:
    raw = re.sub(r"\s+", " ", raw.replace(" ,", ",")).strip(" ,")
    parts = [part.strip(" ,") for part in raw.split(",") if part.strip(" ,")]
    if len(parts) >= 2:
        raw = " ".join(parts[1:] + parts[:1])
    if raw.isupper():
        raw = raw.title()
        for token in ("Pac", "Us", "Usa", "Llc", "Llp"):
            raw = re.sub(rf"\b{token}\b", token.upper(), raw)
    return raw


def receipts(pdf: Path) -> list[dict]:
    doc = fitz.open(pdf)
    rows = []
    for page in doc:
        text = page.get_text()
        if "SCHEDULE A" not in text or "ITEMIZED RECEIPTS" not in text:
            continue
        if schedule_a_category(page) not in {"11a", "11b", "11c", "11d"}:
            continue
        words = page.get_text("words")
        transaction_words = [
            w for w in words
            if 450 <= w[0] <= 570
            and 180 <= w[1] <= 590
            and re.fullmatch(r"(?:SA11[ABCD][A-Z0-9.]*|\d{7,})", w[4], re.I)
        ]
        for transaction in transaction_words:
            transaction_y = transaction[1]
            if checked_memo(page, transaction_y):
                continue
            name_words = words_in(words, 45, transaction_y - 46, 390, transaction_y - 24)
            city_words = words_in(words, 45, transaction_y + 3, 230, transaction_y + 22)
            state_words = words_in(words, 230, transaction_y + 3, 280, transaction_y + 22)
            date_words = words_in(words, 395, transaction_y - 25, 570, transaction_y)
            amount_words = words_in(words, 480, transaction_y + 38, 570, transaction_y + 66)
            receipt_amounts = [(w[0], amount(w[4])) for w in amount_words if amount(w[4]) is not None]
            if not name_words or not receipt_amounts:
                continue
            date_values = [w[4] for w in sorted(date_words, key=lambda w: w[0]) if w[4].isdigit()]
            date = "/".join(date_values[:3]) if len(date_values) >= 3 else ""
            name = display_name(" ".join(w[4] for w in sorted(name_words, key=lambda w: w[0])))
            city = " ".join(w[4] for w in sorted(city_words, key=lambda w: w[0])).title()
            state = " ".join(w[4] for w in sorted(state_words, key=lambda w: w[0])).upper()
            receipt_amount = max(receipt_amounts, key=lambda pair: pair[0])[1]
            if any(w[4] in {"-", "–", "−"} for w in amount_words):
                receipt_amount = -abs(receipt_amount)
            rows.append({
                "date": date,
                "name": name,
                "address": ", ".join(value for value in (city, state) if value),
                "aggregate": receipt_amount,
                "amount": receipt_amount,
                "source": "Federal Election Commission",
            })
    doc.close()
    return rows


REPORTS = {
    "us-house-sarah-mcbride": {
        "committee": "McBride for Delaware Inc.",
        "account": "FEC C00843763",
        "files": [
            ("McBride April 2025.pdf", "01/01/2025", "03/31/2025"),
            ("McBride July 2025.pdf", "04/01/2025", "06/30/2025"),
            ("McBride Oct 2025.pdf", "07/01/2025", "09/30/2025"),
            ("McBride 2025.pdf", "10/01/2025", "12/31/2025"),
            ("McBride April 2026.pdf", "01/01/2026", "03/31/2026"),
            ("McBride July 2026.pdf", "04/01/2026", "06/30/2026"),
            ("McBride Aug 2026.pdf", "07/01/2026", "08/26/2026"),
            ("McBride Oct 2026.pdf", "08/27/2026", "09/30/2026"),
        ],
        "updateFiles": [
            ("202610229940946553.pdf", "10/01/2026", "10/14/2026"),
        ],
        "notices": [
            {"sourceFile": "202610249945201340.pdf", "date": "10/22/2026", "name": "American Association of Nurse Anesthetists Separate Segregated Fund (CRNA-PAC)", "address": "Rosemont, IL", "amount": 2500.00},
            {"sourceFile": "202610249945201340.pdf", "date": "10/22/2026", "name": "The Chemours PAC", "address": "Washington, DC", "amount": 2500.00},
            {"sourceFile": "202610259945203131.pdf", "date": "10/23/2026", "name": "Friends For Hansen", "address": "Middletown, DE", "amount": 1200.00},
        ],
    },
    "us-house-joseph-dr-joe-arminio": {
        "committee": "Citizens for Joe Arminio",
        "account": "FEC C00957365",
        "files": [
            ("Arminio July 2026.pdf", "07/01/2026", "08/26/2026"),
            ("Arminio Oct 2026.pdf", "08/27/2026", "09/30/2026"),
        ],
    },
    "us-sen-michael-dr-mike-katz": {
        "committee": "Dr. Mike Katz for U.S. Senate",
        "account": "FEC C00935163",
        "files": [
            ("Katz August.pdf", "01/01/2026", "03/31/2026"),
            ("Katz July.pdf", "04/01/2026", "06/30/2026"),
            ("Katz Prelim.pdf", "07/01/2026", "08/26/2026"),
            ("Katz October.pdf", "08/27/2026", "09/30/2026"),
        ],
        "updateFiles": [
            ("202610229945116949.pdf", "10/01/2026", "10/14/2026"),
        ],
    },
    "us-sen-chris-coons": {
        "committee": "Chris Coons for Delaware",
        "account": "FEC C00475392",
        "files": [
            ("Coons April 2025.pdf", "01/01/2025", "03/31/2025"),
            ("Coons July 2025.pdf", "04/01/2025", "06/30/2025"),
            ("Coons Oct 2025.pdf", "07/01/2025", "09/30/2025"),
            ("Coons 2025 Annual.pdf", "10/01/2025", "12/31/2025"),
            ("Coons April 2026.pdf", "01/01/2026", "03/31/2026"),
            ("Coons July 2026.pdf", "04/01/2026", "06/30/2026"),
            ("Coons Prelim 2026.pdf", "07/01/2026", "08/26/2026"),
            ("Coons Oct 2026.pdf", "08/27/2026", "09/30/2026"),
        ],
        "updateFiles": [
            ("202610229940935637.pdf", "10/01/2026", "10/14/2026"),
        ],
        "notices": [
            {"sourceFile": "202610249945201275.pdf", "date": "10/22/2026", "name": "Finseca PAC", "address": "Washington, DC", "amount": 1000.00},
            {"sourceFile": "202610249945201275.pdf", "date": "10/22/2026", "name": "Machinists Non Partisan Political League of the International Association of Machinists & Aerospace Workers", "address": "Upper Marlboro, MD", "amount": 5000.00},
        ],
    },
}


def merge(dataset: dict, katz_dir: Path, coons_dir: Path, house_dir: Path, update_dir: Path) -> dict:
    directories = {
        "us-sen-michael-dr-mike-katz": katz_dir,
        "us-sen-chris-coons": coons_dir,
        "us-house-sarah-mcbride": house_dir,
        "us-house-joseph-dr-joe-arminio": house_dir,
    }
    by_id = {candidate["id"]: candidate for candidate in dataset["candidates"]}
    for candidate_id, config in REPORTS.items():
        candidate = by_id[candidate_id]
        totals = []
        donors = []
        small_rows = []
        full_reports = config["files"] + config.get("updateFiles", [])
        update_names = {filename for filename, _, _ in config.get("updateFiles", [])}
        for filename, start, end in full_reports:
            path = (update_dir if filename in update_names else directories[candidate_id]) / filename
            report = summary(path)
            report.update({"filename": filename, "start": start, "end": end})
            totals.append(report)
            donors.extend(receipts(path))
            if report["unitemized"]:
                small_rows.append({
                    "date": end,
                    "name": "TOTAL OF UNITEMIZED FEC CONTRIBUTIONS",
                    "address": "Location unavailable",
                    "aggregate": report["unitemized"],
                    "amount": report["unitemized"],
                    "receiptType": "aggregate-fec-unitemized-contributions",
                })
        notice_rows = [{
            "date": row["date"], "name": row["name"], "address": row["address"],
            "aggregate": row["amount"], "amount": row["amount"],
            "source": "Federal Election Commission 48-hour notice",
            "sourceFile": row["sourceFile"],
        } for row in config.get("notices", [])]
        donors.extend(notice_rows)
        notice_total = round(sum(row["amount"] for row in notice_rows), 2)
        contribution_total = round(sum(report["contributions"] for report in totals) + notice_total, 2)
        displayed_total = round(sum(row["amount"] for row in donors + small_rows), 2)
        gap = round(contribution_total - displayed_total, 2)
        candidate.update({
            "committee": config["committee"],
            "account": config["account"],
            "reportDate": "10/25/2026" if notice_rows else "10/22/2026" if config.get("updateFiles") else "10/15/2026",
            "periodStart": full_reports[0][1],
            "periodEnd": notice_rows[-1]["date"] if notice_rows else full_reports[-1][2],
            "totalReceipts": contribution_total,
            "candidateLoans": round(sum(report["candidateLoans"] for report in totals), 2),
            "totalExpenditures": round(sum(report["expenditures"] for report in totals), 2),
            "endingBalance": totals[-1]["endingBalance"],
            "itemizedTotal": round(sum(row["amount"] for row in donors), 2),
            "smallContributionsTotal": round(sum(row["amount"] for row in small_rows), 2),
            "smallContributionRows": small_rows,
            "reportedItemizedTotal": round(contribution_total - sum(row["amount"] for row in small_rows), 2),
            "itemizedReconciliationGap": gap,
            "delawareTotal": round(sum(row["amount"] for row in donors if row["address"].endswith(", DE")), 2),
            "outsideTotal": round(sum(row["amount"] for row in donors if not row["address"].endswith(", DE")), 2),
            "unitemizedOrOther": gap,
            "donors": donors,
            "excludedRows": 0,
            "sourceFile": "; ".join([filename for filename, _, _ in full_reports] + [row["sourceFile"] for row in config.get("notices", [])]),
            "reportAvailable": True,
            "reportLabel": "Federal Election Commission reports and 48-hour notices" if notice_rows else "Federal Election Commission reports",
            "reportJurisdiction": "Federal Election Commission",
            "locationChartNote": "Based on mailing addresses for itemized FEC contributions; unitemized federal contributions are excluded from this location chart.",
            "endingBalanceDate": totals[-1]["end"],
        })
    dataset["generated"] = datetime.now().date().isoformat()
    return dataset


def main():
    source, katz_dir, coons_dir, house_dir, update_dir, output = map(Path, sys.argv[1:7])
    dataset = json.loads(source.read_text())
    result = merge(dataset, katz_dir, coons_dir, house_dir, update_dir)
    output.write_text(json.dumps(result, indent=2) + "\n")
    for candidate_id in REPORTS:
        candidate = next(c for c in result["candidates"] if c["id"] == candidate_id)
        print(candidate["candidate"], candidate["totalReceipts"], candidate["itemizedReconciliationGap"], len(candidate["donors"]))


if __name__ == "__main__":
    main()
