# Project Review: `book-search`

## Executive summary

`book-search` has a strong product idea: a local, chapter-aware, spoiler-safe reading companion for books. The most compelling wedge is not generic “chat with documents,” but this narrower promise:

> Ingest a local EPUB, preserve chapter structure, set my reading position, ask questions, and get grounded answers with citations that avoid spoilers.

The current architecture is appropriately simple for an early-stage project: EPUB extraction to chapter Markdown, lexical retrieval, chapter/spoiler filtering, and an LLM chat interface. The main recommendation is to resist broadening scope too soon. Make the existing loop trustworthy before expanding into an integrated reader UI, PDF support, personas, or embeddings.

## Current strengths

- **Clear user value:** readers often want recall, clarification, summaries, and thematic discussion without spoilers.
- **Distinctive product hook:** spoiler-aware chapter grounding is more specific and useful than generic document Q&A.
- **Local-first shape:** source books and extracted Markdown stay in a local workspace and are inspectable.
- **Simple architecture:** EPUB → chapter Markdown → retrieval → grounded prompt is a good baseline.
- **Low dependency footprint:** the core package has no required runtime dependencies; LLM support is optional.
- **Good early workflow:** `ingest`, `list`, `show`, `ask`, and `chat` cover the basic user journey.

## Recommended near-term scope

Keep the v0/v1 product focused on the active-reading companion loop:

1. Ingest an EPUB.
2. Preserve chapter order and chapter text.
3. Let the reader set their current chapter/spoiler limit.
4. Answer questions using only allowed book excerpts.
5. Show trustworthy citations/sources.

This scope is valuable enough on its own and provides a strong foundation for later UI or retrieval improvements.

## Highest-priority improvements

### 1. Make citations auditable

Current answers instruct the model to cite chapters, but citations are not fully backed by persistent source spans. The model can still cite loosely or invent references.

Recommended improvements:

- Assign stable IDs to retrieved chunks.
- Store chunk metadata such as:
  - `book_id`
  - `chapter_index`
  - `chapter_title`
  - `chunk_index`
  - source file path
  - paragraph ID or character offsets, if practical
- Return citations from retrieval metadata rather than relying only on model-generated citations.
- Add a CLI option to show the exact retrieved snippets used for an answer.
- Consider validating that displayed citations refer only to retrieved/allowed chunks.

This does not require embeddings or a vector database. It strengthens the current lexical retrieval pipeline.

### 2. Strengthen spoiler guard semantics

The spoiler guard is central to the product and should have explicit, testable behavior.

Clarify:

- What counts as a chapter?
- Are front matter, prologues, epilogues, notes, and appendices included in chapter numbering?
- What happens if extraction order is wrong?
- Should `current_chapter` automatically imply `max_chapter`, or should they remain separate?
- How can a user intentionally override spoiler protection?
- What should the assistant say when the answer exists only after the spoiler limit?

Preferred response pattern:

> I can only use chapters 1–7, and the provided excerpts do not answer that yet without spoilers.

### 3. Add product-level retrieval/evaluation fixtures

The project already has tests, but the core promise would benefit from small scenario-based evals.

Suggested eval cases:

- “Summarize chapter N” retrieves mostly chapter N.
- “Who is X?” retrieves the chapter where X is introduced.
- “What happened to Y?” respects `max_chapter`.
- A question whose answer appears only later produces uncertainty/refusal.
- “What are the recurring themes so far?” uses only allowed chapters.
- Current-chapter retrieval boost works predictably.

These tests will be more valuable than adding embeddings prematurely because they clarify whether failures are caused by extraction, chunking, scoring, or prompting.

### 4. Improve CLI ergonomics before building a reader UI

Before investing in a full integrated reader, polish the CLI workflow.

Possible additions:

