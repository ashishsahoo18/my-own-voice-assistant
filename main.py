import speech_recognition as sr
import pyttsx3
import datetime
import webbrowser
import os
import wikipedia
import pywhatkit
import pyjokes
import requests

engine = pyttsx3.init()
recognizer = sr.Recognizer()

def speak(text):
    engine.say(text)
    engine.runAndWait()

def listen():
    with sr.Microphone() as source:
        print("Listening...")
        recognizer.pause_threshold = 1
        audio = recognizer.listen(source)

    try:
        print("Recognizing...")
        command = recognizer.recognize_google(audio, language="en-in")
        print("User:", command)
        return command.lower()
    except:
        return ""

def weather(city):
    api_key = "YOUR_OPENWEATHER_API_KEY"
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
    try:
        data = requests.get(url).json()
        if data["cod"] != "404":
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"]
            return f"The temperature in {city} is {temp} degree celsius with {desc}."
        else:
            return "City not found."
    except:
        return "Unable to fetch weather."


def convert_number(text):
    words = {
        "zero":"0","one":"1","two":"2","three":"3","four":"4",
        "five":"5","six":"6","seven":"7","eight":"8","nine":"9"
    }
    text = text.replace("plus", "+").replace(" ", "")
    for w, d in words.items():
        text = text.replace(w, d)
    return text


def run_assistant():
    speak("Hello! Pro Voice Assistant activated.")

    while True:
        query = listen()
        if query == "":
            continue

        # TIME
        if "time" in query:
            time = datetime.datetime.now().strftime("%I:%M %p")
            speak(f"The time is {time}")

        # DATE
        elif "date" in query:
            date = datetime.datetime.now().strftime("%d %B %Y")
            speak(f"Today's date is {date}")

        # WIKIPEDIA
        elif "wikipedia" in query:
            speak("Searching Wikipedia")
            topic = query.replace("wikipedia", "")
            try:
                info = wikipedia.summary(topic, 2)
                speak(info)
            except:
                speak("I could not find information.")

        # GOOGLE SEARCH
        elif "search" in query:
            speak("Searching on Google")
            pywhatkit.search(query.replace("search", ""))

        # PLAY SONG
        elif query.startswith("play"):
            song = query.replace("play", "")
            speak(f"Playing {song} on YouTube")
            pywhatkit.playonyt(song)

        # OPEN WEBSITES
        elif "open youtube" in query:
            speak("Opening YouTube")
            webbrowser.open("https://youtube.com")

        elif "open google" in query:
            speak("Opening Google")
            webbrowser.open("https://google.com")

        # ✅ WHATSAPP MESSAGE (YOUR CODE ADDED HERE)
        elif "send message" in query:
            speak("Tell me the number with country code")
            raw_number = listen()
            number = convert_number(raw_number)

            if not number.startswith("+"):
                speak("Invalid number format")
                continue

            speak("What is the message?")
            message = listen()
                                                                                                        
            try:
                now = datetime.datetime.now()
                pywhatkit.sendwhatmsg(
                    number,
                    message,
                    now.hour,
                    now.minute + 1
                )
                speak("Message will be sent in one minute")
            except Exception as e:
                speak("WhatsApp message failed")
                print(e)

        # OPEN APPS
        elif "open notepad" in query:
            speak("Opening Notepad")
            os.startfile("notepad.exe")

        elif "open calculator" in query:
            speak("Opening Calculator")
            os.startfile("calc.exe")

        # JOKE
        elif "joke" in query:
            speak(pyjokes.get_joke())

        # WEATHER
        elif "weather" in query:
            speak("Which city?")
            city = listen()
            speak(weather(city))

        # SYSTEM
        elif "shutdown" in query:
            speak("Shutting down system")
            os.system("shutdown /s /t 1")

        elif "restart" in query:
            speak("Restarting system")
            os.system("shutdown /r /t 1")

        # EXIT
        elif "exit" in query or "stop" in query:
            speak("Goodbye, shutting down assistant")
            break

        else:
            speak("Sorry, I didn't understand.")

run_assistant()
