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

List chapters:

```bash
book-search chapters enshittification-cory-doctorow
```

Search without an LLM:

```bash
book-search search enshittification-cory-doctorow "enshittification" --chapter 7 --spoiler 7
```

Ask a one-shot question:

```bash
book-search ask enshittification-cory-doctorow "What is enshittification?" \
  --chapter 7 --spoiler 7 --show-sources
```

Interactive companion (set chapter as you read):

```bash
book-search chat enshittification-cory-doctorow --chapter 7 --spoiler 7 --show-sources
```

Persist reading position:

```bash
book-search position enshittification-cory-doctorow set 7 --spoiler 7
book-search position enshittification-cory-doctorow show
```

Chat commands: `/chapter N`, `/spoiler N`, `/sources`, `/chapters`, `/clear`, `/quit`

Retrieved chunks use stable ids like `book-id:ch007:c001` and are shown independently of model prose.

### Spoiler guard semantics

- Spine order defines chapter numbers (including front matter).
- Chapters are classified as `front_matter`, `body`, or `back_matter`; `content_start_chapter` marks where reading usually begins.
- `--chapter N` auto-links spoiler guard to chapter N unless you pass `--spoiler` or `--no-spoiler-auto`.
- `/spoiler off` intentionally disables spoiler protection.
- When no relevant excerpts exist within the spoiler limit, the app returns a deterministic refusal without calling the LLM.

Run the spoiler eval suite (optional LLM judge):

```bash
book-search eval spoiler
book-search eval spoiler --judge-model minimax/minimax-m2.5
```

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
- [x] Stable chunk IDs + auditable `--show-sources`
- [x] `chapters`, `search`, `position` CLI commands
- [ ] Integrated reader UI
- [ ] PDF support
- [ ] Author persona layer