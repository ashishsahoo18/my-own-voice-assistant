# OLIVER 2.0 Security Architecture & Threat Model

**Version**: 2.0  
**Phase**: Phase 3 (Security and Permission Manager)  
**Status**: ACTIVE & ENFORCED

---

## 1. Executive Summary

OLIVER 2.0 operates as an agentic Windows assistant with native execution capabilities. Because it can launch applications, perform file operations, and send communications, security is designed with **defense-in-depth** and **zero implicit trust**. 

The fundamental security principle of OLIVER 2.0 is:
> **The LLM is an untrusted planner. The LLM NEVER makes final permission decisions or directly executes system commands.**

All actions, regardless of whether they originate from legacy regex matching, OLIVER intent classification, drop-in user skills, or direct Python calls, must pass through the **central `PolicyEngine`**.

---

## 2. Threat Model (STRIDE-Lite)

| Threat Category | Potential Attack Vector | OLIVER 2.0 Mitigation |
| :--- | :--- | :--- |
| **Spoofing** | Adversary or forged intent claiming user identity | Local execution only; no remote unauthenticated listeners; actions bound to local Windows session. |
| **Tampering** | Path traversal attacks (`../../Windows/System32`) or file overwrites | `PathSandbox` validates all file paths against allowlisted directory roots; blocks `..` escape and Windows system folders (`C:\Windows`, `C:\Program Files`, `.ssh`). |
| **Repudiation** | Actions taken without an audit trail | Structured JSON audit logging (`logs/audit.log`) records every policy evaluation, confirmation creation, approval, denial, and expiration with timestamps and sha-masked secrets. |
| **Information Disclosure** | Credentials, API keys, or private files exposed in logs or prompts | Redacted logger (`StructuredLogger`) masks API keys, secrets, tokens, and email addresses automatically. |
| **Denial of Service** | Rapid tool loops or infinite tool execution | Sliding-window `RateLimiter` caps sensitive calls (max 10 requests / 60 seconds); emergency `KillSwitch` invalidates all pending tokens and halts execution. |
| **Elevation of Privilege** | Prompt injection inducing assistant to execute arbitrary shell commands (`shell=True`, `eval()`) | Zero arbitrary shell execution; `shell=True` and raw `eval()` completely eradicated from codebase; central 4-tier risk gate requires human confirmation for sensitive/dangerous actions. |

---

## 3. Trust Boundaries

```
                 +-----------------------------------------------+
                 |              USER (Voice / Text)              |
                 +-----------------------+-----------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
|                                 UNTRUSTED ZONE                                  |
|  - Speech-to-Text Transcripts                                                   |
|  - Local LLM (Ollama / Llama 3.2)                                                |
|  - Drop-in User Skills / Untrusted Plugins                                      |
+----------------------------------------+----------------------------------------+
                                         |  Planned Tool Call & Arguments
                                         v
+---------------------------------------------------------------------------------+
|                           TRUSTED SECURITY BOUNDARY                             |
|                                                                                 |
|                        +------------------------------+                         |
|                        |     Central PolicyEngine     |                         |
|                        +---------------+--------------+                         |
|                                        |                                        |
|         +-------------------+----------+---------+--------------------+         |
|         |                   |                    |                    |         |
|         v                   v                    v                    v         |
|  [Kill Switch]        [Rate Limiter]      [Path Sandbox]    [Confirmation Mgr]  |
|  (Emergency halt)     (Sliding window)    (Allowlist/Jail)  (Expiring tokens)   |
+----------------------------------------+----------------------------------------+
                                         | ALLOW
                                         v
+---------------------------------------------------------------------------------+
|                              EXECUTION BOUNDARY                                 |
|  - Builtin Skill Handlers (shell=False, AST math, Recycle Bin SHFileOperationW) |
|  - Windows OS APIs (os.startfile, ctypes)                                       |
+---------------------------------------------------------------------------------+
```

---

## 4. Central 4-Tier Risk Policy

Every tool declared in the `SkillRegistry` possesses a strict `ToolRiskLevel`:

