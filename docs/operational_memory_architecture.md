# Operational Memory Architecture

Branch: `operational-memory-mvp`
Date: 2026-06-17

## 1. Executive Summary

The new line of work turns unstructured communication into structured
operational state. The MVP accepts simulated text messages only and extracts:

- Decisions
- Tasks
- Issues
- Information
- Open questions

The value is not answering like a chatbot. The value is maintaining a concise,
verifiable representation of what is actually happening.

The first implementation is intentionally small: `POST /operational-state`,
stateless, no real WhatsApp, no email ingestion, no audio, no UI, no proactive
messages.

## 2. Repository Analysis

Reusable infrastructure:

- FastAPI app and router structure in `main.py` and `api/*`.
- LLM gateway in `core/llm_service.py`.
- Project logging via `core/log.py`.
- Pytest test harness.
- Optional future storage via `core/storage.py`.

Areas intentionally left untouched:

- `core/proactor.py`
- relational/personality memory
- TTS/STT
- face recognition
- document upload/query
- WhatsApp/Telegram/Instagram/Moltbook production integrations
- proactive automation systems

## 3. Reusable Components

- HTTP routing: add one isolated router, `api/operational.py`.
- LLM calls: reuse `llm_service._call_model` with a JSON-only extraction prompt.
- Logging: use `OPERATIONAL_MEMORY_*` events.
- Tests: mock the LLM and assert deterministic schema behavior.

## 4. Components To Isolate

The operational memory domain must stay separate from Genesi's conversational
identity. It lives under:

```text
api/operational.py
core/operational_memory/
tests/test_operational_memory.py
```

It must not import proactor, relational engines, social bots, TTS, STT, or
automation services.

## 5. Components To Create

- `core/operational_memory/models.py`: minimal data model.
- `core/operational_memory/extractor.py`: messages to operational state.
- `api/operational.py`: endpoint `POST /operational-state`.
- `tests/test_operational_memory.py`: schema and normalization tests.

## 6. Dependencies

No new external dependencies are required. The MVP uses the existing FastAPI,
Pydantic, LLM service, and pytest stack.

## 7. Technical Risks

- Hallucinated tasks or decisions.
- Misclassified items between decisions, tasks, and issues.
- Non-deterministic LLM output.
- Long threads exceeding context limits.
- Weak source traceability.

Mitigation in MVP: require a `source` for each extracted item, drop items
without source, normalize IDs deterministically, and test with mocked LLM output.

## 8. Product Risks

- Users may not trust an AI-generated operational state.
- Verification effort may exceed the time saved.
- Real value may depend on difficult integrations, not extraction quality.
- Existing tools may already solve enough of the problem for many users.

## 9. Limits Of The Idea

The system works best on short, explicit, factual text. It will struggle with
implicit decisions, irony, missing context, vague ownership, and social nuance.
The output is a draft operational state, not a source of truth.

## 10. Possible Reasons For Failure

- Accuracy is not high enough for operational responsibility.
- Users do not return to the generated state after the first curiosity test.
- The product needs real channel integration before value is visible.
- Privacy and consent issues block adoption.
- The workflow is perceived as another place to maintain, not a time saver.

## 11. Estimated Code Reuse

Estimated reuse: 30-40% infrastructure reuse, near 0% domain reuse.

Reused: HTTP app, LLM gateway, logging, test framework, optional storage.
New: domain model, prompt, extraction rules, endpoint, validation strategy.

## 12. Roadmap

- M0: passive mode and automation shutdown on `gold-faro-stable`.
- M1: stateless text-only extraction endpoint.
- M2: persisted operational boards and incremental merge.
- M3: one real ingestion channel, only after validation.
- M4: minimal read-only UI, only if the state proves useful.

## 13. MVP Plan

Input:

```json
{
  "messages": ["...", "..."]
}
```

Output:

```json
{
  "decisions": [],
  "tasks": [],
  "issues": [],
  "information": [],
  "open_questions": []
}
```

The MVP has one LLM extraction pass, deterministic cleanup, source-required
items, and tests with mocked LLM responses.

## 14. Validation Strategy

Validate with 15-20 anonymized or simulated real-world threads. Compare the
AI extraction against a manual reference extraction.

Initial success metric: at least 70% precision on tasks and decisions, with
source references that a human can verify quickly.

## 15. MVP Data Model

Decision:

- `id`
- `text`
- `source`

Task:

- `id`
- `text`
- `owner`
- `due`
- `source`

Issue:

- `id`
- `text`
- `source`

Information:

- `id`
- `text`
- `source`

Question:

- `id`
- `text`
- `source`

Persistence: none in M1. Future storage key: `operational_state:{board_id}`.

## 16. Why This Could Fail

This could fail because extracting state is not the same as creating trust. If
the user must re-check every item, the product saves no time. If ownership or
decisions are wrong even occasionally, confidence drops quickly. The easiest
MVP also avoids the hardest part: safely ingesting real communication channels.

## 17. Validate In Less Than 30 Days

Week 1: build the endpoint and run it on test threads.

Week 2: show generated state to 5-8 people with messy threads.

Week 3: run a Wizard-of-Oz test where state is updated daily for a few real
threads.

Week 4: decide go/no-go using accuracy and repeat usage. If people do not come
back to the state, stop or pivot.

## 18. What Not To Build Now

- Real WhatsApp, email, Telegram, or audio ingestion.
- UI/dashboard.
- Proactive notifications.
- TTS/STT, avatar, personality, or relationship features.
- Billing, teams, permissions.
- Complex date parsing.
- Multi-board persistence.

The only thing to build now is the smallest verifiable text-to-state endpoint.
