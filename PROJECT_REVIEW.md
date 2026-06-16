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

---

# Second-pass review: trust loop readiness for UI

## Decision

After the recent trust-loop changes, the project is ready to begin a constrained integrated reader UI.

> Proceed to UI now, but keep the first UI source-forward, spoiler-forward, and deliberately narrow.

The backend trust loop is now sufficient for an MVP because answers are source-backed, spoiler-bounded, auditable, and covered by deterministic product evals. The remaining backend limitations are real, but they are quality and UX constraints rather than blockers to starting a cautious UI.

Do not block the first UI on semantic/vector retrieval, persisted chunk indexes, perfect EPUB parsing, PDF support, or exact passage highlighting.

## Verification

The following checks passed after the recent changes:

```bash
.venv/bin/python -m pytest
```

Result:

```text
42 passed
```

```bash
.venv/bin/python -m book_search eval all --no-judge
```

Result:

```text
All evals: 21/21 passed

Spoiler (5/5)
  [PASS] auto_link_spoiler
  [PASS] refusal_with_later_match
  [PASS] refusal_without_later_match
  [PASS] front_matter_classification
  [PASS] spoiler_excludes_later_retrieval
Retrieval (7/7)
  [PASS] summarize_chapter_prefers_target
  [PASS] character_introduction
  [PASS] spoiler_retrieval_excludes_later
  [PASS] themes_respect_spoiler
  [PASS] chapter_boost_predictable
  [PASS] search_returns_chunk_ids
  [PASS] later_answer_blocked
Ingestion (4/4)
  [PASS] watermark_warnings
  [PASS] warnings_stored_on_record
  [PASS] content_start_detected
  [PASS] duplicate_identifier_guard
Workflow (5/5)
  [PASS] session_export_includes_metadata
  [PASS] session_reset_clears_history
  [PASS] session_reset_keep_position
  [PASS] config_describe_includes_workspace
  [PASS] config_masks_api_keys
```

## What is now strong enough

### Spoiler loop

The spoiler behavior is now good enough for a UI MVP:

- `--chapter` can auto-link the spoiler guard.
- Explicit `--spoiler` still works.
- Users can intentionally disable spoiler protection.
- Retrieval enforces `max_chapter` before prompt construction.
- If no allowed excerpts match but later chapters do, the app returns a deterministic refusal before calling the LLM.
- Eval coverage exists for later-answer blocking, no-spoiler refusals, front matter classification, and retrieval exclusion.

### Source and citation loop

The app now has an auditable answer trail:

- stable chunk IDs such as `book-id:ch007:c001`,
- chunk-level source cards with chapter, title, heading, excerpt, and offsets,
- citation validation for model-cited chunk IDs,
- `--show-sources` and `/sources`,
- text search without an LLM,
- product eval coverage for chunk IDs and retrieval behavior.

The UI should treat backend-provided source cards as the primary trust mechanism. Inline model citations are useful, but should not be the only evidence shown to users.

### Workflow loop

The CLI now exposes the core primitives that a UI will need:

- `chapters`
- `search`
- `position`
- `session`
- `config`
- `doctor`
- `delete`
- `eval`

This indicates the user workflow has stabilized enough to put a first reader interface over it.

## Recommended small hardening before or during UI

Add a simple computed trust status for answer results so the UI can badge responses consistently.

Example:

```python
def answer_trust_status(result: dict) -> str:
    if result.get("spoiler_blocked"):
        return "spoiler_blocked"

    check = result.get("citation_check", {})
    if check.get("unknown_chunk_ids"):
        return "citation_warning"

    if result.get("sources") and not check.get("valid_chunk_ids"):
        return "sources_available_no_inline_citations"

    if check.get("valid_chunk_ids"):
        return "cited"

    return "uncited"
```

Potential UI badges:

- **Cited**
- **Sources available**
- **Citation warning**
- **Spoiler blocked**

This should not be treated as a blocker. It is a small bridge between backend trust signals and UI presentation.

Also avoid presenting `char_start` / `char_end` as exact highlight anchors. They are useful diagnostics, but the current offsets may not map cleanly to rendered full-chapter Markdown. In the UI, either hide offsets or label them as approximate.