| Risk Tier | Name | Description | Policy Engine Action |
| :---: | :--- | :--- | :--- |
| **0** | **SAFE** | Read-only operations, Q&A, weather, time/date, search navigation | **Auto-Allow** |
| **1** | **LOW** | Creating temporary notes, opening applications, non-sensitive operations | **Auto-Allow with audit record** |
| **2** | **SENSITIVE** | Sending WhatsApp/email messages, account actions, modifying important files | **NeedConfirm** (Requires single-use token) |
| **3** | **DANGEROUS** | Deleting files, workstation shutdown/restart, credential access, system config | **NeedConfirm** (Strict confirmation preview) |

### Non-Bypassable Policy Gate
- In **OLIVER mode**, `IntentRouter.execute_route()` passes every tool invocation through `PolicyEngine.evaluate()`.
- In **Legacy mode**, `AshishAssistant.execute_confirmed_command()` passes every action through `PolicyEngine.evaluate()`.
- In **Direct invocation**, `SkillRegistry.execute_tool()` passes through `PolicyEngine.evaluate()`.

---

## 5. Confirmation Manager: Token Binding & Anti-Replay

1. **Exact-Effect Previews**: When an action requires confirmation, OLIVER generates a human-readable preview stating the exact operation, target, and parameters (e.g., `Delete 'report.txt' (moves to Windows Recycle Bin)`).
2. **Action-Bound Tokens**: A cryptographic UUIDv4 token is bound specifically to that action and its parameters.
3. **Strict Yes/No Grammar**: Affirmative tokens are accepted only with explicit confirmations (`yes`, `confirm`, `proceed`, etc.). Ambiguous answers (`maybe`, `why?`) are rejected safely.
4. **Single-Use Consumption**: Tokens are consumed upon the first verification attempt. Once used, they are tracked in an invalidation set to prevent replay attacks.
5. **Token Expiration**: Pending tokens expire automatically after 30 seconds (configurable via `security.confirmation_timeout_seconds`).
6. **Kill Switch Invalidation**: Engaging the emergency kill switch instantly purges and invalidates all pending tokens.

---

## 6. Path Sandbox & Safe Deletion

1. **Allowlisted Directory Roots**: By default, file operations are restricted to the user's home folder, desktop, documents, downloads, and the project workspace.
2. **Traversal Blocking**: Any path containing parent directory escapes (`..`) that resolves outside the allowed roots triggers an immediate `PathSandboxViolation`.
3. **Protected Windows Directories**: Access to sensitive Windows system folders (`C:\Windows`, `C:\Program Files`, `C:\Program Files (x86)`) and credential directories (`.ssh`, `.aws`, browser user profiles) is unconditionally rejected.
4. **Windows Recycle Bin Deletion**: Deletions are never performed with permanent unlinks (`os.remove`/`shutil.rmtree`). Files are moved to the Windows Recycle Bin using `SHFileOperationW` (`FOF_ALLOWUNDO`), or quarantined to a dedicated backup directory if the native shell call is unavailable.

---

## 7. Elimination of Arbitrary Execution

- **Zero `shell=True`**: All subprocess calls use explicit argument lists (`subprocess.Popen([cmd], shell=False)`).
- **Zero `eval()`**: All math and expression evaluation is parsed safely using Python's `ast` module (`ast.parse`) with strict whitelists of numeric constants and unary/binary arithmetic operators.
- **Arbitrary Command Denial**: Any tool requesting raw shell or command prompt execution is rejected by default by the `PolicyEngine`.

---

## 8. Audit Trail Specification

All security-relevant events are logged in structured JSON to `logs/audit.log` via `core.logging.AuditLogger`:
```json
{
  "timestamp": "2026-10-08T18:30:15.123456Z",
  "event_type": "POLICY_EVAL",
  "action": "files.delete_file",
  "risk_level": 3,
  "status": "NEED_CONFIRM",
  "details": {
    "summary": "Delete 'doc.txt' (moves to Windows Recycle Bin)."
  }
}
```
All API keys, phone numbers, and secrets are scrubbed prior to persistence.
