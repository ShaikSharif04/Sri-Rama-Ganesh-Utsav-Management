"""Sri Rama Ganesh Utsav Association – Nagiligond (Vill), Khammam.

A small Flask + SQLite application for festival chanda and expense records.
"""
from __future__ import annotations

import os
import sqlite3
from io import BytesIO
from datetime import datetime
from functools import wraps
from pathlib import Path
from urllib.parse import quote

from flask import (
    Flask, flash, g, jsonify, redirect, render_template, request,
    session, url_for, send_file,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)
DEFAULT_DB = INSTANCE_DIR / "ganesh.db"
DB_PATH = os.environ.get("DATABASE_PATH", str(DEFAULT_DB))

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "change-this-secret-before-deployment"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
)

APP_NAME = "Sri Rama Ganesh Utsav Association"
APP_LOCATION = "Nagiligond (Vill), Khammam"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            amount_received REAL NOT NULL DEFAULT 0 CHECK(amount_received >= 0),
            payable_amount REAL NOT NULL DEFAULT 0 CHECK(payable_amount >= 0),
            payment_status TEXT NOT NULL DEFAULT 'paid' CHECK(payment_status IN ('paid', 'pending')),
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_for TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            expense_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chanda_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            amount_received REAL NOT NULL DEFAULT 0,
            payment_status TEXT NOT NULL DEFAULT 'paid',
            action TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            occurred_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS expense_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_id INTEGER,
            expense_for TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            expense_date TEXT NOT NULL,
            action TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
        """
    )
    # Migrate databases created by earlier app versions without losing records.
    person_columns = {row["name"] for row in db.execute("PRAGMA table_info(persons)").fetchall()}
    if "payment_status" not in person_columns:
        db.execute("ALTER TABLE persons ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'paid'")
        db.execute("UPDATE persons SET payment_status = CASE WHEN COALESCE(payable_amount, 0) > 0 THEN 'pending' ELSE 'paid' END")
    # Seed one baseline history snapshot for each existing person record. This preserves
    # the records already in V1/V2; changes from this version onward are logged separately.
    db.execute(
        """INSERT INTO chanda_history
           (person_id, name, phone, amount_received, payment_status, action, notes, occurred_at)
           SELECT p.id, p.name, p.phone, p.amount_received, p.payment_status,
                  'existing_record', p.notes, COALESCE(p.created_at, datetime('now'))
           FROM persons p
           WHERE NOT EXISTS (
               SELECT 1 FROM chanda_history h WHERE h.person_id = p.id
           )"""
    )
    db.execute(
        """INSERT INTO expense_history
           (expense_id, expense_for, description, amount, expense_date, action, occurred_at)
           SELECT e.id, e.expense_for, e.description, e.amount, e.expense_date,
                  'existing_record', COALESCE(e.created_at, datetime('now'))
           FROM expenses e
           WHERE NOT EXISTS (
               SELECT 1 FROM expense_history h WHERE h.expense_id = e.id
           )"""
    )
    default_username = os.environ.get("ADMIN_USERNAME", "admin")
    default_password = os.environ.get("ADMIN_PASSWORD", "Ganesh@2026")
    existing = db.execute("SELECT id FROM users WHERE username = ?", (default_username,)).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (default_username, generate_password_hash(default_password), datetime.now().isoformat(timespec="seconds")),
        )
    db.commit()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def normalize_indian_phone(raw: str) -> str | None:
    """Return a canonical 10-digit or 91-prefixed mobile number, or None."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return digits
    return None


def money(value) -> str:
    try:
        return f"₹{float(value):,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "₹0"