## Remaining risks and guardrails

### Lexical retrieval can miss paraphrased questions

Retrieval remains lexical. It can miss vague or paraphrased questions such as “what does this mean?” if the query does not share enough terms with the text.

Guardrails:

- Let users include selected text in the question.
- Bias strongly to the current chapter.
- Always show source cards.
- Use copy like “based on these excerpts” rather than “the book says.”
- Consider semantic retrieval later only after real UI usage shows consistent recall failures.

### Dynamic chunks are not ideal for long-term annotations

Chunk IDs are generated from the current chapter Markdown and chunk order. This is acceptable for current Q&A, but less ideal for persistent annotations, saved source links, or re-ingestion stability.

Guardrails:

- Do not build persistent passage annotations in the first UI.
- If annotations become important, add a persisted chunk manifest/index at ingest time.

### Offsets are approximate

`char_start` and `char_end` should not be used for exact highlighting yet.

Guardrails:

- Source clicks should navigate to chapter and heading.
- If highlighting is attempted, search for the excerpt text as a best-effort behavior.
- Do not promise exact source highlights in the MVP.

### EPUB extraction is still strict

The EPUB parser still relies on `ElementTree` and can fail on malformed XHTML.

Guardrails:

- Focus the first UI on already-ingested books.
- Surface extraction errors and warnings clearly.
- Do not make arbitrary drag-and-drop EPUB import the centerpiece until parsing is more tolerant.

### Chapter classification is heuristic

Front/body/back matter classification is useful but imperfect.

Guardrails:

- Show chapter kind labels.
- Show `content_start_chapter`.
- Let users manually set current chapter and spoiler guard.
- Explain that chapter numbers follow EPUB spine order, including front matter.

### Inline citations are not guaranteed

The model is instructed to cite chunk IDs, and unknown cited IDs are detected, but answers are not rejected when the model omits inline citations.

Guardrails:

- Always show backend source cards independently of model prose.
- Badge answers as “Sources available” when source cards exist but inline citations are missing.
- Consider a later retry/repair step if missing inline citations become common.

## Safe first UI scope

### Reader pane

Build a simple reader around the extracted chapter Markdown:

- book list,
- chapter list,
- chapter Markdown display,
- current chapter selector,
- chapter kind labels: `front_matter`, `body`, `back_matter`,
- `content_start_chapter` display,
- manual spoiler override.

Avoid trying to become a full EPUB renderer in the first UI.

### Chat pane

Use the existing companion path:

- submit a question,
- pass current chapter,
- auto-link spoiler guard by default,
- allow explicit spoiler override,
- preserve deterministic spoiler refusal behavior.

The UI should display spoiler state prominently:

- “Using chapters 1–N”
- “Auto-linked to current chapter”
- “Spoiler guard off” only when intentionally disabled

### Sources pane

Always show source cards for each answer:

- chunk ID,
- chapter number and title,
- heading,
- excerpt,
- citation warning if the model cited an unknown chunk ID.

Do not hide sources behind an advanced debug toggle in the first UI. Source visibility is part of the trust loop.

### Search pane

Expose the existing lexical search.

Label it honestly as text/book search, not semantic search.

### Ingestion/status surface

Show ingestion and project health signals:

- extraction warnings,
- content start chapter,
- chapter classification,
- config/doctor issues when relevant.

## What not to build yet

Defer these until the UI proves the core loop is useful:

- exact passage highlighting,
- persistent annotations tied to chunk offsets,
- vector/embedding search,
- PDF support,
- polished arbitrary EPUB import flow,
- author persona layer,
- cross-book/library search.

## Updated recommendation

The trust loop is now set for a constrained UI MVP.

The next product risk is no longer primarily “is the backend trustworthy enough?” It is:

> Does the UI preserve and communicate backend trust signals instead of hiding them?

Start the UI only if it keeps spoiler state, retrieved sources, warnings, and uncertainty visible. If the UI presents answers as polished standalone AI prose without source cards and spoiler state, it will weaken the trust loop that the backend now provides.
