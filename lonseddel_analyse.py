#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path
from typing import Dict, List, Optional

import pdfplumber

PATTERNS = {
    "arbejdstimer": [
        r"Norm\.timer[\s:]*([\d]{1,4}[,.]\d{1,2})",
        r"Betalte timer[\s:]*([\d]{1,4}[,.]\d{1,2})",
        r"Arbejdstid[\s:]*([\d]{1,4}[,.]\d{1,2})",
        r"Arbejdstimer[\s:]*([\d]{1,4}[,.]\d{1,2})",
        r"Timer[\s:]*([\d]{1,4}[,.]\d{1,2})",
    ],
    "sygdom_days": [
        r"Sygedage[\s:]*([\d]{1,4}[,.]\d{1,2})",
        r"Sygdom[\s:]*([\d]{1,4}[,.]\d{1,2})",
        r"Fravær[\s:]*([\d]{1,4}[,.]\d{1,2})",
    ],
    "ferie_days": [
        r"Feriedage[\s:]*([\d]{1,4}[,.]\d{1,2})",
        r"Ferie[\s:]*([\d]{1,4}[,.]\d{1,2})",
        r"Afholdt ferie[\s:]*([\d]{1,4}[,.]\d{1,2})",
    ],
    "brutto": [
        r"A-Indkomst[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"AM-grundlag[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"Ferieberettiget løn[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"Bruttoløn[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"Brutto[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"Løn før skat[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
    ],
    "netto": [
        r"Til udbetaling[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"Udbetalt[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"Netto[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
    ],
    "sh_period": [
        r"Søgnehelligdag,\s*opsparet\s+[\d\s\.,%]+\s+[\d\s\.,%]+\s+([\d\s\.,-]+)",
        r"Søgnehelligdag\s+[\d\s\.,%]+\s+[\d\s\.,%]+\s+([\d\s\.,-]+)",
        r"Søgnehelligdagsopsparing.*?([\d\s\.,-]+)",
        r"Søgnehelligdagsbetaling.*?([\d\s\.,-]+)",
        r"SH\s*[:\-]?\s*([\d\s\.,-]+)",
        r"S/H\s*[:\-]?\s*([\d\s\.,-]+)",
    ],
    "sh_rest": [
        r"Søgnehelligdag(?:, opsparet)?[\s\d\.,%]+\s+[\d\s\.,%]+\s+(-?[\d\s\.,]+)",
        r"Søgnehelligdag(?:, opsparet)?[\s\d\.,%]+\s+(-?[\d\s\.,]+)\s*$",
    ],
    "tax": [
        r"A-skat[^\n]*?([\-\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2}))\s*$",
        r"Skat[^\n]*?([\-\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2}))\s*$",
    ],
    "pension_employee": [
        r"Medarbejderbidrag[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"Arbejdsmarkedspension, medarbejder(?:procent|bidrag).*?([\-\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"Arbejdstagerpension[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"Pension egen[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
    ],
    "pension_employer": [
        r"Virksomhedsprocent\s*\([^)]*\)\s*([\-\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"Arbejdsmarkedspension, virksomhedsbidrag[\s:]*([\-\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"Arbejdsgiverpension[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"Pension arbejdsgiver[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"Pension overføres(?: til [^\d\n]*)?([\-\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)(?:\s|$)",
    ],
    "other_deductions": [
        r"Fri telefon m\.m\. udligning[\s:]*(-?[\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
        r"ATP-bidrag[^\n]*?(-?[\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
    ],
}

PATTERNS_YTD = {
    "arbejdstimer_ytd": [
        r"Arbejdstimer[\s:]*([\d]{1,4}[,.]\d{1,2})",
    ],
    "a_indkomst_ytd": [
        r"(?-i:A-Indkomst[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?))",
    ],
    "am_grundlag_ytd": [
        r"(?-i:AM-grundlag[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?))",
    ],
    "skattebelob_ytd": [
        r"(?-i:A-skat, samlet[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?))",
        r"(?-i:A-skat samlet[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?))",
    ],
    "am_bidrag_samlet_ytd": [
        r"AM-bidrag, samlet[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
    ],
    "atp_medarbejder_ytd": [
        r"ATP, medarbejderbidrag[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
    ],
    "atp_virksomhed_ytd": [
        r"ATP, virksomhedsbidrag[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
    ],
    "feriepengeopsparing_ytd": [
        r"Feriepengeopsparing[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
    ],
    "feriepenge_efter_skat_ytd": [
        r"Feriepenge efter skat[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
    ],
    "fri_telefon_internet_ytd": [
        r"Fri telefon og internet[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
    ],
    "pension_employee_ytd": [
        r"Arbejdsmarkedspension, medarbejderbidrag[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
    ],
    "pension_employer_ytd": [
        r"Arbejdsmarkedspension, virksomhedsbidrag[\s:]*([\d]{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?)",
    ],
}


def norm_number(value: str) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace("kr.", "").replace("kr", "")
    text = text.replace(" ", "")
    if not text:
        return None
    if text.count(",") == 1 and text.count(".") >= 1:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group()) if m else None


YTD_EXCLUDE_PATTERNS = [
    r"år\s+til\s+dato",
    r"til\s+dato",
    r"year\s+to\s+date",
    r"ytd",
]


def text_before_ytd_section(text: str) -> str:
    parts = re.split(r"(?i)\bSALDI\b|År\s+til\s+dato|YEAR\s+TO\s+DATE|\bYTD\b", text, maxsplit=1)
    return parts[0] if parts else text


def text_after_ytd_section(text: str) -> str:
    parts = re.split(r"(?i)\bSALDI\b|År\s+til\s+dato|YEAR\s+TO\s+DATE|\bYTD\b", text, maxsplit=1)
    return parts[1] if len(parts) > 1 else ""


def extract_first(patterns: List[str], text: str, exclude_patterns: Optional[List[str]] = None) -> Optional[float]:
    exclude_patterns = exclude_patterns or []
    for pattern in patterns:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL):
            if exclude_patterns:
                start = text.rfind("\n", 0, m.start()) + 1
                end = text.find("\n", m.end())
                if end == -1:
                    end = len(text)
                line_text = text[start:end]
                if any(re.search(exclude, line_text, flags=re.IGNORECASE) for exclude in exclude_patterns):
                    continue
            return norm_number(m.group(1))
    return None


def extract_all(patterns: List[str], text: str) -> List[float]:
    values = []
    for pattern in patterns:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL):
            value = norm_number(m.group(1))
            if value is not None:
                values.append(value)
    return values


def extract_last(patterns: List[str], text: str) -> Optional[float]:
    values = extract_all(patterns, text)
    return values[-1] if values else None


def read_pdf_text(pdf_path: Path) -> str:
    parts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if txt:
                parts.append(txt)
    return "\n".join(parts)


def text_before_ytd_section(text: str) -> str:
    parts = re.split(r"(?i)\bSALDI\b|År\s+til\s+dato|YEAR\s+TO\s+DATE|\bYTD\b", text, maxsplit=1)
    return parts[0] if parts else text


def parse_payslip_text(text: str) -> dict:
    monthly_text = text_before_ytd_section(text)
    ytd_text = text_after_ytd_section(text)
    sh_period = extract_first(PATTERNS["sh_period"], monthly_text)
    sh_rest = extract_last(PATTERNS["sh_rest"], monthly_text)
    pension_employee = extract_first(PATTERNS["pension_employee"], monthly_text)
    pension_employer = extract_first(PATTERNS["pension_employer"], monthly_text)
    ytd_values = {key: extract_last(patterns, ytd_text) for key, patterns in PATTERNS_YTD.items()}
    pension_total_ytd = None
    if ytd_values.get("pension_employee_ytd") is not None and ytd_values.get("pension_employer_ytd") is not None:
        pension_total_ytd = ytd_values["pension_employee_ytd"] + ytd_values["pension_employer_ytd"]
    return {
        "arbejdstimer": extract_first(PATTERNS["arbejdstimer"], monthly_text, exclude_patterns=YTD_EXCLUDE_PATTERNS),
        "sygdom_days": extract_first(PATTERNS["sygdom_days"], monthly_text),
        "ferie_days": extract_first(PATTERNS["ferie_days"], monthly_text),
        "brutto": extract_first(PATTERNS["brutto"], monthly_text),
        "netto": extract_first(PATTERNS["netto"], monthly_text),
        "skattebelob": extract_first(PATTERNS["tax"], monthly_text),
        "sh_period": sh_period,
        "sh_rest": sh_rest,
        "pension_employee": pension_employee,
        "pension_employer": pension_employer,
        "other_deductions": extract_first(PATTERNS["other_deductions"], monthly_text),
        "arbejdstimer_ytd": ytd_values.get("arbejdstimer_ytd"),
        "a_indkomst_ytd": ytd_values.get("a_indkomst_ytd"),
        "am_grundlag_ytd": ytd_values.get("am_grundlag_ytd"),
        "skattebelob_ytd": ytd_values.get("skattebelob_ytd"),
        "am_bidrag_samlet_ytd": ytd_values.get("am_bidrag_samlet_ytd"),
        "atp_medarbejder_ytd": ytd_values.get("atp_medarbejder_ytd"),
        "atp_virksomhed_ytd": ytd_values.get("atp_virksomhed_ytd"),
        "feriepengeopsparing_ytd": ytd_values.get("feriepengeopsparing_ytd"),
        "feriepenge_efter_skat_ytd": ytd_values.get("feriepenge_efter_skat_ytd"),
        "fri_telefon_internet_ytd": ytd_values.get("fri_telefon_internet_ytd"),
        "pension_employee_ytd": ytd_values.get("pension_employee_ytd"),
        "pension_employer_ytd": ytd_values.get("pension_employer_ytd"),
        "pension_total_ytd": pension_total_ytd,
    }


def analyze_payslip(pdf_path: Path, debug: bool = False) -> Dict[str, object]:
    text = read_pdf_text(pdf_path)
    if debug:
        print(f"\n===== {pdf_path.name} =====")
        print(text[:20000])
        print("===== END =====\n")
    data = parse_payslip_text(text)
    data["file"] = pdf_path.name
    return data


MONTH_ORDER = {
    "januar": 1,
    "februar": 2,
    "marts": 3,
    "april": 4,
    "maj": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def month_sort_key(name: str) -> int:
    text = name.lower()
    for month, index in MONTH_ORDER.items():
        if month in text:
            return index
    return 999


def find_pdfs(folder: Path) -> List[Path]:
    return sorted(
        [p for p in folder.rglob("*.pdf") if p.is_file()],
        key=lambda p: month_sort_key(p.name),
    )


def write_csv(rows: List[Dict[str, object]], output_path: Path) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_table(rows: List[Dict[str, object]]) -> None:
    if not rows:
        print("Ingen lønsedler fundet.")
        return
    headers = ["Fil", "Arbejdstimer", "Sygdom (dage)", "Ferie (dage)", "Brutto", "Netto", "Skat", "SH-perioden", "SH-rest", "Pension m.", "Pension arb.", "Andre fradrag"]
    print("\n" + " | ".join(headers))
    print("-" * 165)
    for r in rows:
        print(
            f"{r['file']} | {r['arbejdstimer']} | {r['sygdom_days']} | {r['ferie_days']} | {r['brutto']} | {r['netto']} | {r.get('skattebelob')} | {r.get('sh_period')} | {r.get('sh_rest')} | {r['pension_employee']} | {r['pension_employer']} | {r.get('other_deductions')}"
        )
        ytd_values = []
        if r.get("arbejdstimer_ytd") is not None:
            ytd_values.append(f"Arbejdstimer YTD: {r['arbejdstimer_ytd']}")
        if r.get("a_indkomst_ytd") is not None:
            ytd_values.append(f"A-Indkomst YTD: {r['a_indkomst_ytd']}")
        if r.get("skattebelob_ytd") is not None:
            ytd_values.append(f"A-skat YTD: {r['skattebelob_ytd']}")
        if r.get("pension_total_ytd") is not None:
            ytd_values.append(f"Pension YTD: {r['pension_total_ytd']}")
        if ytd_values:
            print("   " + " | ".join(ytd_values))


def main():
    parser = argparse.ArgumentParser(description="Læs lønsedler og udtræk info til CSV")
    parser.add_argument("--mappe", required=True, help="Mappe med PDF-lønsedler")
    parser.add_argument("--csv", help="Gem resultat til CSV-fil")
    parser.add_argument("--debug", action="store_true", help="Vis rå tekst fra PDF for fejlsøgning")
    args = parser.parse_args()

    folder = Path(args.mappe)
    if not folder.exists() or not folder.is_dir():
        raise SystemExit(f"Mappe findes ikke: {folder}")

    pdfs = find_pdfs(folder)
    if not pdfs:
        raise SystemExit(f"Ingen PDF-filer fundet i: {folder}")

    rows = []
    for pdf in pdfs:
        try:
            row = analyze_payslip(pdf, debug=args.debug)
            rows.append(row)
        except Exception as e:
            rows.append({
                "file": pdf.name,
                "arbejdstimer": None,
                "sygdom_days": None,
                "ferie_days": None,
                "brutto": None,
                "netto": None,
                "skattebelob": None,
                "sh_period": None,
                "pension_employee": None,
                "pension_employer": None,
            })
            print(f"Fejl i {pdf.name}: {e}")

    print_table(rows)

    if args.csv:
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_csv(rows, out)
        print(f"\nCSV gemt: {out}")


if __name__ == "__main__":
    main()