def record_chanda_history(db: sqlite3.Connection, person, action: str) -> None:
    """Append an immutable snapshot so edits and deletions remain in the audit export."""
    db.execute(
        """INSERT INTO chanda_history
           (person_id, name, phone, amount_received, payment_status, action, notes, occurred_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (person["id"], person["name"], person["phone"], person["amount_received"],
         person["payment_status"], action, person["notes"], datetime.now().isoformat(timespec="seconds")),
    )


def record_expense_history(db: sqlite3.Connection, expense, action: str) -> None:
    """Keep an immutable audit snapshot when an expense is created or deleted."""
    db.execute(
        """INSERT INTO expense_history
           (expense_id, expense_for, description, amount, expense_date, action, occurred_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (expense["id"], expense["expense_for"], expense["description"], expense["amount"],
         expense["expense_date"], action, datetime.now().isoformat(timespec="seconds")),
    )


def build_export_dataset(db: sqlite3.Connection) -> dict:
    """Read every stored member, chanda, audit-history and expense record."""
    people = db.execute("SELECT * FROM persons ORDER BY created_at ASC, id ASC").fetchall()
    expenses = db.execute("SELECT * FROM expenses ORDER BY expense_date ASC, id ASC").fetchall()
    history = db.execute("SELECT * FROM chanda_history ORDER BY occurred_at ASC, id ASC").fetchall()
    expense_history = db.execute("SELECT * FROM expense_history ORDER BY occurred_at ASC, id ASC").fetchall()

    grouped = {}
    for person in people:
        phone = person["phone"]
        item = grouped.get(phone)
        if item is None:
            item = {
                "name": person["name"], "phone": phone, "paid": 0.0, "pending": 0.0,
                "entries": 0, "latest": person["created_at"],
            }
            grouped[phone] = item
        # Use the latest encountered name and date for the directory entry.
        item["name"] = person["name"]
        item["entries"] += 1
        item["latest"] = max(item["latest"], person["created_at"])
        if person["payment_status"] == "paid":
            item["paid"] += float(person["amount_received"] or 0)
        else:
            item["pending"] += float(person["amount_received"] or 0)
    members = sorted(grouped.values(), key=lambda x: x["name"].casefold())
    total_paid = sum(float(p["amount_received"] or 0) for p in people if p["payment_status"] == "paid")
    total_pending = sum(float(p["amount_received"] or 0) for p in people if p["payment_status"] == "pending")
    total_expenses = sum(float(e["amount"] or 0) for e in expenses)
    return {
        "people": people, "members": members, "expenses": expenses, "history": history,
        "expense_history": expense_history,
        "summary": {
            "unique_members": len(members), "chanda_entries": len(people),
            "chanda_paid": total_paid, "chanda_pending": total_pending,
            "expenses": total_expenses, "balance": total_paid - total_expenses,
        },
    }


def create_excel_export(dataset: dict) -> BytesIO:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    summary_ws = wb.active
    summary_ws.title = "Financial Summary"
    purple = "4B176D"
    light_purple = "F0E5F8"
    white = "FFFFFF"
    thin_purple = Side(style="thin", color="E4D9EC")

    summary_ws.merge_cells("A1:B1")
    summary_ws["A1"] = f"{APP_NAME} - Complete Records Export"
    summary_ws["A1"].font = Font(bold=True, size=16, color=white)
    summary_ws["A1"].fill = PatternFill("solid", fgColor=purple)
    summary_ws["A1"].alignment = Alignment(vertical="center")
    summary_ws.row_dimensions[1].height = 30
    summary_rows = [
        ("Location", APP_LOCATION),
        ("Exported At", datetime.now().strftime("%d-%b-%Y %I:%M %p")),
        ("Unique Members", dataset["summary"]["unique_members"]),
        ("Chanda Entries", dataset["summary"]["chanda_entries"]),
        ("Total Chanda Paid (INR)", dataset["summary"]["chanda_paid"]),
        ("Total Chanda Pending (INR)", dataset["summary"]["chanda_pending"]),
        ("Total Expenses (INR)", dataset["summary"]["expenses"]),
        ("Remaining Paid Chanda Balance (INR)", dataset["summary"]["balance"]),
    ]
    for row in summary_rows:
        summary_ws.append(row)
    summary_ws.column_dimensions["A"].width = 38
    summary_ws.column_dimensions["B"].width = 34
    for row in summary_ws.iter_rows(min_row=2, max_row=summary_ws.max_row, min_col=1, max_col=2):
        row[0].font = Font(bold=True, color=purple)
        row[0].fill = PatternFill("solid", fgColor=light_purple)
        row[1].alignment = Alignment(vertical="center")
        for cell in row:
            cell.border = Border(bottom=thin_purple)
    for r in range(6, 10):
        summary_ws.cell(r, 2).number_format = '"INR "#,##0.00'

    def excel_safe(value):
        # Excel interprets text beginning with these characters as formulas.
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
            return "'" + value
        return value

    def add_sheet(title, headers, rows, widths, money_cols=()):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True, color=white)
            cell.fill = PatternFill("solid", fgColor=purple)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[1].height = 30
        for row in rows:
            ws.append([excel_safe(value) for value in row])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for idx, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(idx)].width = width
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = Border(bottom=thin_purple)
            for col in money_cols:
                ws.cell(row[0].row, col).number_format = '"INR "#,##0.00'
        return ws

    member_rows = [
        [i, m["name"], m["phone"], m["paid"], m["pending"], m["entries"], m["latest"]]
        for i, m in enumerate(dataset["members"], start=1)
    ]
    member_ws = add_sheet("Member Directory", ["S.No.", "Member Name", "Phone Number", "Paid Chanda (INR)", "Pending Chanda (INR)", "Chanda Entries", "Latest Record"], member_rows, [9, 25, 18, 20, 22, 16, 22], (4, 5))
    member_total_row = member_ws.max_row + 1
    member_ws.cell(member_total_row, 2, "TOTAL")
    member_ws.cell(member_total_row, 4, f"=SUM(D2:D{member_total_row-1})")
    member_ws.cell(member_total_row, 5, f"=SUM(E2:E{member_total_row-1})")
    for cell in member_ws[member_total_row]:
        cell.font = Font(bold=True, color=white)
        cell.fill = PatternFill("solid", fgColor=purple)
    member_ws.cell(member_total_row, 4).number_format = '"INR "#,##0.00'
    member_ws.cell(member_total_row, 5).number_format = '"INR "#,##0.00'

    contribution_rows = []
    for index, person in enumerate(dataset["people"], start=1):
        is_paid = person["payment_status"] == "paid"
        contribution_rows.append([
            index, person["name"], person["phone"],
            float(person["amount_received"] or 0) if is_paid else 0,
            float(person["amount_received"] or 0) if not is_paid else 0,
            person["created_at"], person["payment_status"].title(),
        ])
    contribution_ws = add_sheet(
        "Member Contributions",
        ["S.No.", "Member Name", "Phone Number", "Paid Chanda (INR)", "Pending Chanda (INR)", "Contribution Date", "Status"],
        contribution_rows,
        [9, 25, 18, 20, 22, 24, 14], (4, 5),
    )
    total_row = contribution_ws.max_row + 1
    contribution_ws.cell(total_row, 2, "TOTAL")
    contribution_ws.cell(total_row, 4, f"=SUM(D2:D{total_row-1})")
    contribution_ws.cell(total_row, 5, f"=SUM(E2:E{total_row-1})")
    for cell in contribution_ws[total_row]:
        cell.font = Font(bold=True, color=white)
        cell.fill = PatternFill("solid", fgColor=purple)
    contribution_ws.cell(total_row, 4).number_format = '"INR "#,##0.00'
    contribution_ws.cell(total_row, 5).number_format = '"INR "#,##0.00'

    chanda_rows = [[p["id"], p["name"], p["phone"], p["amount_received"], p["payment_status"].title(), p["notes"], p["created_at"], p["updated_at"]] for p in dataset["people"]]
    add_sheet("Chanda Records", ["Record ID", "Name", "Phone", "Amount (INR)", "Payment Status", "Notes", "Added At", "Last Updated"], chanda_rows, [12, 24, 18, 16, 17, 30, 23, 23], (4,))

    history_rows = [[h["id"], h["person_id"], h["name"], h["phone"], h["amount_received"], h["payment_status"].title(), h["action"].replace("_", " ").title(), h["notes"], h["occurred_at"]] for h in dataset["history"]]
    add_sheet("Chanda History", ["History ID", "Record ID", "Name", "Phone", "Amount (INR)", "Status", "Action", "Notes", "Date / Time"], history_rows, [12, 12, 24, 18, 16, 14, 20, 30, 23], (5,))

    expense_rows = [[e["id"], e["expense_for"], e["description"], e["expense_date"], e["amount"], e["created_at"]] for e in dataset["expenses"]]
    expense_ws = add_sheet("Expense Records", ["Expense ID", "Category", "Description", "Expense Date", "Amount (INR)", "Entered At"], expense_rows, [12, 20, 36, 16, 18, 23], (5,))
    expense_total_row = expense_ws.max_row + 1
    expense_ws.cell(expense_total_row, 2, "TOTAL EXPENSES")
    expense_ws.cell(expense_total_row, 5, f"=SUM(E2:E{expense_total_row-1})")
    for cell in expense_ws[expense_total_row]:
        cell.font = Font(bold=True, color=white)
        cell.fill = PatternFill("solid", fgColor=purple)
    expense_ws.cell(expense_total_row, 5).number_format = '"INR "#,##0.00'

    expense_history_rows = [[h["id"], h["expense_id"], h["expense_for"], h["description"], h["amount"], h["expense_date"], h["action"].replace("_", " ").title(), h["occurred_at"]] for h in dataset["expense_history"]]
    add_sheet("Expense History", ["History ID", "Expense ID", "Category", "Description", "Amount (INR)", "Expense Date", "Action", "Date / Time"], expense_history_rows, [12, 12, 20, 34, 18, 16, 18, 23], (5,))
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def create_pdf_export(dataset: dict) -> BytesIO:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from xml.sax.saxutils import escape

    output = BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(output, pagesize=page_size, rightMargin=13*mm, leftMargin=13*mm, topMargin=14*mm, bottomMargin=15*mm, title=f"{APP_NAME} - Complete Records")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="FestivalTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.HexColor("#4B176D"), alignment=TA_CENTER, spaceAfter=3))
    styles.add(ParagraphStyle(name="FestivalSub", parent=styles["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#65566F"), alignment=TA_CENTER, spaceAfter=10))
    styles.add(ParagraphStyle(name="SectionHead", parent=styles["Heading2"], fontSize=12, leading=15, textColor=colors.HexColor("#4B176D"), spaceBefore=8, spaceAfter=7))
    styles.add(ParagraphStyle(name="CellSmall", parent=styles["BodyText"], fontSize=7, leading=9, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="CellHead", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=colors.white, alignment=TA_LEFT))
    story = [
        Paragraph(escape(APP_NAME), styles["FestivalTitle"]),
        Paragraph(f"{escape(APP_LOCATION)} | Complete member, chanda, history and expense report", styles["FestivalSub"]),
        Paragraph(f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}", styles["FestivalSub"]),
        Paragraph("Financial Summary", styles["SectionHead"]),
    ]
    summary = dataset["summary"]
    summary_data = [
        ["Unique Members", str(summary["unique_members"]), "Chanda Entries", str(summary["chanda_entries"])],
        ["Total Chanda Paid", f"INR {summary['chanda_paid']:,.2f}", "Pending Chanda", f"INR {summary['chanda_pending']:,.2f}"],
        ["Total Expenses", f"INR {summary['expenses']:,.2f}", "Remaining Balance", f"INR {summary['balance']:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[42*mm, 45*mm, 42*mm, 45*mm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#F0E5F8")),
        ("BACKGROUND", (2,0), (2,-1), colors.HexColor("#F0E5F8")),
        ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#4B176D")),
        ("TEXTCOLOR", (2,0), (2,-1), colors.HexColor("#4B176D")),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"), ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8), ("GRID", (0,0), (-1,-1), .4, colors.HexColor("#DCCDE8")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    story.extend([summary_table, PageBreak()])

    def add_table_section(title, headers, rows, widths):
        story.append(Paragraph(title, styles["SectionHead"]))
        data = [[Paragraph(escape(str(h)), styles["CellHead"]) for h in headers]]
        for row in rows:
            data.append([Paragraph(escape("—" if value is None or value == "" else str(value)), styles["CellSmall"]) for value in row])
        if len(data) == 1:
            data.append([Paragraph("No records available", styles["CellSmall"])] + [""] * (len(headers)-1))
        table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#4B176D")),
            ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#DCD4E4")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#FAF7FC")]),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
            ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        story.append(table)

    add_table_section("Member Directory (grouped by phone number)",
        ["#", "Member", "Phone", "Paid Chanda", "Pending Chanda", "Entries", "Latest Record"],
        [[i, m["name"], m["phone"], f"INR {m['paid']:,.2f}", f"INR {m['pending']:,.2f}", m["entries"], m["latest"]] for i,m in enumerate(dataset["members"],1)],
        [9*mm, 43*mm, 31*mm, 31*mm, 34*mm, 17*mm, 34*mm])
    story.append(PageBreak())
    contribution_report_rows = []
    for i, person in enumerate(dataset["people"], 1):
        amount = float(person["amount_received"] or 0)
        is_paid = person["payment_status"] == "paid"
        contribution_report_rows.append([
            i, person["name"], person["phone"],
            f"INR {amount:,.2f}" if is_paid else "—",
            f"INR {amount:,.2f}" if not is_paid else "—",
            person["created_at"], person["payment_status"].title(),
        ])
    contribution_report_rows.append([
        "", "TOTAL", "", f"INR {summary['chanda_paid']:,.2f}",
        f"INR {summary['chanda_pending']:,.2f}", "", "",
    ])
    add_table_section("Member-wise Chanda Details (date and payment status)",
        ["#", "Member", "Phone", "Paid Chanda", "Pending Chanda", "Date", "Status"],
        contribution_report_rows,
        [9*mm, 39*mm, 29*mm, 29*mm, 31*mm, 35*mm, 20*mm])
    story.append(PageBreak())
    add_table_section("All Chanda Records", ["ID", "Name", "Phone", "Amount", "Status", "Notes", "Added", "Updated"],
        [[p["id"], p["name"], p["phone"], f"INR {float(p['amount_received']):,.2f}", p["payment_status"].title(), p["notes"], p["created_at"], p["updated_at"]] for p in dataset["people"]],
        [10*mm, 34*mm, 27*mm, 23*mm, 18*mm, 36*mm, 32*mm, 32*mm])
    story.append(PageBreak())
    add_table_section("Chanda Activity History", ["History ID", "Record ID", "Name", "Phone", "Amount", "Status", "Action", "Notes", "Date / Time"],
        [[h["id"], h["person_id"] or "—", h["name"], h["phone"], f"INR {float(h['amount_received']):,.2f}", h["payment_status"].title(), h["action"].replace("_", " ").title(), h["notes"], h["occurred_at"]] for h in dataset["history"]],
        [15*mm, 15*mm, 28*mm, 25*mm, 23*mm, 17*mm, 25*mm, 35*mm, 38*mm])
    story.append(PageBreak())
    expense_report_rows = [[e["id"], e["expense_for"], e["description"], e["expense_date"], f"INR {float(e['amount']):,.2f}", e["created_at"]] for e in dataset["expenses"]]
    expense_report_rows.append(["", "", "TOTAL EXPENSES", "", f"INR {summary['expenses']:,.2f}", ""])
    add_table_section("All Expense Records", ["ID", "Category", "Description", "Expense Date", "Amount", "Entered At"],
        expense_report_rows,
        [12*mm, 30*mm, 68*mm, 25*mm, 25*mm, 40*mm])
    story.append(PageBreak())
    add_table_section("Expense Activity History", ["History ID", "Expense ID", "Category", "Description", "Amount", "Expense Date", "Action", "Date / Time"],
        [[h["id"], h["expense_id"] or "—", h["expense_for"], h["description"], f"INR {float(h['amount']):,.2f}", h["expense_date"], h["action"].replace("_", " ").title(), h["occurred_at"]] for h in dataset["expense_history"]],
        [15*mm, 15*mm, 25*mm, 48*mm, 22*mm, 25*mm, 24*mm, 38*mm])

    def add_page_number(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#776A80"))
        canvas.drawString(13*mm, 8*mm, f"{APP_NAME} | {APP_LOCATION}")
        canvas.drawRightString(page_size[0] - 13*mm, 8*mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    output.seek(0)
    return output


@app.template_filter("money")
def money_filter(value):
    return money(value)


@app.template_filter("date_display")
def date_display(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except (TypeError, ValueError):
        return value or "—"


@app.context_processor
def inject_globals():
    return {"app_name": APP_NAME, "app_location": APP_LOCATION}


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            next_path = request.args.get("next", "")
            if next_path.startswith("/") and not next_path.startswith("//"):
                return redirect(next_path)
            return redirect(url_for("dashboard"))
        flash("Invalid username or password. Please try again.", "error")
    return render_template("login.html")


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def dashboard():
    db = get_db()
    stats = db.execute(
        """SELECT COUNT(*) AS total_people,
                  COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN amount_received ELSE 0 END), 0) AS total_chanda,
                  COALESCE(SUM(CASE WHEN payment_status = 'pending' THEN amount_received ELSE 0 END), 0) AS total_pending
           FROM persons"""
    ).fetchone()
    expense_total = db.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM expenses").fetchone()["total"]
    recent_people = db.execute("SELECT * FROM persons ORDER BY id DESC LIMIT 5").fetchall()
    recent_expenses = db.execute("SELECT * FROM expenses ORDER BY expense_date DESC, id DESC LIMIT 5").fetchall()
    return render_template(
        "dashboard.html", active="dashboard", stats=stats,
        expense_total=expense_total,
        balance=float(stats["total_chanda"]) - float(expense_total),
        recent_people=recent_people, recent_expenses=recent_expenses,
    )


@app.route("/persons", methods=["GET", "POST"])
@login_required
def persons():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone_input = request.form.get("phone", "").strip()
        phone = normalize_indian_phone(phone_input)
        notes = request.form.get("notes", "").strip()
        action = request.form.get("action", "pay")
        try:
            amount_received = float(request.form.get("amount_received", "0") or 0)
        except ValueError:
            flash("Enter a valid chanda amount.", "error")
            return redirect(url_for("persons"))
        if not name or not phone_input:
            flash("Name and phone number are required.", "error")
            return redirect(url_for("persons"))
        if not phone:
            flash("Enter a valid Indian mobile number (10 digits, or with +91 country code).", "error")
            return redirect(url_for("persons"))
        if amount_received < 0:
            flash("Amount cannot be negative.", "error")
            return redirect(url_for("persons"))
        if action not in {"pay", "pay_later"}:
            flash("Choose Pay or Pay Later to save this contributor.", "error")
            return redirect(url_for("persons"))
        status = "paid" if action == "pay" else "pending"
        now = datetime.now().isoformat(timespec="seconds")
        cursor = db.execute(
            """INSERT INTO persons (name, phone, amount_received, payable_amount, payment_status, notes, created_at, updated_at)
               VALUES (?, ?, ?, 0, ?, ?, ?, ?)""",
            (name, phone, amount_received, status, notes, now, now),
        )
        saved_person = db.execute("SELECT * FROM persons WHERE id = ?", (cursor.lastrowid,)).fetchone()
        record_chanda_history(db, saved_person, "created")
        db.commit()
        status_label = "Paid" if status == "paid" else "Pending"
        flash(f"{name} was saved successfully as {status_label}.", "success")
        return redirect(url_for("persons"))

    query = request.args.get("q", "").strip()
    if query:
        rows = db.execute(
            "SELECT * FROM persons WHERE name LIKE ? OR phone LIKE ? ORDER BY id DESC",
            (f"%{query}%", f"%{query}%"),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM persons ORDER BY id DESC").fetchall()
    all_people = db.execute("SELECT * FROM persons ORDER BY name COLLATE NOCASE").fetchall()
    return render_template("persons.html", active="persons", persons=rows, all_persons=all_people, query=query)


@app.post("/persons/<int:person_id>/update")
@login_required
def update_person(person_id: int):
    db = get_db()
    person = db.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone()
    if not person:
        flash("Person not found.", "error")
        return redirect(url_for("persons"))
    name = request.form.get("name", "").strip()
    phone_input = request.form.get("phone", "").strip()
    phone = normalize_indian_phone(phone_input)
    try:
        received = float(request.form.get("amount_received", "0") or 0)
    except ValueError:
        flash("Enter a valid chanda amount.", "error")
        return redirect(url_for("persons"))
    status = request.form.get("payment_status", "pending")
    if not name or not phone or received < 0 or status not in {"paid", "pending"}:
        flash("Please check the person details, phone number, amount and payment status.", "error")
        return redirect(url_for("persons"))
    db.execute(
        "UPDATE persons SET name=?, phone=?, amount_received=?, payable_amount=0, payment_status=?, updated_at=? WHERE id=?",
        (name, phone, received, status, datetime.now().isoformat(timespec="seconds"), person_id),
    )
    updated_person = db.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone()
    record_chanda_history(db, updated_person, "updated")
    db.commit()
    flash("Person details updated.", "success")
    return redirect(url_for("persons"))


@app.post("/persons/<int:person_id>/delete")
@login_required
def delete_person(person_id: int):
    db = get_db()
    person = db.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone()
    if person:
        record_chanda_history(db, person, "deleted")
        db.execute("DELETE FROM persons WHERE id = ?", (person_id,))
        db.commit()
    flash("Person record deleted; its history snapshot was retained.", "success")
    return redirect(url_for("persons"))


@app.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    db = get_db()
    if request.method == "POST":
        expense_for = request.form.get("expense_for", "").strip()
        description = request.form.get("description", "").strip()
        date = request.form.get("expense_date", "").strip() or datetime.now().strftime("%Y-%m-%d")
        try:
            amount = float(request.form.get("amount", "0") or 0)
        except ValueError:
            flash("Enter a valid expense amount.", "error")
            return redirect(url_for("expenses"))
        if not expense_for or not description or amount <= 0:
            flash("Expense category, description and an amount greater than zero are required.", "error")
            return redirect(url_for("expenses"))
        cursor = db.execute(
            "INSERT INTO expenses (expense_for, description, amount, expense_date, created_at) VALUES (?, ?, ?, ?, ?)",
            (expense_for, description, amount, date, datetime.now().isoformat(timespec="seconds")),
        )
        saved_expense = db.execute("SELECT * FROM expenses WHERE id = ?", (cursor.lastrowid,)).fetchone()
        record_expense_history(db, saved_expense, "created")
        db.commit()
        flash("Expense recorded successfully.", "success")
        return redirect(url_for("expenses", compose="1", added=cursor.lastrowid))
    rows = db.execute("SELECT * FROM expenses ORDER BY expense_date DESC, id DESC").fetchall()
    total = db.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM expenses").fetchone()["total"]
    all_people = db.execute("SELECT * FROM persons ORDER BY name COLLATE NOCASE").fetchall()
    return render_template("expenses.html", active="expenses", expenses=rows, total=total, all_persons=all_people, now_date=datetime.now().strftime("%Y-%m-%d"))


@app.post("/expenses/<int:expense_id>/delete")
@login_required
def delete_expense(expense_id: int):
    db = get_db()
    expense = db.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    if expense:
        record_expense_history(db, expense, "deleted")
        db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        db.commit()
    flash("Expense record deleted; its history snapshot was retained.", "success")
    return redirect(url_for("expenses"))


@app.get("/reports")
@login_required
def reports():
    db = get_db()
    people = db.execute("SELECT * FROM persons ORDER BY name COLLATE NOCASE").fetchall()
    expenses_rows = db.execute("SELECT * FROM expenses ORDER BY expense_date DESC, id DESC").fetchall()
    summary = db.execute(
        """SELECT COUNT(*) AS people,
                  COALESCE(SUM(CASE WHEN payment_status='paid' THEN amount_received ELSE 0 END),0) AS chanda,
                  COALESCE(SUM(CASE WHEN payment_status='pending' THEN amount_received ELSE 0 END),0) AS pending
           FROM persons"""
    ).fetchone()
    exp_total = db.execute("SELECT COALESCE(SUM(amount),0) AS total FROM expenses").fetchone()["total"]
    return render_template("reports.html", active="reports", people=people, expenses=expenses_rows,
                           summary=summary, expense_total=exp_total, balance=summary["chanda"] - exp_total)


@app.get("/members-overview")
@login_required
def members_overview():
    db = get_db()
    stats = db.execute(
        """SELECT COUNT(DISTINCT phone) AS total_members,
                  COUNT(*) AS contribution_entries,
                  COALESCE(SUM(CASE WHEN payment_status='paid' THEN amount_received ELSE 0 END),0) AS paid_total,
                  COALESCE(SUM(CASE WHEN payment_status='pending' THEN amount_received ELSE 0 END),0) AS pending_total
           FROM persons"""
    ).fetchone()
    recent = db.execute("SELECT * FROM persons ORDER BY id DESC LIMIT 12").fetchall()
    expense_total = db.execute("SELECT COALESCE(SUM(amount),0) AS total FROM expenses").fetchone()["total"]
    return render_template("members_overview.html", active="members_overview", stats=stats,
                           recent=recent, expense_total=expense_total,
                           balance=float(stats["paid_total"]) - float(expense_total))


@app.get("/members")
@login_required
def members():
    db = get_db()
    query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all")
    raw_people = db.execute("SELECT * FROM persons ORDER BY created_at ASC, id ASC").fetchall()
    grouped = {}
    for person in raw_people:
        phone = person["phone"]
        member = grouped.setdefault(phone, {
            "name": person["name"], "phone": phone, "paid": 0.0, "pending": 0.0,
            "entries": 0, "latest": person["created_at"],
        })
        member["name"] = person["name"]
        member["entries"] += 1
        member["latest"] = max(member["latest"], person["created_at"])
        if person["payment_status"] == "paid":
            member["paid"] += float(person["amount_received"] or 0)
        else:
            member["pending"] += float(person["amount_received"] or 0)
    all_members = sorted(grouped.values(), key=lambda item: item["name"].casefold())
    filtered = [m for m in all_members if not query or query.casefold() in m["name"].casefold() or query in m["phone"]]
    if status_filter == "paid":
        filtered = [m for m in filtered if m["paid"] > 0 and m["pending"] == 0]
    elif status_filter == "pending":
        filtered = [m for m in filtered if m["pending"] > 0]
    paid_total = sum(m["paid"] for m in all_members)
    pending_total = sum(m["pending"] for m in all_members)
    return render_template("members.html", active="members", persons=filtered,
                           total_members=len(all_members), paid_total=paid_total,
                           pending_total=pending_total, query=query, status_filter=status_filter)


@app.get("/exports/full-history.xlsx")
@login_required
def export_full_history_excel():
    dataset = build_export_dataset(get_db())
    output = create_excel_export(dataset)
    filename = f"ganesh_festival_complete_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/exports/full-history.pdf")
@login_required
def export_full_history_pdf():
    dataset = build_export_dataset(get_db())
    output = create_pdf_export(dataset)
    filename = f"ganesh_festival_complete_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(output, as_attachment=True, download_name=filename, mimetype="application/pdf")


@app.get("/send-messages")
@login_required
def send_messages():
    people = get_db().execute("SELECT * FROM persons ORDER BY name COLLATE NOCASE").fetchall()
    return render_template("messages.html", active="messages", persons=people)


@app.post("/api/message-batch")
@login_required
def message_batch():
    """Prepare WhatsApp click-to-chat links; the sender must press Send in WhatsApp."""
    data = request.get_json(silent=True) or {}
    ids = data.get("person_ids", [])
    template = str(data.get("template", ""))[:4000]
    if not isinstance(ids, list) or not ids:
        return jsonify(error="Select at least one person."), 400
    safe_ids = []
    for value in ids:
        try:
            safe_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    if not safe_ids:
        return jsonify(error="No valid recipients were selected."), 400
    placeholders = ",".join("?" for _ in safe_ids)
    rows = get_db().execute(f"SELECT * FROM persons WHERE id IN ({placeholders}) ORDER BY name COLLATE NOCASE", safe_ids).fetchall()
    queue = []
    for person in rows:
        phone = "".join(ch for ch in person["phone"] if ch.isdigit())
        if len(phone) == 10:
            phone = "91" + phone
        message = (template
                   .replace("{{name}}", person["name"])
                   .replace("{{amount_received}}", money(person["amount_received"]))
                   .replace("{{payment_status}}", "Paid" if person["payment_status"] == "paid" else "Pending")
                   .replace("{{location}}", APP_LOCATION))
        queue.append({"id": person["id"], "name": person["name"], "phone": phone,
                      "message": message, "url": f"https://wa.me/{phone}?text={quote(message)}"})
    if not queue:
        return jsonify(error="No matching recipients were found."), 404
    return jsonify(items=queue, note="WhatsApp opens with a prepared message. Review it and press Send in WhatsApp.")


@app.post("/api/expense-message")
@login_required
def expense_message():
    """Build the editable festival financial summary for selected contributors."""
    data = request.get_json(silent=True) or {}
    ids = data.get("person_ids", [])
    if not isinstance(ids, list) or not ids:
        return jsonify(error="Select at least one contributor to receive the summary."), 400
    safe_ids = []
    for value in ids:
        try:
            safe_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    if not safe_ids:
        return jsonify(error="No valid recipients were selected."), 400

    db = get_db()
    placeholders = ",".join("?" for _ in safe_ids)
    recipients = db.execute(
        f"SELECT * FROM persons WHERE id IN ({placeholders}) ORDER BY name COLLATE NOCASE", safe_ids
    ).fetchall()
    rows = db.execute("SELECT * FROM expenses ORDER BY expense_date ASC, id ASC").fetchall()
    total_expenses = sum(float(row["amount"]) for row in rows)
    total_chanda = db.execute(
        "SELECT COALESCE(SUM(amount_received), 0) AS total FROM persons WHERE payment_status='paid'"
    ).fetchone()["total"]
    total_pending = db.execute(
        "SELECT COALESCE(SUM(amount_received), 0) AS total FROM persons WHERE payment_status='pending'"
    ).fetchone()["total"]
    remaining = float(total_chanda) - float(total_expenses)

    table_lines = ["S.No. | Particulars | Amount", "--------------------------------"]
    for index, row in enumerate(rows, start=1):
        table_lines.append(f"{index}. {row['expense_for']} - {row['description']} | {money(row['amount'])}")
    table_lines.append(f"TOTAL EXPENSES | {money(total_expenses)}")
    table_text = "\n".join(table_lines)
    summary_lines = [
        f"Total Chanda Received (Paid): {money(total_chanda)}",
        f"Total Pending Chanda: {money(total_pending)}",
        f"Total Expenses: {money(total_expenses)}",
        f"Remaining Chanda Balance: {money(remaining)}",
    ]
    financial_summary = "\n".join(summary_lines)
    template = str(data.get("template", ""))[:5000]
    message = (template.replace("{{expense_table}}", table_text)
               .replace("{{total_chanda}}", money(total_chanda))
               .replace("{{total_pending}}", money(total_pending))
               .replace("{{total_expenses}}", money(total_expenses))
               .replace("{{remaining_balance}}", money(remaining))
               .replace("{{financial_summary}}", financial_summary)
               .replace("{{location}}", APP_LOCATION))

    items = []
    for person in recipients:
        phone = "".join(ch for ch in person["phone"] if ch.isdigit())
        if len(phone) == 10:
            phone = "91" + phone
        personalized = message.replace("{{name}}", person["name"])
        items.append({"id": person["id"], "name": person["name"], "phone": phone,
                      "message": personalized, "url": f"https://wa.me/{phone}?text={quote(personalized)}"})
    return jsonify(
        message=message, items=items, total=total_expenses, total_chanda=float(total_chanda),
        total_pending=float(total_pending), remaining_balance=remaining, count=len(rows),
        rows=[{"category": r["expense_for"], "description": r["description"], "amount": money(r["amount"]), "date": r["expense_date"]} for r in rows],
    )


@app.get("/health")
def health():
    return {"status": "ok", "application": "ganesh-festival-management"}


with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG") == "1")
