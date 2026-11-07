# OLIVER 3.0 — Master Architecture & Development Plan

**Project:** OLIVER 3.0  
**Purpose:** One personal AI assistant that works across Windows laptop and mobile  
**Starting point:** Existing OLIVER 2.0 codebase  
**Development approach:** Audit → Stabilize → Build incrementally → Test → Release

---

## 1. Vision

Build one intelligent personal assistant named **OLIVER** that can be used from both a Windows laptop and a mobile phone.

Both devices must connect to the same backend, identity, conversation history, preferences, and synchronized memory.

The user should be able to speak or type naturally and receive accurate, useful responses through text and voice.

OLIVER should answer general questions inside its own interface. It must not open ChatGPT or Claude as a substitute for answering.

## 2. Core requirements

- One OLIVER identity across all devices.
- Voice and text interaction.
- English, Hindi, and Odia support, tested separately.
- General AI questions answered inside OLIVER.
- Browser and productivity commands handled through existing skills.
- Explicit website-opening requests launch Firefox on Windows.
- Shared conversation history and synchronized memory.
- Mobile microphone access and spoken responses.
- Responsive communication between devices and backend.
- Safe handling of operating-system commands and personal data.
- Local-first AI operation wherever practical.
- Clear error messages when a device or local AI service is unavailable.

## 3. Technology architecture

| Layer | Technology | Responsibility |
|---|---|---|
| Windows frontend | Python + CustomTkinter | Existing desktop interface |
| Mobile frontend | Flutter + Dart | Android/iOS application |
| Backend | Python + FastAPI | Shared OLIVER services and APIs |
| Realtime communication | WebSockets | Streaming messages, status and events |
| AI inference | Existing Ollama + Llama 3.2 | Local AI responses |
| Speech-to-text | Existing Vosk; evaluate Whisper | Voice input |
| Text-to-speech | Inspect existing provider; evaluate Piper | Spoken responses |
| Cloud database | PostgreSQL | Shared account and synchronized data |
| Local database | Existing SQLite | Offline/local storage |
| Optional cache | Redis, only if justified | Caching and background coordination |
| Windows startup | Windows Task Scheduler | Optional greeting after login/wake |
| Mobile notifications | Platform notification services | Reminders and notifications |

Do not integrate a new provider or download a large model without inspecting the current system and obtaining approval.

## 4. Architecture principle

```text
                 ┌──────────────────────┐
                 │     OLIVER Backend   │
                 │ Python + FastAPI     │
                 │ Authentication       │
                 │ AI Orchestration     │
                 │ Memory and Commands  │
                 └──────────┬───────────┘
                            │
                    WebSocket / HTTPS
                     ┌──────┴──────┐
                     │             │
              ┌──────▼─────┐ ┌─────▼──────┐
              │ Windows    │ │ Mobile     │
              │ Python UI  │ │ Flutter UI │
              └────────────┘ └────────────┘
```

Both frontends must use shared backend services. Do not implement separate AI brains or independent memory systems for the two devices.

## 5. AI and voice design

Recommended request flow:

1. Capture user speech or typed text.
2. Convert speech to text using the selected STT provider.
3. Classify the request: conversation, browser action, productivity action, or another supported skill.
4. Apply permission and safety checks before executing actions.
5. Send conversational questions to the configured AI provider.
6. Stream the answer to the active frontend.
7. Convert the answer to speech when voice output is enabled.
8. Save the conversation and synchronize it according to the approved data policy.

The existing laptop Ollama installation may initially serve as the AI inference engine. Mobile access must use an authenticated, encrypted connection through the backend. Never expose an unauthenticated Ollama port directly to the internet.

If the laptop is offline or unavailable, OLIVER must communicate that limitation clearly. Do not silently switch to a paid API.

## 6. Data and synchronization

- Preserve `database/oliver.db`, its existing records, WAL files and migration history.
- Keep SQLite for local/offline operation.
- Introduce PostgreSQL only after a documented migration and synchronization design is approved.
- Define ownership, authentication, device identity and data access rules.
- Define how conflicts are handled when the same conversation or memory changes on two devices.
- Do not delete or automatically merge legacy AYRA databases.
- Do not run destructive migrations, resets or database cleanup during initial backend extraction.

## 7. Development phases

### Phase 0 — Existing project audit
**Status: Reported complete.**

