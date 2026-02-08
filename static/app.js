const statusEl = document.getElementById("status");
const previewEl = document.getElementById("preview");
const assignmentsEl = document.getElementById("assignments");
const notebooksEl = document.getElementById("notebooks");

const classIdInput = document.getElementById("classId");
const assignmentIdInput = document.getElementById("assignmentId");
const notebookIdInput = document.getElementById("notebookId");
const docTitleInput = document.getElementById("docTitle");
const folderIdInput = document.getElementById("folderId");

const autoNumberInput = document.getElementById("autoNumber");
const screenshotsInput = document.getElementById("screenshots");
const shareImagesInput = document.getElementById("shareImages");
const turnInInput = document.getElementById("turnIn");

const listAssignmentsBtn = document.getElementById("listAssignments");
const listNotebooksBtn = document.getElementById("listNotebooks");
const runBtn = document.getElementById("run");
const loginBtn = document.getElementById("loginBtn");
const authStatus = document.getElementById("authStatus");
const logoutBtn = document.getElementById("logoutBtn");

const setStatus = (text) => {
  statusEl.textContent = text;
};
const setPreview = (docId) => {
  if (!docId) {
    previewEl.innerHTML = "No preview yet.";
    return;
  }
  const url = `https://docs.google.com/document/d/${docId}/edit`;
  previewEl.innerHTML = `Preview Doc: <a href="${url}" target="_blank" rel="noreferrer">${url}</a>`;
};

const renderList = (el, items, onPick) => {
  el.innerHTML = "";
  if (!items.length) {
    el.textContent = "No items.";
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "list-item";
    row.textContent = item;
    row.addEventListener("click", () => onPick?.(row));
    el.appendChild(row);
  });
};

const loadConfig = async () => {
  const res = await fetch("/api/config");
  if (!res.ok) return;
  const cfg = await res.json();
  classIdInput.value = cfg.class_id || "";
  assignmentIdInput.value = cfg.assignment_id || "";
  notebookIdInput.value = cfg.notebook_file_id || "";
  docTitleInput.value = cfg.doc_title || "";
  autoNumberInput.checked = cfg.auto_number ?? true;
  screenshotsInput.checked = cfg.screenshot_outputs ?? true;
  shareImagesInput.checked = cfg.share_images ?? true;
  const authRes = await fetch("/api/auth-status");
  if (authRes.ok) {
    const auth = await authRes.json();
    authStatus.textContent = auth.logged_in ? "Logged in" : "Not logged in";
    if (!auth.logged_in) {
      setStatus("Please login to continue.");
    }
  }
};

listAssignmentsBtn.addEventListener("click", async () => {
  if (!classIdInput.value) {
    setStatus("Class ID/URL is required.");
    return;
  }
  setStatus("Fetching assignments...");
  const res = await fetch(`/api/list-assignments?class_id=${classIdInput.value}`);
  if (!res.ok) {
    const err = await res.json();
    setStatus(err.error || "Failed to fetch assignments.");
    return;
  }
  const items = await res.json();
  renderList(
    assignmentsEl,
    items.map((a) => `${a.title} | id=${a.id} | ${a.state}`),
    null
  );
  assignmentsEl.querySelectorAll(".list-item").forEach((itemEl, idx) => {
    itemEl.addEventListener("click", () => {
      assignmentsEl.querySelectorAll(".list-item").forEach((el) =>
        el.classList.remove("selected")
      );
      itemEl.classList.add("selected");
      assignmentIdInput.value = items[idx].id;
      setStatus(`Selected assignment ${items[idx].id}`);
    });
  });
  setStatus("Assignments loaded. Click one to select.");
});

listNotebooksBtn.addEventListener("click", async () => {
  if (!folderIdInput.value) {
    setStatus("Folder ID/URL is required.");
    return;
  }
  setStatus("Fetching notebooks...");
  const res = await fetch(`/api/list-drive-folder?folder_id=${folderIdInput.value}`);
  if (!res.ok) {
    const err = await res.json();
    setStatus(err.error || "Failed to fetch folder.");
    return;
  }
  const items = await res.json();
  renderList(
    notebooksEl,
    items.map((f) => `${f.name} | id=${f.id}`),
    null
  );
  notebooksEl.querySelectorAll(".list-item").forEach((itemEl, idx) => {
    itemEl.addEventListener("click", () => {
      notebooksEl.querySelectorAll(".list-item").forEach((el) =>
        el.classList.remove("selected")
      );
      itemEl.classList.add("selected");
      notebookIdInput.value = items[idx].id;
      setStatus(`Selected notebook ${items[idx].name}`);
    });
  });
  setStatus("Notebooks loaded. Click one to select.");
});

runBtn.addEventListener("click", async () => {
  const payload = {
    class_id: classIdInput.value.trim(),
    assignment_id: assignmentIdInput.value.trim(),
    notebook_file_id: notebookIdInput.value.trim(),
    doc_title: docTitleInput.value.trim() || "Lab Evidence",
    auto_number: autoNumberInput.checked,
    screenshot_outputs: screenshotsInput.checked,
    share_images: shareImagesInput.checked,
    turn_in: turnInInput.checked,
  };
  if (!payload.class_id || !payload.assignment_id || !payload.notebook_file_id) {
    setStatus("Class ID/URL, Assignment ID/URL, and Notebook ID/URL are required.");
    return;
  }
  setStatus("Running pipeline. This can take a minute...");
  const res = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json();
    setStatus(err.error || "Run failed.");
    return;
  }
  const data = await res.json();
  setStatus(`Done. Doc ID: ${data.doc_id}`);
  setPreview(data.doc_id);
});

loginBtn.addEventListener("click", async () => {
  setStatus("Opening login...");
  window.location.href = "/login";
});

logoutBtn.addEventListener("click", async () => {
  setStatus("Switching account...");
  const res = await fetch("/api/logout", { method: "POST" });
  if (!res.ok) {
    const err = await res.json();
    setStatus(err.error || "Logout failed.");
    return;
  }
  authStatus.textContent = "Not logged in";
  setStatus("Logged out. Click Login to sign in again.");
});

loadConfig();
