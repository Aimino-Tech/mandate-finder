import csv
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from market_intelligence.models import TrendReport


def report_to_csv(report: TrendReport) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Category", "Date", "Value", "Moving Avg", "Growth Rate", "Direction"])
    w.writerow([])
    for series in report.top_growing_roles + report.industry_pulse:
        for p in series.points:
            w.writerow([series.category, p.date.isoformat(), p.value, round(p.moving_avg, 2) if p.moving_avg is not None else "", series.growth_rate, series.direction])
        w.writerow([])
    if report.early_warnings:
        w.writerow(["Early Warnings"])
        w.writerow(["Company", "Signal Type", "Headline", "Date", "Confidence"])
        for s in report.early_warnings:
            w.writerow([s.company, s.signal_type, s.headline, s.detected_at.date().isoformat(), s.confidence])
    return out.getvalue()


def _build_pdf(report: TrendReport) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm)
    styles = getSampleStyleSheet()
    heading = ParagraphStyle("SectionHead", parent=styles["Heading2"], spaceBefore=16, spaceAfter=6)
    normal = styles["Normal"]
    els: list[object] = []
    els.append(Paragraph("Market Intelligence Report", ParagraphStyle("ReportTitle", parent=styles["Title"], spaceAfter=12)))
    els.append(Paragraph(f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M')}", normal))
    els.append(Spacer(1, 6 * mm))
    if report.top_growing_roles:
        els.append(Paragraph("Top Growing Roles", heading))
        td = [["Role", "Growth Rate", "Direction", "Total Postings"]]
        for s in report.top_growing_roles[:10]:
            td.append([s.category.replace("_", " ").title(), f"{s.growth_rate * 100:+.1f}%", s.direction, str(int(sum(p.value for p in s.points)))])
        t = Table(td, colWidths=[100, 60, 60, 80])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b5797")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (-1, -1), "CENTER"), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
        els.append(t)
    if report.industry_pulse:
        els.append(Paragraph("Industry Pulse", heading))
        for s in report.industry_pulse[:5]:
            els.append(Paragraph(f"<b>{s.category.title()}</b> \u2014 {s.growth_rate * 100:+.1f}% ({s.direction})", normal))
    if report.early_warnings:
        els.append(Paragraph("Early Warnings", heading))
        wd = [["Company", "Type", "Headline", "Confidence"]]
        for sig in report.early_warnings:
            wd.append([sig.company, sig.signal_type, sig.headline, f"{sig.confidence:.0%}"])
        wt = Table(wd, colWidths=[70, 60, 180, 50])
        wt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9534f")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
        els.append(wt)
    if report.user_insights:
        els.append(Paragraph("Your Insights", heading))
        for ins in report.user_insights:
            els.append(Paragraph(f"\u2022 {ins}", normal))
    doc.build(els)
    return buf.getvalue()


def export_report(report: TrendReport, fmt: str = "csv") -> bytes:
    if fmt == "csv":
        return report_to_csv(report).encode("utf-8")
    if fmt == "pdf":
        return _build_pdf(report)
    raise ValueError(f"Unsupported format: {fmt}")
