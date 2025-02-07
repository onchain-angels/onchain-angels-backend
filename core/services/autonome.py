import requests
from decouple import config


def ping_agent(prompt, action):
    try:
        url = config("AUTONOME_BASE_URL")
        headers = {
            "Authorization": f"Basic {config('AUTONOME_BASIC_AUTH_TOKEN')}",
            "accept": "application/json",
            "content-type": "application/json",
        }
        payload = {"text": prompt, "action": action}
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            raise Exception(response.text)

        text = response.json()[0]["text"]
        print("autonome response: {}".format(text))
        return text

    except Exception as e:
        print("Error sending message to autonome: {}".format(e))
        return None
