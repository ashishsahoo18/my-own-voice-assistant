import sys
print(f"Python executable: {sys.executable}")

try:
    import customtkinter
    print("customtkinter: OK")
except Exception as e:
    print(f"customtkinter ERROR: {e}")

try:
    import selenium
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    print("selenium: OK")
except Exception as e:
    print(f"selenium ERROR: {e}")

try:
    import pywhatkit
    print("pywhatkit: OK")
except Exception as e:
    print(f"pywhatkit ERROR: {e}")

try:
    import ui.app
    print("ui.app import: OK")
except Exception as e:
    print(f"ui.app ERROR: {e}")

try:
    import commands.youtube
    print("commands.youtube import: OK")
except Exception as e:
    print(f"commands.youtube ERROR: {e}")
