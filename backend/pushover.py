# pushover.py

import requests

PUSHOVER_USER_KEY = "uig46b9ik8eqy5fefzbzt8ttri1k6z"
PUSHOVER_APP_TOKEN = "admg7efo3yqp4pwmbi6v92opmpnzov"

def send_pushover_notification(message: str, title: str = "Tau Core System"):
    payload = {
        "token": PUSHOVER_APP_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
        "title": title,
        "priority": 1,
    }
    try:
        response = requests.post("https://api.pushover.net/1/messages.json", data=payload)
        if response.status_code == 200:
            print("✅ Pushover notification sent")
        else:
            print(f"❌ Failed to send Pushover notification: {response.text}")
    except Exception as e:
        print(f"Error sending pushover: {str(e)}")
