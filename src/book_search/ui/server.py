from __future__ import annotations

import json
import re
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .handlers import (
    ApiError,
    api_ask,
    api_book_summary,
    api_chapter_content,
    api_config,
    api_doctor,
    api_get_session,
    api_list_books,
    api_search,
    api_update_session,
)

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>book-search reader</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4efe6;
      --panel: #fffaf3;
      --ink: #1a242d;
      --muted: #5f6d78;
      --accent: #9b3d2e;
      --accent-soft: #f2d5cc;
      --border: #dac8b8;
      --trust-cited: #2f6b4f;
      --trust-sources: #3d5f8f;
      --trust-warning: #9a6116;
      --trust-blocked: #7a3d2f;
      --shadow: rgba(26, 36, 45, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
      background: radial-gradient(circle at top left, #efe4d4, var(--bg) 50%);
      color: var(--ink);
      min-height: 100vh;
    }
    button, input, select, textarea {
      font: inherit;
    }
    .app {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr) 360px;
      min-height: 100vh;
    }
    .sidebar, .reader, .companion {
      border-right: 1px solid var(--border);
      background: var(--panel);
    }
    .companion { border-right: 0; }
    .sidebar {
      padding: 18px;
      overflow: auto;
    }
    .reader {
      padding: 28px 36px 48px;
      overflow: auto;
      background: linear-gradient(180deg, #fffdf8, #f8f1e8);
    }
    .companion {
      display: flex;
      flex-direction: column;
      min-height: 0;
    }
    h1, h2, h3 { margin-top: 0; }
    .brand {
      font-size: 1.35rem;
      margin-bottom: 4px;
    }
    .subtle { color: var(--muted); font-size: 0.92rem; }
    .book-picker, .spoiler-controls, .search-box {
      display: grid;
      gap: 8px;
      margin: 16px 0;
    }
    select, input, textarea {
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 10px 12px;
      background: #fff;
    }
    button {
      border: 0;
      border-radius: 10px;
      padding: 10px 14px;
      background: var(--accent);
      color: white;
      cursor: pointer;
    }
    button.secondary {
      background: #e8ddd2;
      color: var(--ink);
    }
    .chapter-list {
      list-style: none;
      padding: 0;
      margin: 12px 0 0;
      display: grid;
      gap: 6px;
    }
    .chapter-item {
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px 12px;
      cursor: pointer;
      background: #fff;
    }
    .chapter-item.active {
      border-color: var(--accent);
      background: var(--accent-soft);
    }
    .kind {
      display: inline-block;
      font-size: 0.75rem;
      padding: 2px 8px;
      border-radius: 999px;
      background: #ebe2d8;
      color: var(--muted);
      margin-right: 6px;
    }
    .status-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 16px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 0.85rem;
      background: #efe5da;
      color: var(--ink);
    }
    .pill.warn { background: #f8e8c8; color: var(--trust-warning); }
    .reader-content h1, .reader-content h2, .reader-content h3 {
      line-height: 1.25;
    }
    .reader-content p {
      line-height: 1.7;
      margin: 0 0 1rem;
    }
    .warnings {
      margin-top: 12px;
      padding: 12px;
      border-radius: 12px;
      background: #fff4df;
      border: 1px solid #ecd7a8;
      font-size: 0.9rem;
    }
    .companion-header, .search-header, .sources-header {
      padding: 16px 18px;
      border-bottom: 1px solid var(--border);
    }
    .chat-log {
      flex: 1;
      overflow: auto;
      padding: 16px 18px;
      display: grid;
      gap: 14px;
    }
    .message {
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px 14px;
      background: #fff;
    }
    .message.user { background: #f7efe6; }
    .trust-badge {
      display: inline-block;
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      text-transform: uppercase;
      padding: 4px 8px;
      border-radius: 999px;
      margin-bottom: 8px;
    }
    .trust-badge.cited { background: #d8eee4; color: var(--trust-cited); }
    .trust-badge.sources_available_no_inline_citations { background: #dbe7f7; color: var(--trust-sources); }
    .trust-badge.citation_warning { background: #f8e4c8; color: var(--trust-warning); }
    .trust-badge.spoiler_blocked, .trust-badge.uncited { background: #f2ddd8; color: var(--trust-blocked); }
    .source-card {
      border-top: 1px dashed var(--border);
      margin-top: 10px;
      padding-top: 10px;
      font-size: 0.9rem;
    }
    .source-card strong { display: block; }
    .source-excerpt { color: var(--muted); margin-top: 6px; }
    .composer {
      padding: 16px 18px;
      border-top: 1px solid var(--border);
      display: grid;
      gap: 8px;
    }
    .search-results, .sources-panel {
      padding: 0 18px 18px;
      overflow: auto;
    }
    .empty {
      color: var(--muted);
      font-style: italic;
    }
    .message-spoiler {
      font-size: 0.8rem;
      color: var(--muted);
      margin-bottom: 6px;
    }
    .message-body { line-height: 1.55; }
    .citation-warning {
      margin-top: 8px;
      font-size: 0.85rem;
      color: var(--trust-warning);
      background: #f8e8c8;
      border-radius: 8px;
      padding: 6px 8px;
    }
    .health {
      margin-top: 16px;
      font-size: 0.85rem;
      display: grid;
      gap: 6px;
    }
    .health-item {
      border-radius: 8px;
      padding: 6px 8px;
      background: #efe5da;
    }
    .health-item.warn { background: #f8e8c8; color: var(--trust-warning); }
    .health-item.fail { background: #f2ddd8; color: var(--trust-blocked); }
    @media (max-width: 1100px) {
      .app { grid-template-columns: 1fr; }
      .sidebar, .companion { border-right: 0; border-bottom: 1px solid var(--border); }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">book-search</div>
      <div class="subtle">Source-forward reading companion</div>
      <div class="book-picker">
        <label for="bookSelect">Book</label>
        <select id="bookSelect"></select>
      </div>
      <div class="spoiler-controls">
        <label for="chapterSelect">Current chapter</label>
        <select id="chapterSelect"></select>
        <label for="spoilerInput">Spoiler guard (blank = off)</label>
        <input id="spoilerInput" type="number" min="1" placeholder="auto-linked when chapter set" />
        <button id="savePositionBtn" class="secondary">Save reading position</button>
      </div>
      <div id="spoilerState" class="pill">Spoiler guard off</div>
      <div id="contentStart" class="subtle"></div>
      <ul id="chapterList" class="chapter-list"></ul>
      <div id="warnings" class="warnings" hidden></div>
      <div id="healthBar" class="health"></div>
    </aside>

    <main class="reader">
      <div class="status-bar">
        <span id="bookTitle" class="pill">Select a book</span>
        <span id="chapterTitle" class="pill">Chapter</span>
      </div>
      <article id="readerContent" class="reader-content">
        <p class="empty">Choose a chapter to begin reading extracted Markdown.</p>
      </article>
    </main>

    <section class="companion">
      <div class="companion-header">
        <h2>Ask</h2>
        <div class="subtle">Grounded in retrieved excerpts. Spoiler guard enforced.</div>
      </div>
      <div id="chatLog" class="chat-log"></div>
      <div class="composer">
        <textarea id="questionInput" rows="3" placeholder="Ask about the current chapter..."></textarea>
        <button id="askBtn">Ask</button>
      </div>
      <div class="search-header">
        <h3>Text search</h3>
        <div class="subtle">Lexical search, not semantic.</div>
        <div class="search-box">
          <input id="searchInput" placeholder="Search chapter text" />
          <button id="searchBtn" class="secondary">Search</button>
        </div>
      </div>
      <div id="searchResults" class="search-results"></div>
      <div class="sources-header">
        <h3>Latest sources</h3>
        <div class="subtle">Backend source cards are the primary trust signal.</div>
      </div>
      <div id="sourcesPanel" class="sources-panel"></div>
    </section>
  </div>
  <script>
    const state = {
      bookId: null,
      book: null,
      chapterIndex: null,
      autoSpoiler: true,
    };

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error || `Request failed (${response.status})`);
      }
      return payload;
    }

    function trustClass(status) {
      return status || "uncited";
    }

    function escapeHtml(value) {
      return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[ch]);
    }

    function formatText(value) {
      return escapeHtml(value).replace(/\\n/g, "<br>");
    }

    function renderSourceCards(sources, target) {
      target.innerHTML = "";
      if (!sources || !sources.length) {
        target.innerHTML = '<p class="empty">No sources yet.</p>';
        return;
      }
      for (const source of sources) {
        const card = document.createElement("div");
        card.className = "source-card";
        card.innerHTML = `
          <strong>${escapeHtml(source.chunk_id)}</strong>
          <div>Ch ${escapeHtml(source.chapter_index)}: ${escapeHtml(source.chapter_title)}</div>
          ${source.heading ? `<div>Heading: ${escapeHtml(source.heading)}</div>` : ""}
          <div class="source-excerpt">"${escapeHtml(source.excerpt)}"</div>
        `;
        card.addEventListener("click", () => loadChapter(source.chapter_index));
        target.appendChild(card);
      }
    }

    function appendMessage(role, text, meta = {}) {
      const log = document.getElementById("chatLog");
      const item = document.createElement("div");
      item.className = `message ${role}`;
      const badge = meta.trust_status
        ? `<span class="trust-badge ${trustClass(meta.trust_status)}">${escapeHtml(meta.trust_label || meta.trust_status)}</span>`
        : "";
      const spoiler = meta.spoiler_state
        ? `<div class="message-spoiler">${escapeHtml(meta.spoiler_state.label)}</div>`
        : "";
      const unknown = (meta.citation_check && meta.citation_check.unknown_chunk_ids) || [];
      const citationWarning = unknown.length
        ? `<div class="citation-warning">⚠ Model cited chunk ids not in retrieval: ${escapeHtml(unknown.join(", "))}</div>`
        : "";
      const sources = meta.sources || [];
      const sourceHtml = sources.map((source) => `
        <div class="source-card">
          <strong>${escapeHtml(source.chunk_id)}</strong>
          <div>Ch ${escapeHtml(source.chapter_index)}: ${escapeHtml(source.chapter_title)}</div>
          <div class="source-excerpt">"${escapeHtml(source.excerpt)}"</div>
        </div>
      `).join("");
      item.innerHTML = `${badge}${spoiler}<div class="message-body">${formatText(text)}</div>${citationWarning}${sourceHtml}`;
      log.appendChild(item);
      log.scrollTop = log.scrollHeight;
      if (role === "assistant") {
        renderSourceCards(sources, document.getElementById("sourcesPanel"));
      }
    }

    async function loadBooks() {
      const books = await api("/api/books");
      const select = document.getElementById("bookSelect");
      select.innerHTML = "";
      for (const book of books) {
        const option = document.createElement("option");
        option.value = book.book_id;
        option.textContent = `${book.title} (${book.chapter_count} ch)`;
        select.appendChild(option);
      }
      if (books.length) {
        select.value = books[0].book_id;
        await loadBook(books[0].book_id);
      }
    }

    async function loadBook(bookId) {
      state.bookId = bookId;
      state.book = await api(`/api/books/${encodeURIComponent(bookId)}`);
      document.getElementById("bookTitle").textContent = `${state.book.title} — ${state.book.author}`;
      const start = state.book.content_start_chapter;
      document.getElementById("contentStart").textContent = start
        ? `Content starts at chapter ${start}`
        : "";
      const warnings = state.book.extraction_warnings || [];
      const warningsEl = document.getElementById("warnings");
      if (warnings.length) {
        warningsEl.hidden = false;
        warningsEl.innerHTML = `<strong>Extraction warnings</strong><ul>${warnings.map((w) => `<li>${w}</li>`).join("")}</ul>`;
      } else {
        warningsEl.hidden = true;
      }
      renderChapterList();
      populateChapterSelect();
      const session = state.book.session || {};
      if (session.current_chapter) {
        state.chapterIndex = session.current_chapter;
        document.getElementById("chapterSelect").value = String(session.current_chapter);
        await loadChapter(session.current_chapter);
      }
      if (session.max_chapter) {
        document.getElementById("spoilerInput").value = String(session.max_chapter);
      }
      await refreshSpoilerState();
    }

    function renderChapterList() {
      const list = document.getElementById("chapterList");
      list.innerHTML = "";
      for (const chapter of state.book.chapters || []) {
        const item = document.createElement("li");
        item.className = "chapter-item" + (chapter.index === state.chapterIndex ? " active" : "");
        item.innerHTML = `<span class="kind">${chapter.kind}</span>${chapter.index}. ${chapter.title}`;
        item.addEventListener("click", () => {
          state.chapterIndex = chapter.index;
          document.getElementById("chapterSelect").value = String(chapter.index);
          loadChapter(chapter.index);
          renderChapterList();
        });
        list.appendChild(item);
      }
    }

    function populateChapterSelect() {
      const select = document.getElementById("chapterSelect");
      select.innerHTML = "";
      for (const chapter of state.book.chapters || []) {
        const option = document.createElement("option");
        option.value = String(chapter.index);
        option.textContent = `${chapter.index}. ${chapter.title}`;
        select.appendChild(option);
      }
    }

    async function loadChapter(index) {
      state.chapterIndex = Number(index);
      const chapter = await api(`/api/books/${encodeURIComponent(state.bookId)}/chapters/${index}`);
      document.getElementById("chapterTitle").textContent = `${chapter.index}. ${chapter.title} (${chapter.kind})`;
      document.getElementById("readerContent").innerHTML = chapter.html;
      renderChapterList();
    }

    async function refreshSpoilerState() {
      const session = await api(`/api/books/${encodeURIComponent(state.bookId)}/session`);
      const pill = document.getElementById("spoilerState");
      pill.textContent = session.spoiler_state.label;
      pill.className = "pill" + (session.spoiler_state.active ? "" : " warn");
    }

    async function savePosition() {
      const chapter = Number(document.getElementById("chapterSelect").value);
      const spoilerRaw = document.getElementById("spoilerInput").value;
      const body = {
        current_chapter: chapter,
        max_chapter: spoilerRaw ? Number(spoilerRaw) : null,
        auto_spoiler: !spoilerRaw,
      };
      await api(`/api/books/${encodeURIComponent(state.bookId)}/session`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      state.chapterIndex = chapter;
      await loadChapter(chapter);
      await refreshSpoilerState();
    }

    async function askQuestion() {
      const question = document.getElementById("questionInput").value.trim();
      if (!question) return;
      appendMessage("user", question);
      document.getElementById("questionInput").value = "";
      const spoilerRaw = document.getElementById("spoilerInput").value;
      const payload = await api(`/api/books/${encodeURIComponent(state.bookId)}/ask`, {
        method: "POST",
        body: JSON.stringify({
          question,
          current_chapter: state.chapterIndex,
          max_chapter: spoilerRaw ? Number(spoilerRaw) : null,
          auto_spoiler: !spoilerRaw,
        }),
      });
      appendMessage("assistant", payload.answer, payload);
      await refreshSpoilerState();
    }

    async function runSearch() {
      const query = document.getElementById("searchInput").value.trim();
      if (!query) return;
      const spoilerRaw = document.getElementById("spoilerInput").value;
      const params = new URLSearchParams({
        q: query,
        chapter: String(state.chapterIndex || ""),
        spoiler: spoilerRaw || "",
      });
      const payload = await api(`/api/books/${encodeURIComponent(state.bookId)}/search?${params}`);
      const target = document.getElementById("searchResults");
      target.innerHTML = `<p class="subtle">${escapeHtml(payload.note)}</p>`;
      for (const result of payload.results || []) {
        const card = document.createElement("div");
        card.className = "source-card";
        card.innerHTML = `
          <strong>${escapeHtml(result.chunk_id)}</strong>
          <div>Ch ${escapeHtml(result.chapter_index)}: ${escapeHtml(result.chapter_title)}</div>
          <div class="source-excerpt">"${escapeHtml(result.text.slice(0, 220))}..."</div>
        `;
        card.addEventListener("click", () => loadChapter(result.chapter_index));
        target.appendChild(card);
      }
    }

    async function loadHealth() {
      const el = document.getElementById("healthBar");
      try {
        const checks = await api("/api/doctor");
        const issues = (checks || []).filter((check) => check.status !== "ok");
        if (!issues.length) {
          el.innerHTML = '<div class="subtle">Health checks: all OK</div>';
          return;
        }
        el.innerHTML =
          "<strong>Health checks</strong>" +
          issues
            .map(
              (check) =>
                `<div class="health-item ${check.status}"><span class="kind">${escapeHtml(check.status)}</span>${escapeHtml(check.message)}</div>`
            )
            .join("");
      } catch (error) {
        el.innerHTML = `<div class="subtle">Health check unavailable: ${escapeHtml(error.message)}</div>`;
      }
    }

    document.getElementById("bookSelect").addEventListener("change", (event) => loadBook(event.target.value));
    document.getElementById("chapterSelect").addEventListener("change", (event) => loadChapter(event.target.value));
    document.getElementById("savePositionBtn").addEventListener("click", savePosition);
    document.getElementById("askBtn").addEventListener("click", askQuestion);
    document.getElementById("searchBtn").addEventListener("click", runSearch);
    loadBooks().catch((error) => {
      document.getElementById("readerContent").innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
    });
    loadHealth();
  </script>
</body>
</html>
"""


class BookSearchHandler(BaseHTTPRequestHandler):
    workspace: Path | None = None
    default_book_id: str | None = None

    def log_message(self, format: str, *args) -> None:
        return

    def _send_json(self, payload: object, *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, *, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        return payload if isinstance(payload, dict) else {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/":
                return self._send_html(INDEX_HTML)

            if path == "/api/books":
                return self._send_json(api_list_books(self.workspace))

            if path == "/api/config":
                return self._send_json(api_config(self.workspace))

            if path == "/api/doctor":
                return self._send_json(api_doctor(self.workspace))

            book_match = re.fullmatch(r"/api/books/([^/]+)", path)
            if book_match:
                return self._send_json(api_book_summary(book_match.group(1), self.workspace))

            chapter_match = re.fullmatch(r"/api/books/([^/]+)/chapters/(\d+)", path)
            if chapter_match:
                return self._send_json(
                    api_chapter_content(chapter_match.group(1), int(chapter_match.group(2)), self.workspace)
                )

            session_match = re.fullmatch(r"/api/books/([^/]+)/session", path)
            if session_match:
                return self._send_json(api_get_session(session_match.group(1), self.workspace))

            search_match = re.fullmatch(r"/api/books/([^/]+)/search", path)
            if search_match:
                params = parse_qs(parsed.query)
                chapter = _query_int(params, "chapter")
                spoiler = _query_int(params, "spoiler")
                return self._send_json(
                    api_search(
                        search_match.group(1),
                        query=_query_str(params, "q"),
                        current_chapter=chapter,
                        max_chapter=spoiler,
                        workspace=self.workspace,
                    )
                )

            self._send_json({"error": "Not found"}, status=404)
        except ApiError as error:
            self._send_json({"error": str(error)}, status=error.status)
        except FileNotFoundError as error:
            self._send_json({"error": str(error)}, status=404)
        except Exception as error:
            self._send_json({"error": str(error)}, status=500)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        try:
            session_match = re.fullmatch(r"/api/books/([^/]+)/session", parsed.path)
            if session_match:
                body = self._read_json_body()
                return self._send_json(
                    api_update_session(
                        session_match.group(1),
                        current_chapter=body.get("current_chapter"),
                        max_chapter=body.get("max_chapter"),
                        auto_spoiler=bool(body.get("auto_spoiler", True)),
                        workspace=self.workspace,
                    )
                )
            self._send_json({"error": "Not found"}, status=404)
        except ApiError as error:
            self._send_json({"error": str(error)}, status=error.status)
        except FileNotFoundError as error:
            self._send_json({"error": str(error)}, status=404)
        except Exception as error:
            self._send_json({"error": str(error)}, status=500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            ask_match = re.fullmatch(r"/api/books/([^/]+)/ask", parsed.path)
            if ask_match:
                body = self._read_json_body()
                return self._send_json(
                    api_ask(
                        ask_match.group(1),
                        question=str(body.get("question", "")),
                        current_chapter=body.get("current_chapter"),
                        max_chapter=body.get("max_chapter"),
                        auto_spoiler=bool(body.get("auto_spoiler", True)),
                        model=body.get("model"),
                        workspace=self.workspace,
                    )
                )
            self._send_json({"error": "Not found"}, status=404)
        except ApiError as error:
            self._send_json({"error": str(error)}, status=error.status)
        except FileNotFoundError as error:
            self._send_json({"error": str(error)}, status=404)
        except Exception as error:
            self._send_json({"error": str(error)}, status=500)


def _query_str(params: dict, key: str) -> str:
    values = params.get(key, [])
    return values[0] if values else ""


def _query_int(params: dict, key: str) -> int | None:
    value = _query_str(params, key).strip()
    if not value:
        return None
    return int(value)


def serve_ui(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    workspace: Path | None = None,
    book_id: str | None = None,
    open_browser: bool = False,
) -> None:
    handler = partial(BookSearchHandler)
    handler.workspace = workspace
    handler.default_book_id = book_id
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"book-search UI running at {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()