import json
import os
import traceback
from pathlib import Path

from flask import Flask, jsonify, render_template, request, redirect, session
from google_auth_oauthlib.flow import Flow

from lab_agent import (
    SCOPES,
    get_credentials,
    get_services,
    list_pending_assignments,
    list_drive_folder_files,
    run_pipeline,
)


APP_ROOT = Path(__file__).parent
CONFIG_PATH = APP_ROOT / "config.json"
TOKEN_PATH = APP_ROOT / "token.json"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")


def load_config():
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(data: dict):
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def auth_status():
    try:
        if os.getenv("WEB_OAUTH") == "1" and not TOKEN_PATH.exists():
            return False
        creds = get_credentials()
        return bool(creds and creds.valid)
    except Exception:
        return False


def load_oauth_client():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if client_id and client_secret and redirect_uri:
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }

    cred_path = APP_ROOT / "credentials.json"
    if cred_path.exists():
        with cred_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError("credentials.json or GOOGLE_CLIENT_ID/SECRET not found.")


def build_flow():
    client = load_oauth_client()
    flow = Flow.from_client_config(client, scopes=SCOPES)
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if redirect_uri:
        flow.redirect_uri = redirect_uri
    return flow


def normalize_class_id(value: str) -> str:
    if not value:
        return value
    text = value.strip()
    if "classroom.google.com" in text:
        if "/c/" in text:
            parts = text.split("/c/")
            if len(parts) > 1:
                text = parts[1].split("/")[0].split("?")[0]
        elif "/w/" in text:
            parts = text.split("/w/")
            if len(parts) > 1:
                text = parts[1].split("/")[0].split("?")[0]
    # If looks like base64 url-safe, try to decode to numeric id
    if not text.isdigit():
        try:
            import base64

            padded = text + "=" * ((4 - len(text) % 4) % 4)
            decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
            if decoded.isdigit():
                return decoded
        except Exception:
            pass
    return text


def normalize_assignment_id(value: str) -> str:
    if not value:
        return value
    text = value.strip()
    if "classroom.google.com" in text and "/a/" in text:
        parts = text.split("/a/")
        if len(parts) > 1:
            text = parts[1].split("/")[0].split("?")[0]
    return text


def normalize_notebook_id(value: str) -> str:
    if not value:
        return value
    text = value.strip()
    if "colab.research.google.com/drive/" in text:
        return text.split("colab.research.google.com/drive/")[1].split("?")[0]
    if "drive.google.com/file/d/" in text:
        return text.split("drive.google.com/file/d/")[1].split("/")[0].split("?")[0]
    if "drive.google.com/open" in text and "id=" in text:
        return text.split("id=")[1].split("&")[0]
    return text


def normalize_folder_id(value: str) -> str:
    if not value:
        return value
    text = value.strip()
    if text.endswith("/home"):
        return ""
    if "drive.google.com/drive/folders/" in text:
        return text.split("drive.google.com/drive/folders/")[1].split("?")[0]
    if "drive.google.com/drive/u/" in text and "/folders/" in text:
        return text.split("/folders/")[1].split("?")[0]
    return text


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return "ok", 200

@app.get("/api/config")
def api_config():
    return jsonify(load_config())


@app.get("/api/auth-status")
def api_auth_status():
    return jsonify({"logged_in": auth_status()})


@app.get("/login")
def login():
    try:
        flow = build_flow()
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        session["state"] = state
        return redirect(auth_url)
    except Exception as exc:
        traceback.print_exc()
        return f"Login error: {exc}", 500


@app.get("/oauth2callback")
def oauth2callback():
    try:
        flow = build_flow()
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials
        with TOKEN_PATH.open("w", encoding="utf-8") as f:
            f.write(creds.to_json())
        return redirect("/")
    except Exception as exc:
        traceback.print_exc()
        return f"OAuth callback error: {exc}", 500


@app.post("/api/logout")
def api_logout():
    try:
        if TOKEN_PATH.exists():
            TOKEN_PATH.unlink()
        return jsonify({"logged_in": False})
    except Exception as exc:
        return jsonify({"logged_in": False, "error": str(exc)}), 500


@app.get("/api/list-assignments")
def api_list_assignments():
    class_id = request.args.get("class_id")
    if not class_id:
        return jsonify({"error": "class_id is required"}), 400
    class_id = normalize_class_id(class_id)
    try:
        creds = get_credentials()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 401
    _, _, classroom_service = get_services(creds)
    pending = list_pending_assignments(classroom_service, class_id)
    return jsonify(
        [
            {"id": work_id, "title": title, "due": due, "state": state}
            for work_id, title, due, state in pending
        ]
    )


@app.get("/api/list-drive-folder")
def api_list_drive_folder():
    folder_id = request.args.get("folder_id")
    if not folder_id:
        return jsonify({"error": "folder_id is required"}), 400
    folder_id = normalize_folder_id(folder_id)
    if not folder_id:
        return jsonify(
            {
                "error": "Please paste a folder URL like https://drive.google.com/drive/folders/FOLDER_ID"
            }
        ), 400
    try:
        creds = get_credentials()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 401
    drive_service, _, _ = get_services(creds)
    files = list_drive_folder_files(drive_service, folder_id)
    return jsonify(files)


@app.post("/api/run")
def api_run():
    payload = request.get_json(force=True)
    required = ["class_id", "assignment_id", "notebook_file_id"]
    for key in required:
        if not payload.get(key):
            return jsonify({"error": f"{key} is required"}), 400

    class_id = normalize_class_id(payload["class_id"])
    assignment_id = normalize_assignment_id(payload["assignment_id"])
    notebook_id = normalize_notebook_id(payload["notebook_file_id"])
    config = {
        "class_id": class_id,
        "assignment_id": assignment_id,
        "notebook_file_id": notebook_id,
        "doc_title": payload.get("doc_title", "Lab Evidence"),
        "share_images": bool(payload.get("share_images", True)),
        "screenshot_outputs": bool(payload.get("screenshot_outputs", True)),
        "auto_number": bool(payload.get("auto_number", True)),
    }
    save_config(config)

    try:
        doc_id = run_pipeline(
            config,
            auto_number=config["auto_number"],
            turn_in=bool(payload.get("turn_in", False)),
        )
        return jsonify({"doc_id": doc_id})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5055"))
    app.run(host="0.0.0.0", port=port, debug=False)
