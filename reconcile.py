#!/usr/bin/env python3
import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

PRIMARY_DARK = colors.HexColor("#1a1a2e")
PRIMARY_MID = colors.HexColor("#16213e")
ACCENT = colors.HexColor("#0f3460")
RED = colors.HexColor("#e94560")
GREEN = colors.HexColor("#25a244")
LIGHT_BG = colors.HexColor("#f4f6f9")
MID_GRAY = colors.HexColor("#6f7b91")
WHITE = colors.white
TEXT = colors.HexColor("#1c1c2e")
YELLOW = colors.HexColor("#f4b400")


def normalize_decimal(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("kr.", "").replace("kr", "").replace(" ", "")
    if text.count(",") == 1 and text.count(".") >= 1:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group()) if m else None


def money(value: float) -> str:
    if value is None:
        return "0,00"
    try:
        return f"{float(value):,.2f}".replace(",", " ").replace(".", ",")
    except Exception:
        return str(value)


def parse_date(value) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt)
        except Exception:
            pass
    return None


def is_friday(date_obj: datetime) -> bool:
    return date_obj.weekday() == 4


def sick_hours_from_days(days: float, date_obj: Optional[datetime]) -> float:
    return days * (7.0 if date_obj and is_friday(date_obj) else 7.5)


def detect_category(row) -> str:
    category = (row.get("category") or row.get("type") or row.get("kategori") or "").strip().lower()
    note = (row.get("note") or row.get("tekst") or row.get("description") or "").lower()
    if category:
        if category in ("sick", "sygdom", "syg"):
            return "sick"
        if category in ("vacation", "ferie"):
            return "vacation"
        return "work"
    if any(k in note for k in ["syg", "sygdom", "fravær"]):
        return "sick"
    if any(k in note for k in ["ferie", "vacation"]):
        return "vacation"
    return "work"

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
    text = (name or "").lower()
    for month, index in MONTH_ORDER.items():
        if month in text:
            return index
    return 999


def load_minuba_csv(path: Path) -> Dict[str, float]:
    total = {"work_hours": 0.0, "sick_hours": 0.0, "vacation_hours": 0.0}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hours = normalize_decimal(row.get("hours") or row.get("timer") or row.get("antal_timer") or 0) or 0.0
            cat = detect_category(row)
            if cat == "sick":
                total["sick_hours"] += hours
            elif cat == "vacation":
                total["vacation_hours"] += hours
            else:
                total["work_hours"] += hours
    return total


