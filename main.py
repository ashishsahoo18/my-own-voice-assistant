# ================= IMPORTS =================
import pywhatkit
import time
import cv2
import pyttsx3
import speech_recognition as sr
from dotenv import load_dotenv
import os
import subprocess
import webbrowser
from openai import OpenAI

load_dotenv()

print(os.getenv("OPENAI_API_KEY"))  # test
# ================= OPENAI =================
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# ================= VOICE SETUP =================
engine = pyttsx3.init()
voices = engine.getProperty('voices')
engine.setProperty('voice', voices[1].id)
engine.setProperty('rate', 145)

def speak(text):

    print("Ayra:", text)

    engine.say(text)

    for i in range(10):
        show_face(True)
        time.sleep(0.1)

    engine.runAndWait()

    show_face(False)

# ================= LISTEN =================
def listen():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source)
        audio = r.listen(source)
    try:
        return r.recognize_google(audio).lower()
    except:
        return ""

# ================= AI =================
def ai_reply(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except:
        return "I am offline. Please try basic commands."

# ================= OFFLINE FALLBACK =================
offline_answers = {
    "what is python": "Python is a programming language used for backend, AI and automation.",
    "what is ai": "AI means machines that can think and learn like humans.",
    "what is array": "Array stores multiple values in one variable."
}

# ================= SYSTEM FUNCTIONS =================
def open_notepad():
    subprocess.Popen(["notepad.exe"])

def create_folder(name):
    path = os.path.join(os.getcwd(), name)
    if not os.path.exists(path):
        os.mkdir(path)
        return "Folder created"
    return "Folder already exists"

def delete_folder(name):
    path = os.path.join(os.getcwd(), name)
    if os.path.exists(path):
        os.rmdir(path)
        return "Folder deleted"
    return "Folder not found"

def create_file(name):
    if not name.endswith(".txt"):
        name += ".txt"
    open(name, "w").close()
    subprocess.Popen(["notepad.exe", name])
    return "File created and opened"

def delete_file(name):
    if not name.endswith(".txt"):
        name += ".txt"
    if os.path.exists(name):
        os.remove(name)
        return "File deleted"
    return "File not found"

# ================= CALCULATOR =================
def calculate(cmd):
    try:
        cmd = cmd.replace("plus", "+").replace("minus", "-")
        cmd = cmd.replace("into", "*").replace("multiply", "*")
        cmd = cmd.replace("divide", "/")
        result = eval(cmd)
        return f"Result is {result}"
    except:
        return "Calculation error"

# ================= CHROME SEARCH =================
def chrome_search(query):
    webbrowser.open(f"https://www.google.com/search?q={query}")

# ================= YOUTUBE =================
def play_youtube(song):
    pywhatkit.playonyt(song)

# ================= WHATSAPP =================
def send_whatsapp(number, message):
    number = "+91" + number
    pywhatkit.sendwhatmsg_instantly(
        phone_no=number,
        message=message,
        wait_time=10,
        tab_close=True
    )

# ================= FACE =================
face = cv2.imread("face.jpg")
face = cv2.resize(face, (400, 400))

def show_face(talking=False):
    img = face.copy()
    if talking:
        cv2.ellipse(img, (200, 280), (40, 20), 0, 0, 180, (0,0,0), 3)
    else:
        cv2.line(img, (160, 280), (240, 280), (0,0,0), 3)
    cv2.imshow("Ayra", img)
    cv2.waitKey(1)

# ================= MAIN =================
speak("Ayra activated. Say Ayra to start.")

while True:
    command = listen()

    if "ayra" not in command:
        continue

    speak("Yes Ashu")
    user_cmd = listen()
    print("Command:", user_cmd)
    show_face(True)

    if "exit" in user_cmd:
        speak("Goodbye Ashu")
        break

    elif "open notepad" in user_cmd:
        open_notepad()
        speak("Opening notepad")

    elif "play song" in user_cmd:
        speak("Which song?")
        song = listen()
        play_youtube(song)
        speak("Playing song")

    elif "send whatsapp message" in user_cmd:
        speak("Tell number")
        number = listen().replace(" ", "")
        speak("Tell message")
        message = listen()
        send_whatsapp(number, message)
        speak("Message sent")

    elif "create folder" in user_cmd:
        speak("Folder name")
        name = listen()
        speak(create_folder(name))

    elif "delete folder" in user_cmd:
        speak("Folder name")
        name = listen()
        speak(delete_folder(name))

    elif "create file" in user_cmd:
        speak("File name")
        name = listen()
        speak(create_file(name))

    elif "delete file" in user_cmd:
        speak("File name")
        name = listen()
        speak(delete_file(name))

    elif "calculate" in user_cmd:
        speak(calculate(user_cmd))

    elif "search" in user_cmd:
        query = user_cmd.replace("search", "")
        chrome_search(query)
        speak("Searching")

    elif user_cmd in offline_answers:
        speak(offline_answers[user_cmd])

    else:
        speak(ai_reply(user_cmd))

cv2.destroyAllWindows()
