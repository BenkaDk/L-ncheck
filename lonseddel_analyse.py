#!/usr/bin/env python3
"""
lonseddel_analyse.py
--------------------
Læser PDF-lønsedler fra en mappe og udregner:
  - Samlede arbejdstimer
  - Samlede sygedage
  - Samlede feriedage

Krav:
    pip install pdfplumber rich

Brug:
    python lonseddel_analyse.py --mappe ./lønsedler
    python lonseddel_analyse.py --mappe ./lønsedler --debug
"""

import argparse
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

try:
    import pdfplumber
except ImportError:
    sys.exit("Mangler pdfplumber. Installer med: pip install pdfplumber")

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None


# ---------------------------------------------------------------------------
# Dataklasse for én lønseddel
# ---------------------------------------------------------------------------
@dataclass
class Lonseddel:
    fil: str
    arbejdstimer: float = 0.0
    sygedage: float = 0.0
    feriedage: float = 0.0
    fejl: Optional[str] = None


# ---------------------------------------------------------------------------
# Mønstre til udtræk – tilpas til dit lønsystem
# ---------------------------------------------------------------------------
PATTERNS = {
    # Timer: fx "Arbejdstimer    160,00" eller "Timer i alt: 37,50"
    "arbejdstimer": [
        r"(?:arbejdstimer?|timer\s+i\s+alt|normaltimer|løntimer)[\s:]*([\d]{1,4}[,.]\d{1,2})",
        r"(?:betalte\s+timer|antal\s+timer)[\s:]*([\d]{1,4}[,.]\d{1,2})",
        r"timer[\s:]+([\d]{1,4}[,.]\d{1,2})",
    ],
    # Sygefravær: fx "Sygedage  2" eller "Sygdom: 1,0"
    "sygedage": [
        r"(?:sygedage|sygefrav[æa]r|sygdom)[\s:]*([\d]{1,2}[,.]?\d{0,2})",
        r"(?:fravær\s+sygdom)[\s:]*([\d]{1,2}[,.]?\d{0,2})",
    ],
    # Ferie: fx "Feriedage   5" eller "Ferie afholdt: 2,0"
    "feriedage": [
        r"(?:feriedage|ferie\s+afholdt|afholdt\s+ferie|ferie)[\s:]*([\d]{1,2}[,.]?\d{0,2})",
        r"(?:optjent\s+ferie|feriefridage)[\s:]*([\d]{1,2}[,.]?\d{0,2})",
    ],
}


def dk_til_float(tekst: str) -> float:
    """Konverterer dansk talformat (1.234,56 eller 1234,56) til float."""
    tekst = tekst.replace(".", "").replace(",", ".")
    try:
        return float(tekst)
    except ValueError:
        return 0.0


def udtræk_værdi(tekst: str, kategori: str, debug: bool = False) -> float:
    """Prøver alle mønstre for kategorien og returnerer første match."""
    for mønster in PATTERNS[kategori]:
        match = re.search(mønster, tekst, re.IGNORECASE | re.MULTILINE)
        if match:
            if debug:
                print(f"  [{kategori}] Match med: {mønster!r} → {match.group(1)!r}")
            return dk_til_float(match.group(1))
    return 0.0


def læs_pdf(sti: Path, debug: bool = False) -> Lonseddel:
    """Udtrækker tekst fra PDF og finder relevante værdier."""
    seddel = Lonseddel(fil=sti.name)
    try:
        with pdfplumber.open(sti) as pdf:
            # Saml al tekst fra alle sider
            al_tekst = "\n".join(
                side.extract_text() or "" for side in pdf.pages
            )

        if debug:
            print(f"\n--- {sti.name} ---")
            print(al_tekst[:1500])
            print("---")

        seddel.arbejdstimer = udtræk_værdi(al_tekst, "arbejdstimer", debug)
        seddel.sygedage = udtræk_værdi(al_tekst, "sygedage", debug)
        seddel.feriedage = udtræk_værdi(al_tekst, "feriedage", debug)

    except Exception as exc:
        seddel.fejl = str(exc)

    return seddel


def analyser_mappe(mappe: Path, debug: bool = False) -> list[Lonseddel]:
    """Finder alle PDF-filer i mappen og analyserer dem."""
    pdf_filer = sorted(mappe.glob("*.pdf"))
    if not pdf_filer:
        sys.exit(f"Ingen PDF-filer fundet i: {mappe}")

    return [læs_pdf(f, debug) for f in pdf_filer]