- `book-search chapters <book>` — list chapters without dumping full metadata.
- `book-search position <book> set <chapter>` — persist reading position outside chat.
- `book-search ask <book> "question" --show-sources` — display retrieved snippets.
- `book-search search <book> <query>` — search without calling an LLM.
- `book-search delete <book>` — remove an ingested book safely.
- `book-search doctor` — validate API keys, optional dependencies, and workspace layout.

A polished CLI will expose real user workflow problems faster than a premature UI.

## Gaps to clarify

### Product requirements

- Who is the first target user?
  - fiction readers
  - nonfiction readers
  - students
  - researchers
  - book clubs
  - language learners
- Is the main use case recall, analysis, summarization, discussion, or study?
- Is privacy/local-first a core selling point?
- Should the app eventually support offline/local LLMs?
- Should it operate on one book at a time or across a personal library?
- How important is no-spoiler correctness compared with answer completeness?

### Functional requirements

- Book deletion behavior.
- Duplicate EPUB detection.
- Reimport behavior.
- Persistent reading position outside chat sessions.
- Source inspection/debug retrieval.
- Manual chapter correction, renaming, or reordering.
- Search-only mode without an LLM.
- Handling front matter, notes, appendices, and epilogues.
- Chat/session export.
- Configurable data directory and model settings.

### Technical requirements

- Stable chunk IDs.
- Persistent retrieval metadata.
- Citation validation.
- Extraction warnings.
- Deterministic fake-LLM tests.
- Golden EPUB fixtures.
- Data format/schema versioning for future migrations.
- Graceful behavior when optional dependencies are missing.

## Scope risks

### Integrated reader UI

An integrated reader UI is attractive, but it can consume the project. It introduces rendering, navigation, themes, annotations, progress sync, accessibility, selection-based Q&A, and layout bugs.

Recommendation: defer until the CLI companion loop proves useful. If built, start with a minimal Markdown reader plus chat pane rather than a full EPUB reader.

### PDF support

PDF support is a substantially different problem. PDFs lack reliable chapter structure, semantic headings, reading order, and paragraph flow. Good support may require OCR, layout analysis, page-based citations, and different spoiler semantics.

Recommendation: defer until EPUB support is reliable and users explicitly demand PDF support.

### Author persona layer

An author persona could be delightful, but it can undermine groundedness or imply the system authentically speaks as the author.

Safer framing:

- concise explainer
- book club mode
- Socratic tutor
- literary critic
- character/worldbuilding focus

Avoid promising an authentic author voice unless the system has strong source material and clear disclaimers.

### Embeddings/vector search

Do not add embeddings by default yet. Lexical retrieval is a reasonable baseline. First determine whether retrieval failures are caused by:

- bad extraction,
- weak chapter structure,
- poor chunking,
- missing metadata,
- citation weakness,
- or true semantic recall limitations.

If needed later, add embeddings as optional hybrid retrieval or reranking rather than as a required dependency.

## Suggested roadmap

### P0: Trust the current loop

- Stable chunk metadata and IDs.
- Auditable source display.
- Spoiler behavior tests.
- Product-level retrieval evals.
- Better chapter/source inspection commands.

### P1: Make ingestion reliable

- Extraction warnings.
- Better front matter detection.
- Stable chapter IDs.
- Better handling of odd EPUB structures.
- Duplicate and reimport behavior.

### P2: Polish the user workflow

- Search-only command.
- Position management command.
- Session export/reset.
- Better model/config diagnostics.
- Optional SQLite/FTS if JSON/files become limiting.

### P3: Expand carefully

Only after the core loop is trustworthy:

- minimal reader UI,
- optional embeddings/hybrid retrieval,
- local model support,
- PDF support,
- discussion-style presets.

## Bottom line

The strongest version of this project is not “an AI reader for every document format.” It is:

> A trustworthy, spoiler-safe companion for books you are actively reading.

The next best investment is the trust layer: reliable chapter structure, stable chunks, auditable citations, spoiler-correct retrieval, and small evals. Once users believe the answers and the spoiler guard, the UI/PDF/persona ideas become much safer to build.
