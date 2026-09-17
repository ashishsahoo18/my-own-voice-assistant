from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def test_selenium():
    try:
        print("Testing Chrome...")
        driver = webdriver.Chrome()
        driver.get("https://www.youtube.com")
        print("Chrome opened successfully!")
        driver.quit()
        return True
    except Exception as e:
        print(f"Chrome failed: {e}")

    try:
        print("Testing Edge...")
        driver = webdriver.Edge()
        driver.get("https://www.youtube.com")
        print("Edge opened successfully!")
        driver.quit()
        return True
    except Exception as e:
        print(f"Edge failed: {e}")

    return False

if __name__ == "__main__":
    test_selenium()
