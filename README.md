# book-search

A reading companion for local books. Ingest EPUBs, keep chapter structure, and chat with a grounded agent while you read.

Ported from reusable components in `~/Github/tools/projects/book-to-skill` and `book-rlm`.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Optional: install [Calibre](https://calibre-ebook.com/) for richer EPUB metadata (`ebook-meta`).

For companion chat (OpenRouter recommended):

```bash
pip install -e ".[llm]"
export OPENROUTER_API_KEY=...
export BOOK_SEARCH_CHAT_MODEL=moonshotai/kimi-k2.6   # optional override
```

See recommended models:

```bash
book-search models
```

## Usage

Ingest an EPUB:

```bash
book-search ingest /path/to/book.epub
```

List ingested books:

```bash
book-search list
```

Show book details:

```bash
book-search show my-book-id
```

Ask a one-shot question:

```bash
book-search ask enshittification-cory-doctorow "What is enshittification?" --chapter 7

# try another free OpenRouter model
book-search ask enshittification-cory-doctorow "What is enshittification?" \
  --chapter 7 --model minimax/minimax-m2.5
```

Interactive companion (set chapter as you read):

```bash
book-search chat enshittification-cory-doctorow --chapter 7 --spoiler 7 \
  --model moonshotai/kimi-k2.6
```

Chat commands: `/chapter N`, `/spoiler N`, `/chapters`, `/clear`, `/quit`

## Data layout

```
data/books/<book-id>/
  source/          # copied EPUB
  extracted/       # combined book.md + calibre sidecars
  chapters/        # per-chapter markdown (001-title.md, ...)
  companion/       # persona and chat state (future)
  book.json        # metadata + chapter index
```

## Roadmap

- [x] EPUB ingestion with chapter markdown
- [x] Companion chat CLI (chapter-aware retrieval)
- [x] Reading position + spoiler guard
- [ ] Integrated reader UI
- [ ] PDF support
- [ ] Author persona layer