#!/usr/bin/env python3
"""Build the 2026 Delaware general-election campaign-finance dataset.

The official candidate page controls candidate names, parties, and races. The
supplied 30-day reports control financial totals. Qualified candidates without
a supplied candidate-committee report remain visible with reportAvailable=false.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import extract_data as candidate_parser
from extract_outside_spending import choose_reports, parse_report


ACCOUNT_TO_CANDIDATE = {
    "01005567": "Paul Hertz",
    "01005575": "Valerie George",
    "01006706": "Alison T. Gibbs",
    "01001986": "Kim Williams",
    "01002709": "Nicole Poore",
    "01003090": "Lyndon D. Yearick",
    "01003091": "Sean M. Lynn",
    "01003160": "Mike Smith",
    "01003818": "Jack Walsh",
    "01004199": "Kathy Jennings",
    "01004213": "Kendra Johnson",
    "01004274": "Bryan William Shupe",
    "01004409": "John L. Rieley",
    "01004772": "Spiros Mantzavinos",
    "01005348": "Kerri Evelyn Harris",
    "01005517": "Sophie Phillips",
    "01005540": "Lydia York",
    "01005550": "Norman R. Barlow",
    "01005581": "Robert \"Bobby\" Scott",
    "01006174": "Steve Pickering",
    "01006187": "Shay Frisby",
    "01006227": "Dan Cruce",
    "01006391": "Maureen Madden",
    "01006437": "Ramona Bracy",
    "01006444": "Rachel \"Rae\" Krantz",
    "01006445": "Jason Hoover",
    "01006453": "Ryan Stuckey",
    "01006457": "Ted Lauzen",
    "01006466": "Morgan Hudson",
    "01006529": "Emily A. Thompson",
    "01006541": "Gary Taylor",
    "01006607": "Joshua Pennington",
    "01006672": "Jamar Money",
    "01006677": "Alex Green",
    "01006679": "Mary \"Penny\" Kubin",
    "01006684": "Gene Dvornick",
    "01006685": "Andrew \"Andy\" Gorlich",
    "01006696": "Michael Ramone",
    "01006697": "Stephen P. Ondich",
    "01006711": "Austin Cassidy",
    "01006738": "Tori Parker",
    "01006741": "Mara Gorman",
    "01001340": "Daniel B. Short",
    "01002132": "Ed Osienski",
    "01002266": "Ciro Poppiti",
    "01002690": "Timothy Dale Dukes",
    "01002700": "Jeffrey N. Spiegelman",
    "01002827": "Brian G. Pettyjohn",
    "01000408": "Gerald W. Hocker",
    "01004126": "Jeff Hall",
    "01004153": "Krista Griffith",
    "01004210": "Wm Shannon Morris",
    "01004236": "Jesse R. Vanderwende",
    "01004307": "Dee Durham",
    "01004341": "David Carter",
    "01004425": "Douglas B. Hudson",
    "01004439": "Nnamdi O. Chukwuocha",
    "01004636": "Eric Morrison",
    "01004978": "Sherae'a \"Rae\" Moore",
    "01005329": "Greg Fuller",
    "01005375": "DeShanna U. Neal",
    "01005524": "Eugenia Thornton",
    "01005565": "Alexandra Reed Baker",
    "01005596": "Jamie Collins",
    "01005829": "Branden Fletcher-Dominguez",
    "01005874": "Valerie Jones Giltner",
    "01005971": "Claire Snyder-Hall",
    "01006069": "Gregg Lindner",
    "01006115": "Mara Gorman",
    "01006291": "Mark Pugh",
    "01006426": "Alonna Berry",
    "01006458": "Nisha Lodhavia",
    "01006507": "Kira Alejandro",
    "01006542": "Robert T. Lee",
    "01006558": "John Atkins",
    "01006622": "Justine Cuccia",
    "01006627": "Dave Redlawsk",
    "01006635": "Carlie Carey",
    "01006644": "Frank E Coleman",
    "01006654": "Dan Zitofsky",
    "01006662": "Michelle H. Booker",
    "01006671": "Shane Cavanaugh",
    "01006673": "Annie Norman",
    "01006695": "David Tackett",
    "01006718": "Anton Brogden",
    "01006700": "Tyeisha \"Tye\" Grier",
    "01006699": "Chris Rowe",
    "01006710": "Ayanna Khan-Flowers",
    "01006724": "Harry S. Gold",
    "01006730": "Dolores Dunleavy",
    "01006726": "April Callaway",
    "01006731": "Tanya Hettler",
    "01006729": "Hildi Bachtle",
    "01006733": "Brent Burdge",
    "01006734": "Shane Stoneman",
    "01006736": "Enala A. Mwashitete",
    "01006735": "Lisa McInnis",
    "01006698": "Janyce Colmery",
    "01004162": "William Bush",
    "01004342": "Melissa Minor Brown",
    "01004369": "Larry Lambert",
    "01004725": "Madinah Wilson-Anton",
    "01004748": "Kyra L. Hoffner",
    "01004789": "Marie Pinkney",
    "01005519": "Brandon Toole",
    "01005886": "Kamela T. Smith",
    "01005977": "Dexter \"Dizzy\" Bland",
    "01006025": "Melanie Ross Levin",
    "01006470": "Jill Hicks",
    "01006689": "Melissa S. Brayman",
    "01006709": "David C. \"Dave\" Graham",
    "01006712": "Steven Washington",
    "01006717": "Carolyn Frank",
    "01006742": "Shane Cavanaugh",
    "01002289": "Terry L. Pepper",
    "01004147": "Scott Phillips",
    "01005478": "Cyndie Romer",
    "01005582": "Frank Burns",
    "01006451": "Pamela Salaam",
    "01006633": "Mike Simpler",
    "01006732": "Shawn L. Dottery",
}


def text_only(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def race_meta(office: str) -> tuple[str, str]:
    simple = {
        "U.S. Senator": ("US-SEN", "U.S. Senate"),
        "Representative in Congress": ("US-HOUSE", "U.S. House"),
        "Attorney General": ("AG", "Attorney General"),
        "Auditor of Accounts": ("AUD", "Auditor of Accounts"),
        "State Treasurer": ("TRS", "State Treasurer"),
        "New Castle County Recorder of Deeds": ("NCC-ROD", "New Castle County Recorder of Deeds"),
        "New Castle County Register of Wills": ("NCC-ROW", "New Castle County Register of Wills"),
        "New Castle County Sheriff": ("NCC-SHERIFF", "New Castle County Sheriff"),
        "Kent County Recorder of Deeds": ("KC-ROD", "Kent County Recorder of Deeds"),
        "Kent County Sheriff": ("KC-SHERIFF", "Kent County Sheriff"),
        "Kent County Levy Court At-Large": ("KC-AL", "Kent County Levy Court At-Large"),
        "Sussex County Recorder of Deeds": ("SC-ROD", "Sussex County Recorder of Deeds"),
        "Sussex County Register of Wills": ("SC-ROW", "Sussex County Register of Wills"),
        "Sussex County Sheriff": ("SC-SHERIFF", "Sussex County Sheriff"),
    }
    if office in simple:
        return simple[office]
    patterns = (
        (r"State Senator District (\d+)", "SD", "State Senate District"),
        (r"State Representative District (\d+)", "RD", "State House District"),
        (r"New Castle County Council District (\d+)", "NCC", "New Castle County Council District"),
        (r"Kent County Levy Court District (\d+)", "KC", "Kent County Levy Court District"),
        (r"Sussex County Council District (\d+)", "SC", "Sussex County Council District"),
    )
    for pattern, prefix, label in patterns:
        match = re.fullmatch(pattern, office)
        if match:
            number = str(int(match.group(1)))
            return f"{prefix}{number}", f"{label} {number}"
    return slug(office).upper(), office


def parse_candidates(page: Path) -> list[dict]:
    source = page.read_text(encoding="utf-8", errors="ignore")
    candidates = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", source, re.S | re.I):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)
        if len(cells) < 6:
            continue
        name_match = re.search(
            r"<span class='main-span'[^>]*>(.*?)(?:<i|</span>)", cells[3], re.S | re.I
        )
        record = {
            "office": text_only(cells[0]),
            "county": text_only(cells[1]),
            "party": text_only(cells[2]),
            "candidate": text_only(name_match.group(1) if name_match else cells[3]),
            "status": text_only(cells[4]),
            "filed": text_only(cells[5]),
        }
        if record["status"] != "Qualified":
            continue
        race_id, race = race_meta(record["office"])
        record.update({"raceId": race_id, "race": race})
        record["id"] = f"{race_id.casefold()}-{slug(record['candidate'])}"
        candidates.append(record)
    return candidates


def pdf_text(pdf: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        check=True, capture_output=True, text=True,
    ).stdout


def report_sort_key(pdf: Path) -> tuple[int, datetime, int, str]:
    text = pdf_text(pdf)
    first = text.split("\f", 1)[0]
    amended = int(bool(re.search(r"AMENDMENT\s*:\s*R YES", first)))
    report_date = candidate_parser.field(first, "DATE OF THIS REPORT")
    version = re.search(r"Document:\s*14904\s+Version:\s*(\d+)", text)
    try:
        parsed_date = datetime.strptime(report_date, "%m/%d/%Y")
    except ValueError:
        parsed_date = datetime.min
    return amended, parsed_date, int(version.group(1)) if version else 1, pdf.name


def choose_candidate_reports(pdf_dir: Path) -> tuple[dict[str, Path], list[dict]]:
    by_account: dict[str, list[Path]] = defaultdict(list)
    excluded = []
    for pdf in sorted(pdf_dir.glob("*.pdf")):
        text = pdf_text(pdf).split("\f", 1)[0]
        account = candidate_parser.field(text, "ACCOUNT NUMBER")
        if account.startswith("01"):
            by_account[account].append(pdf)
    selected = {}
    for account, reports in by_account.items():
        ordered = sorted(reports, key=report_sort_key, reverse=True)
        selected[account] = ordered[0]
        for report in ordered[1:]:
            excluded.append({"sourceFile": report.name, "reason": "duplicate or superseded candidate report"})
    return selected, excluded


def empty_financial_record(candidate: dict) -> dict:
    return {
        **candidate,
        "committee": "No candidate-committee report supplied",
        "account": "",
        "reportAvailable": False,
        "reportDate": "",
        "periodStart": "",
        "periodEnd": "",
        "totalReceipts": 0,
        "candidateLoans": 0,
        "totalExpenditures": 0,
        "endingBalance": 0,
        "itemizedTotal": 0,
        "smallContributionsTotal": 0,
        "smallContributionRows": [],
        "reportedItemizedTotal": 0,
        "itemizedReconciliationGap": 0,
        "delawareTotal": 0,
        "outsideTotal": 0,
        "unitemizedOrOther": 0,
        "donors": [],
        "excludedRows": 0,
        "sourceFile": "",
    }


def candidate_dataset(pdf_dir: Path, official_page: Path) -> tuple[dict, dict[str, Path], list[dict]]:
    official = parse_candidates(official_page)
    official_by_name = {c["candidate"]: c for c in official}
    selected, excluded = choose_candidate_reports(pdf_dir)
    records = {c["candidate"]: empty_financial_record(c) for c in official}
    unmatched = []
    matched_reports: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    for account, pdf in selected.items():
        official_name = ACCOUNT_TO_CANDIDATE.get(account)
        candidate = official_by_name.get(official_name or "")
        if not candidate:
            first = pdf_text(pdf).split("\f", 1)[0]
            unmatched.append({
                "account": account,
                "organization": candidate_parser.field(first, "FULL ORGANIZATION NAME"),
                "sourceFile": pdf.name,
                "reason": "candidate committee does not match a qualified general-election candidate",
            })
            continue
        matched_reports[candidate["candidate"]].append((account, pdf))

    for official_name, reports in matched_reports.items():
        reports.sort(key=lambda item: report_sort_key(item[1]), reverse=True)
        account, pdf = reports[0]
        candidate = official_by_name[official_name]
        for duplicate_account, duplicate_pdf in reports[1:]:
            excluded.append({
                "sourceFile": duplicate_pdf.name,
                "reason": f"superseded report for the same candidate (account {duplicate_account})",
            })
        finance = candidate_parser.extract(pdf)
        full_text = pdf_text(pdf)
        reported_loans = candidate_parser.amount_field(
            full_text[:8000], r"SCHEDULE D-1\s*-\s*TOTAL LOANS RECEIVED AND DEBTS INCURRED"
        )
        finance.update(candidate)
        finance.update({
            "id": candidate["id"],
            "candidate": candidate["candidate"],
            "shortName": candidate["candidate"].split()[-1],
            "raceId": candidate["raceId"],
            "race": candidate["race"],
            "party": candidate["party"],
            "county": candidate["county"],
            "filed": candidate["filed"],
            "reportAvailable": True,
            "candidateLoans": candidate_parser.candidate_loans_received(
                full_text, candidate["candidate"], reported_loans
            ),
        })
        records[candidate["candidate"]] = finance
    candidates = sorted(records.values(), key=lambda c: (c["race"], c["party"], c["candidate"]))
    payload = {
        "generated": datetime.now().date().isoformat(),
        "election": "2026 General Election",
        "reportType": "30-day general-election reports",
        "candidateSource": "https://elections.delaware.gov/candidates/candidatelist/genl_fcddt_2026.html",
        "source": "Delaware campaign finance reports supplied by Spotlight Delaware",
        "candidates": candidates,
        "unmatchedCandidateReports": unmatched,
        "excludedCandidateReports": excluded,
    }
    return payload, selected, unmatched


def normalized(value: str) -> str:
    value = re.sub(r'"[^"]+"', " ", value)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def recipient_matches(raw_text: str, candidates: list[dict]) -> list[dict]:
    haystack = normalized(raw_text)
    compact = haystack.replace(" ", "")
    matches = []
    for candidate in candidates:
        committee = normalized(candidate["committee"]) if candidate["reportAvailable"] else ""
        name = normalized(candidate["candidate"])
        name_parts = name.split()
        committee_hit = bool(committee) and len(committee) >= 8 and (
            committee in haystack or committee.replace(" ", "") in compact
        )
        name_hit = len(name_parts) >= 2 and name_parts[0] in haystack.split() and name_parts[-1] in haystack.split()
        if committee_hit or name_hit:
            matches.append(candidate)
    # Different spellings found in reports and PAC payees.
    aliases = {
        "shannon morris": "Wm Shannon Morris",
        "danny short": "Daniel B. Short",
        "tim dukes": "Timothy Dale Dukes",
        "doug hudson": "Douglas B. Hudson",
        "david redlawsk": "Dave Redlawsk",
        "sheraea moore": "Sherae'a \"Rae\" Moore",
        "anne norman": "Annie Norman",
        "rajalakshmi lodhavia": "Nisha Lodhavia",
        "branden fletcher": "Branden Fletcher-Dominguez",
        "rae krantz": "Rachel \"Rae\" Krantz",
        "andy gorlich": "Andrew \"Andy\" Gorlich",
        "alexander green": "Alex Green",
        "kimberly williams": "Kim Williams",
    }
    by_name = {c["candidate"]: c for c in candidates}
    for alias, official in aliases.items():
        if alias in haystack and by_name.get(official) not in matches:
            matches.append(by_name[official])
    return matches


DSEA_CANDIDATE_ALIASES = {
    "moore": "Sherae'a \"Rae\" Moore",
    "ross levin": "Melanie Ross Levin",
    "snyder hall": "Claire Snyder-Hall",
    "berry": "Alonna Berry",
    "morrison": "Eric Morrison",
    "mantzavinos": "Spiros Mantzavinos",
    "gorman": "Mara Gorman",
    "poore": "Nicole Poore",
    "hoffner": "Kyra L. Hoffner",
    "lindner": "Gregg Lindner",
    "lodhavia": "Nisha Lodhavia",
    "krantz": "Rachel \"Rae\" Krantz",
}

COMMON_GROUND_UNALLOCATED_SUPPORT = [
    "Mark Pugh",
    "Shane Cavanaugh",
    "Gary Taylor",
    "Jamar Money",
    "Gene Dvornick",
    'Mary "Penny" Kubin',
]


def dsea_allocations(raw_text: str, candidates: list[dict]) -> list[tuple[dict, float]]:
    """Extract the candidate-level amounts printed inside DSEA's grouped rows."""
    by_name = {candidate["candidate"]: candidate for candidate in candidates}
    allocations = []
    for label, amount in re.findall(
        r"([A-Za-z][A-Za-z-]+)\s*(?:\|\s*)?\(([\d,]+(?:\.\d+)?)\)", raw_text
    ):
        official = DSEA_CANDIDATE_ALIASES.get(normalized(label))
        candidate = by_name.get(official or "")
        if candidate:
            allocations.append((candidate, float(amount.replace(",", ""))))
    return allocations


