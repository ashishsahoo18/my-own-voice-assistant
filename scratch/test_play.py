import pywhatkit
import time
import pyautogui

def test_play(song):
    print(f"Testing playonyt for: {song}")
    try:
        pywhatkit.playonyt(song)
        print("Successfully called pywhatkit.playonyt")
        time.sleep(3)
        # Send play shortcut (k or space) via pyautogui if needed
        pyautogui.press('k')
        print("Sent play shortcut ('k') via pyautogui")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    test_play("Ik Mulaqaat")