def udskriv_resultater(sedler: list[Lonseddel]) -> None:
    """Printer en pæn oversigt med totaler."""
    total_timer = sum(s.arbejdstimer for s in sedler)
    total_sygdom = sum(s.sygedage for s in sedler)
    total_ferie = sum(s.feriedage for s in sedler)
    fejl_sedler = [s for s in sedler if s.fejl]

    if HAS_RICH:
        tabel = Table(
            title="📄 Lønseddel-analyse",
            box=box.ROUNDED,
            show_lines=True,
        )
        tabel.add_column("Fil", style="cyan", no_wrap=True)
        tabel.add_column("Arbejdstimer", justify="right", style="green")
        tabel.add_column("Sygedage", justify="right", style="yellow")
        tabel.add_column("Feriedage", justify="right", style="blue")
        tabel.add_column("Status", justify="center")

        for s in sedler:
            if s.fejl:
                tabel.add_row(s.fil, "–", "–", "–", f"[red]FEJL: {s.fejl}[/red]")
            else:
                tabel.add_row(
                    s.fil,
                    f"{s.arbejdstimer:.2f}",
                    f"{s.sygedage:.1f}",
                    f"{s.feriedage:.1f}",
                    "[green]OK[/green]",
                )

        # Totallinje
        tabel.add_row(
            "[bold]TOTAL[/bold]",
            f"[bold green]{total_timer:.2f}[/bold green]",
            f"[bold yellow]{total_sygdom:.1f}[/bold yellow]",
            f"[bold blue]{total_ferie:.1f}[/bold blue]",
            "",
        )

        console.print()
        console.print(tabel)
        console.print(
            Panel(
                f"[green]Arbejdstimer i alt:[/green]  {total_timer:.2f} timer\n"
                f"[yellow]Sygedage i alt:[/yellow]      {total_sygdom:.1f} dage\n"
                f"[blue]Feriedage i alt:[/blue]     {total_ferie:.1f} dage\n"
                f"Antal lønsedler:        {len(sedler)}",
                title="📊 Samlet oversigt",
                border_style="bright_white",
            )
        )

        if fejl_sedler:
            console.print(f"[red]⚠️  {len(fejl_sedler)} seddel(er) kunne ikke læses korrekt.[/red]")

    else:
        # Fallback uden Rich
        print("\n=== Lønseddel-analyse ===")
        print(f"{'Fil':<35} {'Timer':>10} {'Sygdage':>10} {'Feriedage':>10}")
        print("-" * 70)
        for s in sedler:
            if s.fejl:
                print(f"{s.fil:<35} FEJL: {s.fejl}")
            else:
                print(f"{s.fil:<35} {s.arbejdstimer:>10.2f} {s.sygedage:>10.1f} {s.feriedage:>10.1f}")
        print("-" * 70)
        print(f"{'TOTAL':<35} {total_timer:>10.2f} {total_sygdom:>10.1f} {total_ferie:>10.1f}")
        print(f"\nSamlet: {total_timer:.2f} timer  |  {total_sygdom:.1f} sygedage  |  {total_ferie:.1f} feriedage")


# ---------------------------------------------------------------------------
# Tip: Tilpas mønstre til dit lønsystem
# ---------------------------------------------------------------------------
TILPASNINGS_GUIDE = """
TILPASNING AF MØNSTRE
=====================
Åbn filen og find ordbogen PATTERNS øverst.
Hvert mønster er et regulært udtryk (regex) der matcher tekst på din lønseddel.

Eksempel – hvis din lønseddel skriver "Norm.timer: 162,00":
    Tilføj til arbejdstimer-listen:
        r"Norm\.timer[\s:]*([\d]{1,4}[,.]\d{1,2})"

Brug --debug flaget for at se den rå PDF-tekst og hvilke mønstre der matcher:
    python lonseddel_analyse.py --mappe ./lønsedler --debug
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Analyser PDF-lønsedler og summér timer, sygedage og feriedage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=TILPASNINGS_GUIDE,
    )
    parser.add_argument(
        "--mappe", "-m",
        default=".",
        help="Sti til mappen med PDF-lønsedler (standard: aktuel mappe)",
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Vis rå PDF-tekst og regex-matches for fejlsøgning",
    )
    args = parser.parse_args()

    mappe = Path(args.mappe).resolve()
    if not mappe.is_dir():
        sys.exit(f"Mappen findes ikke: {mappe}")

    sedler = analyser_mappe(mappe, debug=args.debug)
    udskriv_resultater(sedler)


if __name__ == "__main__":
    main()
