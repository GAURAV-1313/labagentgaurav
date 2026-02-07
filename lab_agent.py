import argparse
import base64
import io
import json
import os
import re
import tempfile
from datetime import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import nbformat
from nbconvert import HTMLExporter
from playwright.sync_api import sync_playwright


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/classroom.coursework.me",
]


QUESTION_PATTERNS = [
    re.compile(r"\bQ(?:uestion)?\s*([0-9]+)\b", re.IGNORECASE),
]


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_credentials() -> Credentials:
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("token.json", "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


def get_services(creds: Credentials):
    drive_service = build("drive", "v3", credentials=creds)
    docs_service = build("docs", "v1", credentials=creds)
    classroom_service = build("classroom", "v1", credentials=creds)
    return drive_service, docs_service, classroom_service


def download_notebook(drive_service, file_id: str) -> dict:
    request = drive_service.files().get_media(
        fileId=file_id, supportsAllDrives=True
    )
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return json.loads(fh.read().decode("utf-8"))


def find_question_number(text: str):
    for pattern in QUESTION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def parse_notebook(nb: dict, auto_number: bool):
    questions = {}
    current_q = None
    screenshot_map = []
    auto_index = 1
    pending_reasoning = None

    for cell in nb.get("cells", []):
        cell_type = cell.get("cell_type")
        source = "".join(cell.get("source", []))

        if cell_type == "markdown":
            qn = find_question_number(source)
            if qn:
                current_q = qn
                questions.setdefault(current_q, {"items": []})
                pending_reasoning = None
                continue
            if current_q:
                text = source.strip()
                if text:
                    if pending_reasoning:
                        pending_reasoning = (pending_reasoning + "\n" + text).strip()
                    else:
                        pending_reasoning = text
            continue

        if cell_type == "code":
            if current_q is None:
                qn = find_question_number(source)
                if qn:
                    current_q = qn
            if current_q is None:
                # Try to detect question number from outputs
                for out in cell.get("outputs", []):
                    out_type = out.get("output_type")
                    if out_type == "stream":
                        text = "".join(out.get("text", []))
                        qn = find_question_number(text)
                        if qn:
                            current_q = qn
                            break
                    elif out_type in ("execute_result", "display_data"):
                        data = out.get("data", {})
                        if "text/plain" in data:
                            text = "".join(data["text/plain"])
                            qn = find_question_number(text)
                            if qn:
                                current_q = qn
                                break
                if current_q is None and auto_number:
                    current_q = str(auto_index)
                    auto_index += 1
                if current_q is None:
                    continue
            questions.setdefault(current_q, {"items": []})
            if source.strip():
                item = {"code": source, "outputs": ""}
                if pending_reasoning:
                    item["reasoning"] = pending_reasoning
                    pending_reasoning = None
                questions[current_q]["items"].append(item)

            outputs = cell.get("outputs", [])
            if outputs:
                if not questions[current_q]["items"]:
                    item = {"code": "", "outputs": ""}
                    if pending_reasoning:
                        item["reasoning"] = pending_reasoning
                        pending_reasoning = None
                    questions[current_q]["items"].append(item)
                item_index = len(questions[current_q]["items"]) - 1
                screenshot_map.append((current_q, item_index))

            for out in outputs:
                out_type = out.get("output_type")
                if out_type == "stream":
                    text = "".join(out.get("text", []))
                    if text.strip():
                        if questions[current_q]["items"]:
                            questions[current_q]["items"][-1]["outputs"] += text
                elif out_type in ("execute_result", "display_data"):
                    data = out.get("data", {})
                    if "text/plain" in data:
                        text = "".join(data["text/plain"])
                        if text.strip():
                            if questions[current_q]["items"]:
                                questions[current_q]["items"][-1]["outputs"] += text
                    if "image/png" in data:
                        if questions[current_q]["items"]:
                            questions[current_q]["items"][-1]["image_b64"] = data["image/png"]

    return questions, screenshot_map


def export_notebook_html(nb: dict) -> str:
    # Normalize cell sources to strings for nbconvert
    for cell in nb.get("cells", []):
        src = cell.get("source", "")
        if isinstance(src, list):
            cell["source"] = "".join(src)
        elif src is None:
            cell["source"] = ""
    nb_node = nbformat.from_dict(nb)
    exporter = HTMLExporter()
    body, _ = exporter.from_notebook_node(nb_node)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
    tmp.write(body.encode("utf-8"))
    tmp.close()
    return tmp.name


def capture_output_screenshots(html_path: str) -> list:
    screenshots = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file://{html_path}", wait_until="networkidle")

        elements = page.query_selector_all(".output_area")
        if not elements:
            elements = page.query_selector_all(".output")
        if not elements:
            elements = page.query_selector_all(".jp-OutputArea")

        for i, el in enumerate(elements):
            try:
                path = tempfile.mkstemp(prefix=f"output-{i}-", suffix=".png")[1]
                el.screenshot(path=path)
                screenshots.append(path)
            except Exception:
                continue

        browser.close()

    return screenshots


def create_doc(docs_service, title: str) -> str:
    doc = docs_service.documents().create(body={"title": title}).execute()
    return doc["documentId"]


def upload_image(drive_service, image_b64: str) -> str:
    raw = base64.b64decode(image_b64)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp.write(raw)
        tmp_path = tmp.name

    media = MediaFileUpload(tmp_path, mimetype="image/png")
    file_metadata = {"name": f"lab-evidence-{datetime.utcnow().isoformat()}.png"}
    created = drive_service.files().create(
        body=file_metadata, media_body=media, fields="id", supportsAllDrives=True
    ).execute()
    os.unlink(tmp_path)
    return created["id"]


def upload_image_file(drive_service, path: str) -> str:
    media = MediaFileUpload(path, mimetype="image/png")
    file_metadata = {"name": f"lab-evidence-shot-{datetime.utcnow().isoformat()}.png"}
    created = drive_service.files().create(
        body=file_metadata, media_body=media, fields="id", supportsAllDrives=True
    ).execute()
    return created["id"]


def maybe_share_file(drive_service, file_id: str):
    drive_service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
        supportsAllDrives=True,
    ).execute()


