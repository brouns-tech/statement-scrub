"""Entirely fabricated demo input; suitable for tests and learning the review UI."""
from io import BytesIO
from reportlab.pdfgen import canvas


def demo_pdf() -> bytes:
    out = BytesIO()
    c = canvas.Canvas(out, invariant=1)
    c.setTitle("Fabricated demo input")
    c.setFont('Helvetica', 12)
    c.drawString(40, 800, "DEMO - FICTIEVE BRONGEGEVENS")
    for y, label, value in [(760, 'Rekeninghouder', 'DEMO PERSOON'),
                            (735, 'Rekening', 'NL00 DEMO 0000 0000 00'),
                            (705, 'Beginsaldo', '1.000,00')]:
        c.drawString(40, y, label)
        c.drawString(240, y, value)
    c.drawString(40, 660, 'Datum')
    c.drawString(150, 660, 'Omschrijving')
    c.drawString(420, 660, 'Bedrag')
    c.drawString(40, 630, '03-02-2025')
    c.drawString(150, 630, 'DEMO BETALING')
    c.drawString(420, 630, '-100,00')
    c.drawString(40, 590, 'Eindsaldo')
    c.drawString(240, 590, '900,00')
    c.save()
    return out.getvalue()
