import time, json, os, sys
from pathlib import Path

# Ensure project root is in path
root = Path(__file__).resolve().parent.parent
sys.path.append(str(root))

from ai.assistant import AshishAssistant

# Wrapper to capture timing
class TimedAssistant(AshishAssistant):
    def handle(self, message: str) -> str:
        start = time.perf_counter()
        result = super().handle(message)
        elapsed = time.perf_counter() - start
        # Store timing in a global dict
        timings.setdefault(message, {})['total'] = elapsed
        return result

    def handle_result(self, message: str, confirmation_token=None):
        start = time.perf_counter()
        result = super().handle_result(message, confirmation_token)
        elapsed = time.perf_counter() - start
        timings.setdefault(message, {})['total'] = elapsed
        return result

# Wrap AIService.ask to capture Ollama latency
from ai.ai_service import AIService
_original_ask = AIService.ask

def timed_ask(self, prompt: str) -> str:
    start = time.perf_counter()
    resp = _original_ask(self, prompt)
    elapsed = time.perf_counter() - start
    timings.setdefault(prompt, {})['ollama_latency'] = elapsed
    return resp

AIService.ask = timed_ask

# Global dict to store timings
Timings = {}

def record_timing(key, subkey, value):
    Timings.setdefault(key, {})[subkey] = value

timings = Timings

assistant = TimedAssistant()

prompts = [
    "Hey Oliver, what’s the weather today?",
    "Explain the difference between recursion and iteration.",
    "Write a Python function that merges two dictionaries.",
    "Plan a three‑step morning routine for me.",
    "Recall what we talked about in the last chat session."
]

results = []
for p in prompts:
    start = time.perf_counter()
    reply = assistant.handle(p)
    total = time.perf_counter() - start
    # reply may be from AIService, Ollama latency captured
    timings.setdefault(p, {})['total'] = total
    results.append((p, reply))

# Write report
report_path = Path(__file__).parent / "perf_baseline_report.txt"
with open(report_path, "w", encoding="utf-8") as f:
    f.write("Performance Baseline Report\n")
    f.write("===========================\n\n")
    for prompt in prompts:
        t = timings.get(prompt, {})
        total = t.get('total', None)
        ollama = t.get('ollama_latency', None)
        f.write(f"Prompt: {prompt}\n")
        f.write(f"  Total response time: {total:.3f}s\n" if total is not None else "  Total response time: N/A\n")
        f.write(f"  Ollama request latency: {ollama:.3f}s\n" if ollama is not None else "  Ollama request latency: N/A\n")
        f.write("\n")
    f.write("End of report\n")
print(f"Report written to {report_path}")