def build_doc_requests(questions: dict, drive_service, share_images: bool):
    requests = []
    index = 1

    def add_text(txt: str):
        nonlocal index
        requests.append({"insertText": {"location": {"index": index}, "text": txt}})
        index += len(txt)

    add_text("Lab Evidence\n\n")

    for qn in sorted(questions.keys(), key=lambda x: int(x)):
        q = questions[qn]
        add_text(f"Question {qn}\n")
        add_text("=" * 40 + "\n")

        items = q.get("items", [])
        for i, item in enumerate(items, start=1):
            add_text(f"Code {i}:\n")
            for line in item["code"].strip().splitlines():
                add_text(f"    {line}\n")
            add_text("\n")

            if item.get("image_b64"):
                add_text(f"Image {i}:\n")
                try:
                    file_id = upload_image(drive_service, item["image_b64"])
                    if share_images:
                        maybe_share_file(drive_service, file_id)
                    image_url = f"https://drive.google.com/uc?id={file_id}"
                    requests.append(
                        {
                            "insertInlineImage": {
                                "location": {"index": index},
                                "uri": image_url,
                                "objectSize": {
                                    "height": {"magnitude": 300, "unit": "PT"},
                                    "width": {"magnitude": 450, "unit": "PT"},
                                },
                            }
                        }
                    )
                    index += 1
                    add_text("\n")
                except Exception:
                    add_text("(Image attached in Drive; embed failed)\n")
                add_text("\n")

            if item.get("screenshot_file"):
                add_text(f"Output {i}:\n")
                try:
                    file_id = upload_image_file(drive_service, item["screenshot_file"])
                    if share_images:
                        maybe_share_file(drive_service, file_id)
                    image_url = f"https://drive.google.com/uc?id={file_id}"
                    requests.append(
                        {
                            "insertInlineImage": {
                                "location": {"index": index},
                                "uri": image_url,
                                "objectSize": {
                                    "height": {"magnitude": 300, "unit": "PT"},
                                    "width": {"magnitude": 450, "unit": "PT"},
                                },
                            }
                        }
                    )
                    index += 1
                    add_text("\n")
                except Exception:
                    add_text("(Screenshot attached in Drive; embed failed)\n")
                add_text("\n")

            if item.get("reasoning"):
                add_text(f"Reasoning {i}:\n")
                for line in item["reasoning"].strip().splitlines():
                    add_text(f"    {line}\n")
                add_text("\n")

        add_text("\n")

    return requests