def load_payslip_csv(path: Path) -> Dict[str, Any]:
    result = {
        "work_hours": 0.0,
        "sick_hours": 0.0,
        "gross_salary": 0.0,
        "net_salary": 0.0,
        "tax": 0.0,
        "sh_period": 0.0,
        "sh_rest": 0.0,
        "pension_employee": 0.0,
        "pension_employer": 0.0,
        "pension_total": 0.0,
        "other_deductions": 0.0,
        "arbejdstimer_ytd": 0.0,
        "payslip_total_hours_ytd": 0.0,
        "payslip_total_hours_source": "monthly",
        "a_indkomst_ytd": 0.0,
        "am_grundlag_ytd": 0.0,
        "skattebelob_ytd": 0.0,
        "pension_employee_ytd": 0.0,
        "pension_employer_ytd": 0.0,
        "pension_total_ytd": 0.0,
        "rows": [],
    }
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result["rows"].append(row)
            work = normalize_decimal(row.get("arbejdstimer") or row.get("hours") or row.get("timer") or 0) or 0.0
            result["work_hours"] += work
            sick_days = normalize_decimal(row.get("sygdom_days") or row.get("sygedage") or row.get("sick_days") or 0) or 0.0
            sick_date = parse_date(row.get("date") or row.get("dato") or row.get("day") or row.get("Date"))
            if sick_days:
                result["sick_hours"] += sick_hours_from_days(sick_days, sick_date)
            gross = normalize_decimal(row.get("brutto") or row.get("gross") or 0) or 0.0
            net = normalize_decimal(row.get("netto") or row.get("net") or 0) or 0.0
            sh = normalize_decimal(row.get("sh_period") or row.get("sh") or row.get("sh_amount") or row.get("savings") or row.get("opsparing") or 0) or 0.0
            sh_rest = normalize_decimal(row.get("sh_rest") or row.get("sh_balance") or row.get("rest") or 0) or 0.0
            emp = normalize_decimal(row.get("pension_employee") or row.get("medarbejderpension") or 0) or 0.0
            er = normalize_decimal(row.get("pension_employer") or row.get("arbejdsgiverpension") or 0) or 0.0
            tax = normalize_decimal(row.get("skattebelob") or row.get("tax") or row.get("skat") or 0) or 0.0
            ptotal = normalize_decimal(row.get("pension_total") or 0) or 0.0
            if ptotal == 0.0:
                ptotal = emp + er
            other = normalize_decimal(row.get("andre_fradrag") or row.get("other_deductions") or 0) or 0.0
            result["gross_salary"] += gross
            result["net_salary"] += net
            result["tax"] += tax
            result["sh_period"] += sh
            result["sh_rest"] = sh_rest
            result["pension_employee"] += emp
            result["pension_employer"] += er
            result["pension_total"] += ptotal
            result["other_deductions"] += other

    if result["rows"]:
        result["rows"].sort(key=lambda r: month_sort_key(r.get("file") or ""))
        last_row = result["rows"][-1]
        result["a_indkomst_ytd"] = normalize_decimal(last_row.get("a_indkomst_ytd") or last_row.get("brutto_ytd") or 0) or 0.0
        result["am_grundlag_ytd"] = normalize_decimal(last_row.get("am_grundlag_ytd") or 0) or 0.0
        result["skattebelob_ytd"] = normalize_decimal(last_row.get("skattebelob_ytd") or 0) or 0.0
        result["pension_employee_ytd"] = normalize_decimal(last_row.get("pension_employee_ytd") or 0) or 0.0
        result["pension_employer_ytd"] = normalize_decimal(last_row.get("pension_employer_ytd") or 0) or 0.0
        result["pension_total_ytd"] = normalize_decimal(last_row.get("pension_total_ytd") or 0) or 0.0
        arbejdstimer_ytd = 0.0
        has_ytd_hours = False
        if last_row.get("arbejdstimer_ytd") not in (None, ""):
            arbejdstimer_ytd = normalize_decimal(last_row.get("arbejdstimer_ytd")) or 0.0
            has_ytd_hours = True
        result["arbejdstimer_ytd"] = arbejdstimer_ytd
        result["payslip_total_hours_ytd"] = arbejdstimer_ytd
        result["payslip_total_hours_source"] = "ytd" if has_ytd_hours else "monthly"
        result["payslip_total_hours"] = arbejdstimer_ytd if has_ytd_hours else result["work_hours"] + result["sick_hours"]
    return result


