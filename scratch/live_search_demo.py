"""Live demonstration script for AYRA AI question search routing."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
from unittest.mock import patch
from ai.assistant import AyraAssistant

def run_live_demo():
    assistant = AyraAssistant()
    
    questions = [
        "What is Python?",
        "What is machine learning?",
        "Explain recursion.",
        "Why is the sky blue?",
        "What is an API?",
        "Who invented the computer?",
        "How does Django work?",
        "Difference between TCP and UDP",
    ]
    
    print("=" * 60)
    print("AYRA AI - LIVE QUESTION SEARCH ROUTING DEMO")
    print("=" * 60)
    
    for q in questions:
        print(f"\n[USER INPUT]: {q}")
        with patch("webbrowser.open") as mock_open:
            mock_open.return_value = True
            response = assistant.handle(q)
            print(f"[AYRA ACTION]: {response}")
            if mock_open.called:
                print(f"[BROWSER URL]: {mock_open.call_args[0][0]}")

if __name__ == "__main__":
    run_live_demo()
