from ai.assistant import AyraAssistant
from ai.gemini_client import client as gemini_client
from pathlib import Path

assistant = AyraAssistant()
# Simulate Gemini quota exhausted
gemini_client.quota_exhausted = True

print('--- Gemini UNAVAILABLE (simulated) ---')
print('Q1:', assistant.handle('What is DFS and BFS algorithm?'))
print('Q2:', assistant.handle('What is Python?'))

# Local commands
print('\n--- Local commands ---')
print('C1:', assistant.handle('Create a folder named Ashish on my Desktop'))
# Check folder existence
print('Exists:', (Path.home() / 'Desktop' / 'Ashish').exists())
print('C2:', assistant.handle('Create a file named Ayra.py inside Ashish'))
print('Exists file:', (Path.home() / 'Desktop' / 'Ashish' / 'Ayra.py').exists())
print('C3:', assistant.handle('Create a folder named Ashish on my Desktop and create a file named Ayra.py inside it'))
print('Exists file2:', (Path.home() / 'Desktop' / 'Ashish' / 'Ayra.py').exists())