def attach_and_turn_in(classroom_service, class_id: str, assignment_id: str, doc_id: str):
    submissions = classroom_service.courses().courseWork().studentSubmissions().list(
        courseId=class_id, courseWorkId=assignment_id, userId="me"
    ).execute()
    items = submissions.get("studentSubmissions", [])
    if not items:
        raise RuntimeError("No student submission found for this assignment.")
    submission_id = items[0]["id"]

    classroom_service.courses().courseWork().studentSubmissions().modifyAttachments(
        courseId=class_id,
        courseWorkId=assignment_id,
        id=submission_id,
        body={
            "addAttachments": [
                {
                    "driveFile": {
                        "id": doc_id,
                    }
                }
            ]
        },
    ).execute()

    classroom_service.courses().courseWork().studentSubmissions().turnIn(
        courseId=class_id, courseWorkId=assignment_id, id=submission_id
    ).execute()


def list_pending_assignments(classroom_service, class_id: str):
    coursework = classroom_service.courses().courseWork().list(
        courseId=class_id
    ).execute()
    items = coursework.get("courseWork", [])

    pending = []
    for cw in items:
        work_id = cw.get("id")
        title = cw.get("title", "Untitled")
        due = cw.get("dueDate")
        due_str = ""
        if due:
            due_str = f"{due.get('year')}-{due.get('month'):02d}-{due.get('day'):02d}"

        submissions = classroom_service.courses().courseWork().studentSubmissions().list(
            courseId=class_id, courseWorkId=work_id, userId="me"
        ).execute()
        subs = submissions.get("studentSubmissions", [])
        if not subs:
            continue
        state = subs[0].get("state")
        if state in ("NEW", "CREATED", "RECLAIMED_BY_STUDENT"):
            pending.append((work_id, title, due_str, state))

    return pending


def list_drive_folder_files(drive_service, folder_id: str):
    results = drive_service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, mimeType)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    return results.get("files", [])


def run_pipeline(
    config: dict,
    *,
    auto_number: bool,
    turn_in: bool,
):
    creds = get_credentials()
    drive_service, docs_service, classroom_service = get_services(creds)

    nb = download_notebook(drive_service, config["notebook_file_id"])
    questions, screenshot_map = parse_notebook(nb, auto_number)
    if not questions:
        raise RuntimeError(
            "No questions found. Add markdown cells with Q1 / Question 1, etc."
        )

    shots = []
    if config.get("screenshot_outputs", False):
        html_path = export_notebook_html(nb)
        shots = capture_output_screenshots(html_path)
        os.unlink(html_path)
        print(f"Screenshot capture: found {len(shots)} output images")
        for i, (qn, item_index) in enumerate(screenshot_map):
            if i < len(shots):
                items = questions[qn].setdefault("items", [])
                while len(items) <= item_index:
                    items.append({"code": "", "outputs": ""})
                items[item_index]["screenshot_file"] = shots[i]

    title = config.get("doc_title", "Lab Evidence")
    doc_id = create_doc(docs_service, title)
    requests = build_doc_requests(
        questions, drive_service, config.get("share_images", False)
    )
    docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()

    for path in shots:
        try:
            os.unlink(path)
        except OSError:
            pass

    if turn_in:
        attach_and_turn_in(
            classroom_service, config["class_id"], config["assignment_id"], doc_id
        )

    return doc_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--list-assignments", action="store_true")
    parser.add_argument("--list-drive-folder", default=None)
    parser.add_argument("--auto-number", action="store_true")
    parser.add_argument("--no-turn-in", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    creds = get_credentials()
    drive_service, docs_service, classroom_service = get_services(creds)

    if args.list_assignments:
        pending = list_pending_assignments(classroom_service, config["class_id"])
        if not pending:
            print("No pending assignments found.")
            return
        print("Pending assignments:")
        for work_id, title, due_str, state in pending:
            due_part = f" (due {due_str})" if due_str else ""
            print(f"- {title}{due_part} | id={work_id} | state={state}")
        return

    if args.list_drive_folder:
        files = list_drive_folder_files(drive_service, args.list_drive_folder)
        if not files:
            print("No files found in folder.")
            return
        print("Files in folder:")
        for f in files:
            print(f"- {f['name']} | id={f['id']} | {f['mimeType']}")
        return

    auto_number = args.auto_number or config.get("auto_number", False)
    doc_id = run_pipeline(
        config,
        auto_number=auto_number,
        turn_in=not args.no_turn_in,
    )
    if args.no_turn_in:
        print("Doc created. Skipping Classroom turn-in.")
    print(f"Submitted. Doc ID: {doc_id}")


if __name__ == "__main__":
    main()
