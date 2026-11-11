# Sri Rama Ganesh Utsav Association – Complete Festival Management App (V5)

A consolidated Flask + SQLite web application for Nagiligond (Vill), Khammam. This release brings the full reference design and requested modules into one project.

## Included modules

- Login and purple/gold Ganesh-themed interface.
- Dashboard with total members, paid chanda, expenses and remaining balance.
- Person Details: Pay, Pay Later, Send WhatsApp Message; Paid/Pending status; edit and delete.
- Expenses: category, description, amount, date, itemized records and totals.
- WhatsApp Communication: Chanda Thank You and Festival Expenses Summary tabs; Select All, Paid, Pending and manual recipient selection; editable templates and previews; personalized WhatsApp queue.
- Members overview and Members Directory with search, paid/pending totals, status and latest record.
- Records & Reports.
- Complete Excel and PDF exports: financial summary, grouped member directory, member-wise contribution detail, all chanda records, chanda activity history, all expenses and expense activity history.
- Audit snapshots for new and deleted chanda and expense entries. Existing records are backfilled as baseline snapshots on first launch of this version.
- Railway deployment files.

## Run on Windows

1. Extract the ZIP.
2. Open PowerShell in the extracted project folder (the folder containing `app.py` and `requirements.txt`).
3. Create environment: `python -m venv .venv`
4. Install packages: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
5. Start: `.\.venv\Scripts\python.exe app.py`
6. Open `http://127.0.0.1:5000`.

Or double-click `start_windows.bat`.

First-run login: `admin` / `Ganesh@2026`. Change the password and `SECRET_KEY` before public hosting.

## Preserve your existing data when upgrading

1. Stop the old app with `Ctrl+C`.
2. Make a backup copy of `instance/ganesh.db`.
3. Copy the old `instance/ganesh.db` into the V5 project's `instance` folder. Create the `instance` folder if it does not exist.
4. Start V5. It adds the expense-history table and keeps the existing persons and expenses. Existing chanda and expense rows are imported into history as baseline records.

Never replace an existing database with an empty database if you need to keep old records.

## WhatsApp sending limitation

The app prepares a queue of personalized WhatsApp Click-to-Chat links. The browser opens one selected member chat at a time; the operator must press **Send** in WhatsApp and then return to continue the queue. A normal website cannot silently send WhatsApp messages or send to every chat simultaneously. True automated bulk delivery requires the official WhatsApp Business Platform API, approved templates and recipient opt-in.

## Exports

Excel contains separate sheets for Financial Summary, Member Directory, Member Contributions, Chanda Records, Chanda History, Expense Records and Expense History. PDF includes the corresponding report sections and financial totals. Filtered directory views do not limit the export: all stored records are included.

## Deployment

Use persistent storage for SQLite on Railway (or configure `DATABASE_PATH` to a persistent volume). Set strong `SECRET_KEY`, `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables before public deployment. Do not expose the default credentials.