SENATE_MAJORITY_ALIASES = {
    "dan cruce": "Dan Cruce",
    "shay frisby": "Shay Frisby",
    "mara gorman": "Mara Gorman",
    "nicole poore": "Nicole Poore",
    "kyra hoffner": "Kyra L. Hoffner",
    "nish lodhavia": "Nisha Lodhavia",
    "nisha lodhavia": "Nisha Lodhavia",
}


def senate_majority_allocations(raw_text: str, candidates: list[dict]) -> list[tuple[dict, float]]:
    """Extract candidate amounts printed in Senate Majority Caucus grouped rows."""
    by_name = {candidate["candidate"]: candidate for candidate in candidates}
    allocations = []
    pattern = (
        r"(Dan Cruce|Shay Frisby|Mara Gorman|Nicole Poore|Kyra Hoffner|"
        r"Nish(?:a)?\s*(?:\|\s*)?Lodhavia),?\s*(?:\|\s*)?SD\s*\d+\s*:\s*"
        r"(?:\|\s*)?\$?\s*([\d,]+(?:\.\d+)?)"
    )
    for label, amount in re.findall(pattern, raw_text, re.I):
        official = SENATE_MAJORITY_ALIASES.get(normalized(label))
        candidate = by_name.get(official or "")
        if candidate:
            allocations.append((candidate, float(amount.replace(",", ""))))
    return allocations


