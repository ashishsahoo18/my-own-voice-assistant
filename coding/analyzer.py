"""Static code analyzer, AST inspector, and error traceback diagnostician for OLIVER 2.0."""

from __future__ import annotations

import ast
import re
from typing import Any, Optional

from coding.languages import LanguageDetector
from coding.models import DiagnosticResult


class CodeAnalyzer:
    """Performs static code inspection, AST verification, and traceback diagnosis."""

    # Traceback and compiler error pattern regexes
    PYTHON_TB_PATTERN = re.compile(
        r"File\s+[\"'](?P<file>[^\"']+)[\"'],\s+line\s+(?P<line>\d+)(?:,\s+in\s+(?P<scope>\S+))?"
    )
    PYTHON_EXC_PATTERN = re.compile(
        r"^(?P<type>[a-zA-Z0-9_\.]+(?:Error|Exception|Warning|Interrupt|Exit)):\s*(?P<msg>.*)$",
        re.MULTILINE,
    )

    CPP_ERROR_PATTERN = re.compile(
        r"(?P<file>[a-zA-Z0-9_\-\.\/\\]+):(?P<line>\d+):(?:(?P<col>\d+):)?\s+(?P<severity>error|fatal error|warning):\s+(?P<msg>.+)"
    )
    MSVC_ERROR_PATTERN = re.compile(
        r"(?P<file>[a-zA-Z0-9_\-\.\/\\]+)\((?P<line>\d+)\):\s+(?P<severity>error|fatal error|warning)\s+(?P<code>C\d+):\s+(?P<msg>.+)"
    )

    NODE_ERROR_PATTERN = re.compile(
        r"^(?P<type>[A-Za-z]+Error):\s*(?P<msg>.+?)(?:\n\s+at\s+.*?\((?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+)\))?",
        re.MULTILINE,
    )

    SQL_ERROR_PATTERN = re.compile(
        r"(?i)(?:syntax\s+error\s+at\s+or\s+near\s+['\"](?P<token>[^'\"]+)['\"]|column\s+['\"](?P<col>[^'\"]+)['\"]\s+does\s+not\s+exist|table\s+['\"](?P<table>[^'\"]+)['\"]\s+already\s+exists)"
    )

    @classmethod
    def check_python_syntax(cls, code: str) -> Optional[tuple[int, int, str, str]]:
        """Verify Python code syntax via standard library AST.
        
        Returns:
            None if valid, or (lineno, col_offset, error_message, problematic_line).
        """
        try:
            ast.parse(code)
            return None
        except SyntaxError as err:
            lineno = err.lineno or 1
            offset = err.offset or 0
            msg = err.msg or "SyntaxError"
            text = err.text or ""
            return (lineno, offset, msg, text.strip())

    @classmethod
    def diagnose_traceback(cls, error_log: str, code: Optional[str] = None, language_hint: Optional[str] = None) -> DiagnosticResult:
        """Parse stack trace or compiler error and extract structured diagnostics."""
        log = (error_log or "").strip()
        lang = LanguageDetector.normalize_language_name(language_hint or "")
        if lang == "Unknown":
            lang = LanguageDetector.detect(code or "", explicit_hint=language_hint)

        py_tb_matches = list(cls.PYTHON_TB_PATTERN.finditer(log))

        # 1. JavaScript / Node.js
        node_match = cls.NODE_ERROR_PATTERN.search(log)
        js_loc_match = re.search(r"^\s*at\s+.*?\((?P<file>[^:]+):(?P<line>\d+)(?::\d+)?\)", log, re.MULTILINE)
        if (node_match or js_loc_match or "    at " in log or lang in ("JavaScript", "TypeScript")) and not py_tb_matches:
            err_type = node_match.group("type") if node_match else "JavaScript Error"
            msg = node_match.group("msg").strip() if node_match else log.splitlines()[0]
            loc = None
            if js_loc_match:
                loc = f"{js_loc_match.group('file')}:{js_loc_match.group('line')}"
            elif node_match and node_match.group("file") and node_match.group("line"):
                loc = f"{node_match.group('file')}:{node_match.group('line')}"
            return DiagnosticResult(
                language="JavaScript",
                error_type=err_type,
                location=loc,
                root_cause=f"{err_type}: {msg}",
                explanation=f"JavaScript runtime error: '{msg}'.",
                suggested_fix="Verify null/undefined checks, object properties, or asynchronous awaits.",
            )

        # 2. Python Stack Trace / Syntax Error
        py_exc_match = cls.PYTHON_EXC_PATTERN.search(log)
        if py_exc_match or py_tb_matches or lang == "Python":
            if py_exc_match:
                exc_type = py_exc_match.group("type")
                exc_msg = py_exc_match.group("msg").strip()
                loc = None
                if py_tb_matches:
                    last_tb = py_tb_matches[-1]
                    loc = f"{last_tb.group('file')}:{last_tb.group('line')}"
                return cls._create_python_diagnosis(exc_type, exc_msg, loc, code)

        # 3. C++ Compiler Error (GCC/Clang or MSVC)
        cpp_match = cls.CPP_ERROR_PATTERN.search(log)
        msvc_match = cls.MSVC_ERROR_PATTERN.search(log)
        if cpp_match or msvc_match or lang in ("C++", "C"):
            m = cpp_match or msvc_match
            if m:
                fl = m.group("file")
                ln = m.group("line")
                msg = m.group("msg").strip()
                sev = m.group("severity")
                code_str = m.groupdict().get("code", "")
                err_type = f"C++ Compiler {sev.capitalize()} ({code_str})" if code_str else f"C++ Compiler {sev.capitalize()}"
                return DiagnosticResult(
                    language="C++",
                    error_type=err_type,
                    location=f"{fl}:{ln}",
                    root_cause=f"{sev.capitalize()}: {msg}",
                    explanation=f"The C++ compiler encountered a problem at line {ln}: '{msg}'.",
                    suggested_fix=f"Review declarations, header inclusions (#include), and types around line {ln}.",
                )

        # 4. SQL Error
        sql_match = cls.SQL_ERROR_PATTERN.search(log)
        if sql_match or lang == "SQL":
            if sql_match:
                token = sql_match.groupdict().get("token")
                col = sql_match.groupdict().get("col")
                tbl = sql_match.groupdict().get("table")
                cause = f"Syntax near '{token}'" if token else f"Unknown column '{col}'" if col else f"Table '{tbl}' exists"
                return DiagnosticResult(
                    language="SQL",
                    error_type="SQL Query Error",
                    root_cause=cause,
                    explanation=f"Database query execution failure: {log.splitlines()[0] if log else cause}",
                    suggested_fix="Check table and column identifiers, syntax keywords, and quoting rules.",
                )

        # Fallback / Generic
        first_line = log.splitlines()[0] if log else "Unknown error"
        return DiagnosticResult(
            language=lang if lang != "Unknown" else "General",
            error_type="Diagnostic Report",
            root_cause=first_line,
            explanation=f"Error log inspection: {log[:300]}",
            suggested_fix="Inspect relevant function declarations and parameters.",
        )

    @classmethod
    def _create_python_diagnosis(cls, exc_type: str, exc_msg: str, loc: Optional[str], code: Optional[str]) -> DiagnosticResult:
        """Create structured root cause and fixes for Python exceptions."""
        expl = ""
        fix = ""
        if exc_type == "IndentationError":
            expl = "Python requires consistent indentation (usually 4 spaces). Mixed tabs and spaces or missing indentation after a colon causes this error."
            fix = "Ensure code blocks after 'def', 'if', 'for', 'class', etc., are indented with 4 spaces."
        elif exc_type == "SyntaxError":
            expl = f"Invalid Python syntax encountered: {exc_msg}."
            fix = "Check for missing colons (:), unclosed parentheses, quotes, or invalid operators."
        elif exc_type == "KeyError":
            expl = f"Attempted to access dictionary key {exc_msg} that does not exist."
            fix = f"Use dict.get({exc_msg}) with a default value, or check 'if {exc_msg} in my_dict:' before accessing."
        elif exc_type == "AttributeError":
            expl = f"The object does not have the specified attribute or method: {exc_msg}."
            fix = "Verify the object type and spelling of the attribute. Check for 'None' return values."
        elif exc_type == "TypeError":
            expl = f"Type mismatch or wrong arguments passed: {exc_msg}."
            fix = "Inspect argument counts, expected types, and verify variables are not None."
        elif exc_type == "IndexError":
            expl = "Attempted to access a sequence index that is out of range."
            fix = "Check len(sequence) before indexing, or use slice operations."
        else:
            expl = f"Python raised {exc_type}: {exc_msg}."
            fix = "Review variable scopes, parameter types, and handle potential exceptions with try/except."

        return DiagnosticResult(
            language="Python",
            error_type=exc_type,
            location=loc,
            root_cause=f"{exc_type}: {exc_msg}",
            explanation=expl,
            suggested_fix=fix,
        )

    @classmethod
    def estimate_complexity(cls, code: str, language: str = "Python") -> tuple[str, str, str]:
        """Estimate Big-O time and space complexity with reasoning and caveats.
        
        Returns:
            (time_complexity, space_complexity, reasoning)
        """
        lines = code.splitlines()
        loop_depth = 0
        max_loop_depth = 0
        has_recursion = False
        has_large_alloc = False

        func_names = set(re.findall(r"\bdef\s+([a-zA-Z0-9_]+)\b", code))

        for line in lines:
            stripped = line.strip()
            # Count nested loops (heuristic)
            if re.match(r"^(?:for|while)\b", stripped):
                loop_depth += 1
                if loop_depth > max_loop_depth:
                    max_loop_depth = loop_depth
            elif stripped.endswith(":") and not re.match(r"^(?:for|while|if|elif|else|try|except|finally)\b", stripped):
                # block exit or new scope
                pass

            # Detect self-call (recursion)
            for fn in func_names:
                if re.search(rf"\b{fn}\s*\(", stripped) and not stripped.startswith(f"def {fn}"):
                    has_recursion = True

            # Detect data structure allocation
            if any(k in stripped for k in ("[]", "{}", "list(", "dict(", "set(", "vector<", "new ")):
                has_large_alloc = True

        # Time complexity deduction
        if has_recursion:
            time_comp = "O(2^N) or O(N!) [Recursive without memoization]" if max_loop_depth == 0 else "O(N * 2^N) [Recursive with loops]"
            reasoning = "Contains recursive function calls. Without memoization or divide-and-conquer, recursive branching dominates runtime."
        elif max_loop_depth >= 3:
            time_comp = f"O(N^{max_loop_depth}) [Polynomial]"
            reasoning = f"Detected {max_loop_depth} levels of nested iteration."
        elif max_loop_depth == 2:
            time_comp = "O(N^2) [Quadratic]"
            reasoning = "Detected nested loop iteration over input elements."
        elif max_loop_depth == 1:
            time_comp = "O(N) [Linear]"
            reasoning = "Single-pass sequential iteration over inputs."
        else:
            time_comp = "O(1) [Constant]"
            reasoning = "Direct operations and fixed-time statements without unbounded loops or recursion."

        # Space complexity deduction
        if has_recursion:
            space_comp = "O(N) [Call stack frames]"
        elif has_large_alloc and max_loop_depth >= 1:
            space_comp = "O(N) [Auxiliary storage proportional to input size]"
        elif has_large_alloc:
            space_comp = "O(1) or O(K) [Fixed buffer/collection]"
        else:
            space_comp = "O(1) [In-place, constant auxiliary memory]"

        return time_comp, space_comp, reasoning