def reconcile(minuba: Dict[str, float], payslip: Dict[str, Any], hourly_rate: float) -> Dict[str, Any]:
    minuba_total = minuba["work_hours"] + minuba["sick_hours"]
    payslip_total = round(payslip["payslip_total_hours"], 2)
    hour_diff = round(minuba_total - payslip_total, 2)
    money_diff = round(hour_diff * hourly_rate, 2)

    expected_gross_minuba = round(minuba_total * hourly_rate, 2)
    expected_gross_payslip = round(payslip_total * hourly_rate, 2)
    gross_diff = round(payslip["gross_salary"] - expected_gross_minuba, 2)

    if hour_diff > 0:
        status = "De skylder dig"
        conclusion = (
            f"Minuba viser {minuba_total:.2f} betalte timer i alt, mens lønsedlen viser {payslip_total:.2f}. "
            f"Der mangler derfor {hour_diff:.2f} timer, svarende til {money(money_diff)} kr. før skat og fradrag."
        )
    elif hour_diff < 0:
        status = "Du skylder dem"
        conclusion = (
            f"Lønsedlen viser {payslip_total:.2f} betalte timer i alt, mens Minuba viser {minuba_total:.2f}. "
            f"Der er derfor {abs(hour_diff):.2f} timer for meget, svarende til {money(abs(money_diff))} kr. før skat og fradrag."
        )
    else:
        status = "Timerne matcher"
        conclusion = f"Minuba og lønsedlens betalte timer matcher præcist: {minuba_total:.2f} timer."

    summary = (
        f"Minuba arbejdstimer: {minuba['work_hours']:.2f}. "
        f"Minuba sygetimer: {minuba['sick_hours']:.2f}. "
        f"Ferie-timer er ikke medregnet. "
        f"Lønsedlens betalte timer: {payslip_total:.2f} ({payslip['payslip_total_hours_source']}). "
        f"Lønsedlens arbejdstimer: {payslip['work_hours']:.2f}. "
        f"Lønsedlens sygetimer beregnet fra dage: {payslip['sick_hours']:.2f}. "
        f"SH i perioden: {payslip['sh_period']:.2f}. "
        f"SH rest: {payslip['sh_rest']:.2f}. "
        f"Skat: {payslip['tax']:.2f}. "
        f"Medarbejderpension: {payslip['pension_employee']:.2f}. "
        f"Arbejdsgiverpension: {payslip['pension_employer']:.2f}. "
        f"Pension i alt: {payslip['pension_total']:.2f}."
    )

    return {
        "status": status,
        "minuba_work_hours": round(minuba["work_hours"], 2),
        "minuba_sick_hours": round(minuba["sick_hours"], 2),
        "minuba_vacation_hours": round(minuba["vacation_hours"], 2),
        "minuba_total_hours": minuba_total,
        "payslip_work_hours": round(payslip["work_hours"], 2),
        "payslip_sick_hours": round(payslip["sick_hours"], 2),
        "payslip_total_hours": payslip_total,
        "payslip_total_hours_ytd": round(payslip["payslip_total_hours_ytd"], 2),
        "payslip_total_hours_source": payslip["payslip_total_hours_source"],
        "hour_diff": hour_diff,
        "money_diff": money_diff,
        "expected_gross_minuba": expected_gross_minuba,
        "expected_gross_payslip": expected_gross_payslip,
        "gross_salary": round(payslip["gross_salary"], 2),
        "gross_diff": gross_diff,
        "net_salary": round(payslip["net_salary"], 2),
        "tax": round(payslip["tax"], 2),
        "a_indkomst_ytd": round(payslip["a_indkomst_ytd"], 2),
        "am_grundlag_ytd": round(payslip["am_grundlag_ytd"], 2),
        "skattebelob_ytd": round(payslip["skattebelob_ytd"], 2),
        "sh_period": round(payslip["sh_period"], 2),
        "sh_rest": round(payslip["sh_rest"], 2),
        "pension_employee": round(payslip["pension_employee"], 2),
        "pension_employer": round(payslip["pension_employer"], 2),
        "pension_total": round(payslip["pension_total"], 2),
        "pension_employee_ytd": round(payslip["pension_employee_ytd"], 2),
        "pension_employer_ytd": round(payslip["pension_employer_ytd"], 2),
        "pension_total_ytd": round(payslip["pension_total_ytd"], 2),
        "other_deductions": round(payslip["other_deductions"], 2),
        "summary": summary,
        "conclusion": conclusion,
    }


def write_csv(data: Dict[str, Any], path: Path):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(data.keys()))
        writer.writeheader()
        writer.writerow(data)


