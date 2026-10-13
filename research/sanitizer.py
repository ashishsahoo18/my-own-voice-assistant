"""HTML content extraction, text sanitization, and prompt-injection defense."""

from __future__ import annotations

import re
from bs4 import BeautifulSoup


# Common prompt-injection triggers and control-override patterns
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|in)\s+(developer|unrestricted|god|dan|jailbreak)\s+mode?", re.IGNORECASE),
    re.compile(r"(system\s+override|system\s+prompt|developer\s+mode|dan\s+mode):", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(rules|safety|guidelines|policies)", re.IGNORECASE),
    re.compile(r"(execute|run)\s+(the\s+following\s+)?(command|shell|script|tool):", re.IGNORECASE),
    re.compile(r"bypass\s+(all\s+)?(security|policy|confirmations?)", re.IGNORECASE),
]


class ContentSanitizer:
    """Sanitizes raw HTML and neutralizes prompt-injection payloads from untrusted web sources."""

    def __init__(self, max_chars: int = 5000) -> None:
        self.max_chars = max_chars

    def extract_text_from_html(self, raw_html: str) -> str:
        """Extract clean text content from raw HTML, discarding scripts, styles, and navigation."""
        if not raw_html or not raw_html.strip():
            return ""

        soup = BeautifulSoup(raw_html, "html.parser")

        # Strip active scripts, styles, forms, and boilerplate navigation
        for tag in soup(["script", "style", "noscript", "iframe", "svg", "form", "nav", "header", "footer", "aside"]):
            tag.decompose()

        # Extract text elements
        text = soup.get_text(separator="\n", strip=True)

        # Collapse excessive newlines and spaces
        cleaned = re.sub(r"\n\s*\n+", "\n\n", text).strip()
        return cleaned[: self.max_chars]

    def neutralize_prompt_injections(self, text: str) -> tuple[str, list[str]]:
        """Identify and defuse prompt injection attempts in untrusted content.
        
        Returns (neutralized_text, list_of_detected_patterns).
        """
        detected: list[str] = []
        neutralized = text

        for pattern in INJECTION_PATTERNS:
            matches = pattern.findall(neutralized)
            if matches:
                detected.append(pattern.pattern)
                # Defuse by prefixing and neutralizing the command structure
                neutralized = pattern.sub(r"[FLAGGED_UNTRUSTED_INSTRUCTION: \g<0>]", neutralized)

        return neutralized, detected

    def format_untrusted_evidence_block(self, title: str, url: str, content: str) -> str:
        """Wrap untrusted web content in secure XML delimiters to isolate it from LLM instructions."""
        clean_text = self.extract_text_from_html(content) if ("<html" in content.lower() or "<div" in content.lower()) else content
        safe_text, injections = self.neutralize_prompt_injections(clean_text[: self.max_chars])

        warning_tag = f' injection_flagged="{len(injections)}"' if injections else ""
        return (
            f'<untrusted_web_evidence title="{title}" url="{url}"{warning_tag}>\n'
            f"{safe_text}\n"
            f"</untrusted_web_evidence>"
        )