def outside_dataset(pdf_dir: Path, candidate_payload: dict) -> dict:
    candidates = candidate_payload["candidates"]
    reports = [parse_report(pdf) for pdf in sorted(pdf_dir.glob("*.pdf"))]
    pac_reports = [r for r in reports if r["account"].startswith(("02", "03"))]
    ignored_tpa_accounts = {"04006715"}
    tpa_reports = [
        r for r in reports
        if r["account"].startswith("04") and r["account"] not in ignored_tpa_accounts
    ]
    selected_pac, excluded = choose_reports(pac_reports)
    selected_tpa, excluded_tpa = choose_reports(tpa_reports)
    excluded.extend(excluded_tpa)
    excluded.extend({
        "sourceFile": r["sourceFile"],
        "reason": "Excluded at Spotlight Delaware's direction",
    } for r in reports if r["account"] in ignored_tpa_accounts)
    allocations = []
    issues = []
    groups = []

    for report in selected_pac:
        if report["reportedTotal"] <= 0:
            excluded.append({"sourceFile": report["sourceFile"], "reason": "PAC or political committee reported no expenditures"})
            continue
        for index, row in enumerate(report["expenditures"]):
            matches = recipient_matches(row["rawText"], candidates)
            if len(matches) == 1:
                candidate = matches[0]
                allocations.append({
                    "id": f"pac-{report['account']}-{hashlib.sha1(report['sourceFile'].encode()).hexdigest()[:8]}-{index}",
                    "candidateId": candidate["id"],
                    "candidateName": candidate["candidate"],
                    "targetCandidateId": None,
                    "position": "support",
                    "allocationType": "direct-pac-contribution",
                    "amount": row["amount"],
                    "date": row["date"],
                    "organization": report["organization"],
                    "account": report["account"],
                    "activity": "Direct PAC donation",
                    "payee": row["payee"],
                    "sourceFile": report["sourceFile"],
                    "reportPeriodEnd": report["periodEnd"],
                    "note": "PAC expenditure paid directly to the named candidate committee.",
                })
            elif len(matches) > 1:
                issues.append({
                    "account": report["account"], "sourceFile": report["sourceFile"],
                    "reason": "Expenditure matched multiple candidate committees and was left unattributed.",
                    "amount": row["amount"], "rawText": row["rawText"],
                })
        existing = next((g for g in groups if g["account"] == report["account"]), None)
        if existing:
            existing["reportedExpenditures"] = round(existing["reportedExpenditures"] + report["reportedTotal"], 2)
            existing["reportCount"] += 1
        else:
            groups.append({
                "account": report["account"],
                "organization": report["organization"],
                "entityType": "PAC",
                "reportedExpenditures": report["reportedTotal"],
                "candidateAttributed": 0,
                "reportCount": 1,
            })

    for report in selected_tpa:
        if report["reportedTotal"] <= 0:
            excluded.append({"sourceFile": report["sourceFile"], "reason": "third-party advertiser reported no expenditures"})
            continue
        for index, row in enumerate(report["expenditures"]):
            if report["account"] == "04005615":
                split_allocations = senate_majority_allocations(row["rawText"], candidates)
                if not split_allocations or abs(sum(amount for _, amount in split_allocations) - row["amount"]) > .01:
                    issues.append({
                        "account": report["account"], "sourceFile": report["sourceFile"],
                        "reason": "Senate Majority Caucus candidate allocations did not reconcile and were left unattributed.",
                        "amount": row["amount"], "rawText": row["rawText"],
                    })
                    continue
                key = hashlib.sha1(report["sourceFile"].encode()).hexdigest()[:8]
                for split_index, (candidate, amount) in enumerate(split_allocations):
                    allocations.append({
                        "id": f"tpa-{report['account']}-{key}-{index}-{split_index}-{candidate['id']}",
                        "candidateId": candidate["id"],
                        "candidateName": candidate["candidate"],
                        "targetCandidateId": None,
                        "position": "support",
                        "allocationType": "independent-spending",
                        "amount": amount,
                        "date": row["date"],
                        "organization": report["organization"],
                        "account": report["account"],
                        "activity": "Digital advertising",
                        "payee": row["payee"],
                        "sourceFile": report["sourceFile"],
                        "reportPeriodEnd": report["periodEnd"],
                        "note": "Candidate amount printed in the filing's grouped expenditure description.",
                    })
                continue
            if report["account"] == "04003188":
                split_allocations = dsea_allocations(row["rawText"], candidates)
                if not split_allocations or abs(sum(amount for _, amount in split_allocations) - row["amount"]) > .01:
                    issues.append({
                        "account": report["account"], "sourceFile": report["sourceFile"],
                        "reason": "DSEA candidate allocations did not reconcile to the expenditure and were left unattributed.",
                        "amount": row["amount"], "rawText": row["rawText"],
                    })
                    continue
                key = hashlib.sha1(report["sourceFile"].encode()).hexdigest()[:8]
                for split_index, (candidate, amount) in enumerate(split_allocations):
                    allocations.append({
                        "id": f"tpa-{report['account']}-{key}-{index}-{split_index}-{candidate['id']}",
                        "candidateId": candidate["id"],
                        "candidateName": candidate["candidate"],
                        "targetCandidateId": None,
                        "position": "support",
                        "allocationType": "independent-spending",
                        "amount": amount,
                        "date": row["date"],
                        "organization": report["organization"],
                        "account": report["account"],
                        "activity": "Digital advertising, mail and production",
                        "payee": row["payee"],
                        "sourceFile": report["sourceFile"],
                        "reportPeriodEnd": report["periodEnd"],
                        "note": "Candidate amount printed in the filing's grouped expenditure description.",
                    })
                continue
            matches = recipient_matches(row["rawText"], candidates)
            if report["account"] == "04006743" and len(matches) > 1:
                # The filing names the candidates associated with each grouped
                # expenditure but does not allocate a dollar amount among them.
                # Preserve the association without inventing candidate totals.
                continue
            if len(matches) != 1:
                issues.append({
                    "account": report["account"], "sourceFile": report["sourceFile"],
                    "reason": "Independent expenditure could not be matched to exactly one qualified candidate.",
                    "amount": row["amount"], "rawText": row["rawText"],
                })
                continue
            candidate = matches[0]
            key = hashlib.sha1(report["sourceFile"].encode()).hexdigest()[:8]
            allocations.append({
                "id": f"tpa-{report['account']}-{key}-{index}-{candidate['id']}",
                "candidateId": candidate["id"],
                "candidateName": candidate["candidate"],
                "targetCandidateId": None,
                "position": "support" if re.search(r"support", row["rawText"], re.I) else "associated",
                "allocationType": "independent-spending",
                "amount": row["amount"],
                "date": row["date"],
                "organization": report["organization"],
                "account": report["account"],
                "activity": "Digital advertising" if re.search(r"digital", row["rawText"], re.I) else "Candidate-associated expenditure",
                "payee": row["payee"],
                "sourceFile": report["sourceFile"],
                "reportPeriodEnd": report["periodEnd"],
                "note": "",
            })
        existing = next((g for g in groups if g["account"] == report["account"]), None)
        if existing:
            existing["reportedExpenditures"] = round(existing["reportedExpenditures"] + report["reportedTotal"], 2)
            existing["reportCount"] += 1
        else:
            groups.append({
                "account": report["account"], "organization": report["organization"],
                "entityType": "Third-party advertiser",
                "reportedExpenditures": report["reportedTotal"],
                "candidateAttributed": 0, "reportCount": 1,
            })
    for group in groups:
        group["candidateAttributed"] = round(sum(a["amount"] for a in allocations if a["account"] == group["account"]), 2)
        if group["account"] == "04006743":
            by_name = {candidate["candidate"]: candidate for candidate in candidates}
            group["unallocatedCandidateSupport"] = [
                by_name[name]["id"] for name in COMMON_GROUND_UNALLOCATED_SUPPORT
            ]
            unallocated_amount = round(
                group["reportedExpenditures"] - group["candidateAttributed"], 2
            )
            group["unallocatedSupportNote"] = (
                f"The filings name supported candidates in grouped expenditures totaling ${unallocated_amount:,.2f} "
                "but do not provide candidate-level amounts."
            )
    groups.sort(key=lambda g: (g["entityType"], g["organization"]))
    allocations.sort(key=lambda a: (a["account"], a["date"], a["id"]))
    return {
        "generated": datetime.now().date().isoformat(),
        "methodology": "General-election third-party spending and PAC direct donations are reported separately from candidate fundraising.",
        "groups": groups,
        "allocations": allocations,
        "reviewIssues": issues,
        "excludedReports": excluded,
    }


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit(
            "usage: build_general_database.py PDF_DIR OFFICIAL_HTML CANDIDATE_JSON OUTSIDE_JSON"
        )
    pdf_dir, official_page, candidate_output, outside_output = map(Path, sys.argv[1:])
    candidate_payload, _, unmatched = candidate_dataset(pdf_dir, official_page)
    candidate_output.parent.mkdir(parents=True, exist_ok=True)
    candidate_output.write_text(json.dumps(candidate_payload, indent=2), encoding="utf-8")
    outside_payload = outside_dataset(pdf_dir, candidate_payload)
    outside_output.write_text(json.dumps(outside_payload, indent=2), encoding="utf-8")
    available = sum(c["reportAvailable"] for c in candidate_payload["candidates"])
    print(f"Published {len(candidate_payload['candidates'])} qualified candidates; {available} have supplied reports")
    print(f"Candidate donor rows: {sum(len(c['donors']) for c in candidate_payload['candidates'])}")
    print(f"Unmatched candidate-account reports: {len(unmatched)}")
    print(f"Public outside groups: {len(outside_payload['groups'])}")
    print(f"Outside allocations: {len(outside_payload['allocations'])}")


if __name__ == "__main__":
    main()
