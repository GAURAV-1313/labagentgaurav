# AI Lab Agent (Colab → Google Doc → Classroom)

This project creates a Google Doc from a Colab notebook by pairing each question number with evidence (code + output), then submits it to a Google Classroom assignment.

## What It Does
- Reads a Colab `.ipynb` from Google Drive
- Parses question numbers from markdown cells (ex: `Q1`, `Question 2`)
- Collects evidence from code cells and their outputs
- Creates a Google Doc with `Question → Evidence`
- Attaches the Doc to a Classroom assignment and turns it in

## Setup (One Time)
1. Enable APIs in your Google Cloud project:
   - Google Classroom API
   - Google Docs API
   - Google Drive API
2. Configure OAuth consent screen for your school account.
3. Create OAuth Client ID (Desktop App) and download `credentials.json`.

Place `credentials.json` in this project folder.

## Config
Copy `config.example.json` to `config.json` and fill in:
- `class_id`
- `assignment_id`
- `notebook_file_id`

### Get Assignment ID (API)
If the assignment ID isn’t visible in the URL, use the built-in API helper:
```
python lab_agent.py --list-assignments --config config.json
```
It will show pending assignments with IDs so you can copy the one you want.

## Install
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install
```

## Run
```
python lab_agent.py --config config.json
```

## UI (Single Page)
Start the local web app:
```
python app.py
```
Open `http://localhost:5055` in your browser.

## Notes
- Question numbers can be detected in markdown, code comments, or output text (ex: `Q3`, `Question 4`).
- For full output screenshots, set `"screenshot_outputs": true` in your config.
- Drive access uses read-only scope, so you may need to re-auth the first time after changes.