- Inspect the current architecture and entry points.
- Document the database, services, dependencies and tests.
- Identify backend extraction seams.
- Record Git status and uncommitted changes.
- Produce `docs/ARCHITECTURE_AUDIT.md`.

No application code or data should be modified during this phase.

### Phase 0.5 — Stabilization
**Status: Pending explicit approval.**

- Inspect the duplicated `handle()` method in `ai/assistant.py`.
- Confirm the intended `request_id` behavior.
- Review current browser, voice, memory, task and reminder integrations.
- Fix only specifically approved issues.
- Run the relevant regression tests.
- Preserve existing database records and public behavior.

### Phase 1 — FastAPI backend foundation
**Status: Not started.**

- Introduce a backend application without replacing the existing desktop entry point.
- Define API request and response schemas.
- Add authentication and device identity design.
- Extract reusable AI and assistant services carefully.
- Add health checks and structured logging.
- Add API tests.
- Keep the existing Windows application functional.

### Phase 2 — Connect the Windows frontend
- Connect the existing CustomTkinter interface to the backend.
- Preserve the existing UI and working interactions.
- Support streaming text responses.
- Display backend connection and error states.
- Verify existing desktop skills still work.

### Phase 3 — Voice pipeline
- Integrate and verify speech-to-text.
- Integrate and verify text-to-speech.
- Support interruption and cancellation where technically possible.
- Test English, Hindi and Odia independently.
- Measure voice input and output latency.

### Phase 4 — Realtime communication
- Add WebSocket streaming.
- Support connection recovery and reconnect behavior.
- Handle disconnects and duplicate requests safely.
- Evaluate WebRTC or LiveKit only if actual audio-streaming requirements justify them.

### Phase 5 — Database and synchronization
- Document the PostgreSQL and SQLite responsibilities.
- Design authentication, data ownership and synchronization.
- Define offline behavior and conflict resolution.
- Test migration on a disposable copy before any production-data migration.

### Phase 6 — Flutter mobile application
- Build the mobile interface.
- Connect it to the same authenticated backend.
- Add text chat, microphone input and voice output.
- Display connection and synchronization status.
- Test on a real Android device.

### Phase 7 — Shared memory and productivity
- Connect conversations, preferences, reminders and tasks through shared services.
- Implement cross-device synchronization.
- Verify that users can access only their own data.

### Phase 8 — Device automation and notifications
- Add optional Windows login/wake greeting using Task Scheduler.
- Add mobile notifications.
- Require confirmation for sensitive or irreversible actions.
- Provide controls to disable greetings and notifications.

### Phase 9 — Security and reliability
- Enforce authentication and authorization.
- Use HTTPS and secure WebSocket connections.
- Protect credentials and tokens.
- Validate inputs and permissions.
- Add rate limits and safe error handling.
- Test unauthorized access and device disconnection.

### Phase 10 — Testing and release
- Run unit, integration and regression tests.
- Test Windows and Android independently.
- Test laptop-to-mobile synchronization.
- Measure response, speech and synchronization latency.
- Document installation, configuration, backup and recovery.
- Prepare a release checklist before declaring OLIVER 3.0 ready.

## 8. Performance measurements

Record actual measurements rather than describing OLIVER as fast without evidence.

Track:

- Speech-to-text completion time.
- AI time to first token.
- Full AI response time.
- Time to first audio.
- WebSocket response latency.
- Cross-device synchronization delay.
- Reconnection time after network interruption.

Record hardware, model, language, network and test conditions with the measurements.

## 9. Non-negotiable preservation rules

1. Do not replace the existing project with a new template.
2. Do not delete existing application features.
3. Do not delete or reset SQLite databases.
4. Do not discard uncommitted changes.
5. Do not overwrite working modules without inspecting their callers and tests.
6. Do not add paid APIs or services without explicit approval.
7. Do not expose local AI services directly to the public internet.
8. Do not automatically commit, push, tag or deploy.
9. Make small, reviewable changes with regression tests.
10. Stop and report if a required change risks existing data or functionality.

## 10. Approval gates

- Phase 0 audit does not authorize code changes.
- Phase 0.5 requires approval of the proposed stabilization changes.
- Phase 1 requires a verified backup, reviewed audit findings and explicit approval.
- Each later phase requires a report of changes, tests, limitations and remaining risks.
- Never treat a proposed architecture or a passing unit-test count as proof of full device-level functionality.

**Final goal:** One secure, reliable OLIVER assistant, accessible from Windows and mobile, with shared services, memory and conversations.