def write_json(data: Dict[str, Any], path: Path):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def make_pdf(data: Dict[str, Any], path: Path, hourly_rate: float):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("titlex", fontName="Helvetica-Bold", fontSize=22, textColor=WHITE, alignment=TA_LEFT, leading=24))
    styles.add(ParagraphStyle("subx", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#aab4c8"), alignment=TA_LEFT, leading=12))
    styles.add(ParagraphStyle("headx", fontName="Helvetica-Bold", fontSize=11, textColor=ACCENT, leading=13, spaceAfter=3))
    styles.add(ParagraphStyle("bodyx", fontName="Helvetica", fontSize=9.5, textColor=TEXT, leading=14))
    styles.add(ParagraphStyle("smallx", fontName="Helvetica", fontSize=8.5, textColor=MID_GRAY, leading=12))
    styles.add(ParagraphStyle("verdictx", fontName="Helvetica-Bold", fontSize=26, textColor=WHITE, alignment=TA_CENTER, leading=30))
    styles.add(ParagraphStyle("verdicts", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#d0d8e8"), alignment=TA_CENTER, leading=12))

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=10 * mm, bottomMargin=12 * mm)
    story = []

    header = Table([
        [Paragraph("Løncheck Rapport", styles["titlex"]), Paragraph(datetime.today().strftime("Genereret %d/%m/%Y"), styles["subx"])],
    ], colWidths=[120 * mm, 63 * mm])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY_DARK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 7 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7 * mm),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    story.append(header)
    story.append(Spacer(1, 5 * mm))

    verdict_color = RED if data["hour_diff"] < 0 else GREEN if data["hour_diff"] > 0 else ACCENT
    verdict_amount = f"{money(abs(data['money_diff']))} kr." if data["hour_diff"] != 0 else "0,00 kr."
    verdict = Table([
        [Paragraph(data["status"], styles["verdicts"])],
        [Paragraph(verdict_amount, styles["verdictx"])],
        [Paragraph("Difference baseret på timer og timeløn", styles["verdicts"])],
    ], colWidths=[183 * mm])
    verdict.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), verdict_color),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    story.append(verdict)
    story.append(Spacer(1, 5 * mm))

    def stat_cell(label, value, alert=False):
        val_style = ParagraphStyle("valx", fontName="Helvetica-Bold", fontSize=13, textColor=RED if alert else TEXT, leading=15)
        return [Paragraph(label, ParagraphStyle("lblx", fontName="Helvetica-Bold", fontSize=9, textColor=MID_GRAY, leading=11)), Paragraph(value, val_style)]

    stats = [
        [stat_cell("MINUBA ARBEJDSTIMER", money(data["minuba_work_hours"])), stat_cell("LØNSEDDEL ARBEJDSTIMER", money(data["payslip_work_hours"]))],
        [stat_cell("MINUBA SYGETIMER", money(data["minuba_sick_hours"])), stat_cell("LØNSEDDEL SYGETIMER", money(data["payslip_sick_hours"]))],
        [stat_cell("MINUBA FERIE-TIMER", money(data["minuba_vacation_hours"])), stat_cell("LØNSEDDEL TOTAL BETALTE TIMER", money(data["payslip_total_hours"]))],
        [stat_cell("FORSKEL I TIMER", money(data["hour_diff"]), True), stat_cell("FORSKEL I KRONER", f"{money(data['money_diff'])} kr.", True)],
    ]
    stat_tables = []
    for row in stats:
        inner_row = []
        for label, value in row:
            inner = Table([[label], [value]], colWidths=[88 * mm])
            inner.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
                ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5 * mm),
                ("ROUNDEDCORNERS", [4, 4, 4, 4]),
            ]))
            inner_row.append(inner)
        stat_tables.append(inner_row)
    stats_tbl = Table(stat_tables, colWidths=[91.5 * mm, 91.5 * mm])
    stats_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
    ]))
    story.append(stats_tbl)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("LØNDETALJER", styles["headx"]))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT, spaceAfter=3 * mm))
    lon_data = [
        [Paragraph("POST", ParagraphStyle("p1", fontName="Helvetica-Bold", fontSize=9.5, textColor=WHITE)), Paragraph("BELØB", ParagraphStyle("p1", fontName="Helvetica-Bold", fontSize=9.5, textColor=WHITE))],
        ["Timeløn", f"{money(hourly_rate)} kr."],
        ["Forventet bruttoløn ud fra Minuba", f"{money(data['expected_gross_minuba'])} kr."],
        ["Forventet bruttoløn ud fra lønseddel", f"{money(data['expected_gross_payslip'])} kr."],
        ["Lønseddel brutto", f"{money(data['gross_salary'])} kr."],
        ["Lønseddel A-indkomst år til dato", f"{money(data['a_indkomst_ytd'])} kr."],
        ["Lønseddel AM-grundlag år til dato", f"{money(data['am_grundlag_ytd'])} kr."],
        ["Lønseddel netto", f"{money(data['net_salary'])} kr."],
        ["Skat", f"{money(abs(data['tax']))} kr."],
        ["A-skat samlet år til dato", f"{money(abs(data['skattebelob_ytd']))} kr."],
        ["SH / Opsparing i perioden", f"{money(data['sh_period'])} kr."],
        ["SH rest", f"{money(data['sh_rest'])} kr."],
        ["Medarbejderpension", f"{money(data['pension_employee'])} kr."],
        ["Arbejdsgiverpension", f"{money(data['pension_employer'])} kr."],
        ["Pension i alt", f"{money(data['pension_total'])} kr."],
        ["Medarbejderpension år til dato", f"{money(data['pension_employee_ytd'])} kr."],
        ["Arbejdsgiverpension år til dato", f"{money(data['pension_employer_ytd'])} kr."],
        ["Pension i alt år til dato", f"{money(data['pension_total_ytd'])} kr."],
        ["Andre fradrag i alt", f"{money(data['other_deductions'])} kr."],
    ]
    lon_tbl = Table(lon_data, colWidths=[110 * mm, 73 * mm])
    lon_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_MID),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dde2ec")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT),
        ("FONTNAME", (1, 4), (1, 4), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 4), (1, 4), YELLOW),
        ("TEXTCOLOR", (1, 5), (1, 5), YELLOW),
        ("TEXTCOLOR", (1, 6), (1, 6), YELLOW),
    ]))
    story.append(lon_tbl)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("FORKLARING", styles["headx"]))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT, spaceAfter=3 * mm))
    rules = [
        ("Medregnet:", "Arbejdstimer og sygetimer fra Minuba."),
        ("Ikke medregnet:", "Ferietimer, da ferie er selvbetalt."),
        ("Sygedage omregnet:", "Fredage tæller 7,0 timer. Øvrige dage tæller 7,5 timer."),
        ("Hovedregel:", "Lønseddel total > Minuba total = du skylder. Minuba total > lønseddel total = de skylder dig."),
        ("SH / Opsparing:", "Vises som info i rapporten."),
        ("SH rest:", "Viser restsaldo, hvis den findes i sidste lønseddel."),
        ("Andre fradrag:", "Viser den samlede års-sum af fradrag fra lønsedlen.")
    ]
    rule_rows = [[Paragraph(k, ParagraphStyle("rk", fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT)), Paragraph(v, styles["bodyx"])] for k, v in rules]
    rule_tbl = Table(rule_rows, colWidths=[38 * mm, 145 * mm])
    rule_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(rule_tbl)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("KONKLUSION", styles["headx"]))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT, spaceAfter=3 * mm))
    story.append(Paragraph(data["conclusion"], styles["bodyx"]))
    story.append(Spacer(1, 4 * mm))

    footer = Table([
        [Paragraph("Rapporten er genereret automatisk af Løncheck — github.com/BenkaDk/Loen-Check", styles["smallx"]), Paragraph(datetime.today().strftime("%d/%m/%Y"), styles["smallx"])],
    ], colWidths=[155 * mm, 28 * mm])
    footer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(footer)

    doc.build(story)


