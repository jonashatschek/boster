"""Generates small but real PDFs laid out like annual reports, for API tests."""

import pymupdf

DEFAULT_KEY_FIGURES = [
    ("Skuldsättning, kr/kvm", "4 000", "4 200"),
    ("Sparande, kr/kvm", "90", "120"),
    ("Räntekänslighet, %", "12", "11"),
]

DEFAULT_STATEMENTS = [
    ("Nettoomsättning", "5 000 000", "4 800 000"),
    ("Rörelseresultat", "900 000", "800 000"),
    ("Räntekostnader och liknande resultatposter", "-700 000", "-600 000"),
    ("Årets resultat", "200 000", "200 000"),
    ("Kassa och bank", "1 000 000", "900 000"),
    ("Summa tillgångar", "90 000 000", "91 000 000"),
    ("Summa eget kapital", "50 000 000", "49 800 000"),
    ("Långfristiga skulder", "", ""),
    ("Skulder till kreditinstitut", "40 000 000", "41 000 000"),
]


def make_report_pdf(name: str = "Brf Provhuset", organisation_number: str = "769600-1234",
                    period: tuple[str, str] = ("2025-01-01", "2025-12-31"), previous_period_end: str = "2024-12-31",
                    key_figures: list[tuple[str, str, str]] = DEFAULT_KEY_FIGURES,
                    statements: list[tuple[str, str, str]] = DEFAULT_STATEMENTS,
                    land: str = "Fastigheten innehas med tomträtt.") -> bytes:
    """A report whose fiscal year is `period`, with one comparison year in the tables."""
    current_year, previous_year = period[1][:4], previous_period_end[:4]
    document = pymupdf.open()
    cover = document.new_page()
    cover.insert_text((60, 80), f"Årsredovisning för {name}", fontsize=12)
    cover.insert_text((60, 100), organisation_number, fontsize=10)
    cover.insert_text((60, 120), f"Räkenskapsåret {period[0]} - {period[1]}", fontsize=10)
    cover.insert_text((60, 140), land, fontsize=10)

    def table(page, y, rows):
        for label, *values in rows:
            page.insert_text((60, y), label, fontsize=9)
            for x_right, value in zip((360, 430), values):
                page.insert_text((x_right - len(value) * 4.6, y), value, fontsize=9)
            y += 14

    key_figure_page = document.new_page()
    key_figure_page.insert_text((60, 60), "Flerårsöversikt", fontsize=11)
    table(key_figure_page, 80, [("", current_year, previous_year), *key_figures])
    statement_page = document.new_page()
    statement_page.insert_text((60, 60), "Resultaträkning och balansräkning", fontsize=11)
    table(statement_page, 80, [("", period[1], previous_period_end), *statements])
    content = document.tobytes()
    document.close()
    return content