def main():
    parser = argparse.ArgumentParser(description="Aarsbaseret loencheck")
    parser.add_argument("--minuba-csv", required=True)
    parser.add_argument("--payslip-csv", required=True)
    parser.add_argument("--hourly-rate", type=float, required=True)
    parser.add_argument("--out-csv", default="annual_reconciliation_report.csv")
    parser.add_argument("--out-json", default="annual_reconciliation_report.json")
    parser.add_argument("--out-pdf", default="annual_reconciliation_report.pdf")
    args = parser.parse_args()

    minuba_path = Path(args.minuba_csv)
    payslip_path = Path(args.payslip_csv)
    for csv_path, label in ((minuba_path, "Minuba"), (payslip_path, "Payslip")):
        if not csv_path.is_file():
            parser.error(f"{label} CSV not found: {csv_path}")

    minuba = load_minuba_csv(minuba_path)
    payslip = load_payslip_csv(payslip_path)
    data = reconcile(minuba, payslip, args.hourly_rate)

    Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_pdf).parent.mkdir(parents=True, exist_ok=True)

    write_csv(data, Path(args.out_csv))
    write_json(data, Path(args.out_json))
    make_pdf(data, Path(args.out_pdf), args.hourly_rate)

    print("Færdig.")
    print(f"CSV gemt: {args.out_csv}")
    print(f"JSON gemt: {args.out_json}")
    print(f"PDF gemt: {args.out_pdf}")
    print(f"Minuba total betalte timer: {data['minuba_total_hours']:.2f}")
    print(f"Lønseddel total betalte timer: {data['payslip_total_hours']:.2f}")
    print(f"Forskel timer: {data['hour_diff']:.2f}")
    print(f"Forskel kroner: {data['money_diff']:.2f}")


if __name__ == "__main__":
    main()
