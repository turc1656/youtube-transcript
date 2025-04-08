import os
import requests
from dotenv import load_dotenv


def deploy():
    try:
        WEBHOOK_URL = os.getenv('DEPLOYMENT_WEBHOOK_URL')
        SECRET_TOKEN = os.getenv('DEPLOYMENT_SECRET_TOKEN')

        print("Triggering deployment...")

        response = requests.post(f"{WEBHOOK_URL}?token={SECRET_TOKEN}")

        if response.status_code == 200:
            print("✅ Deployment triggered successfully!")
        else:
            print(f"❌ Failed to trigger deployment. Status code: {response.status_code}")
            print("Response:", response.text)
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    load_dotenv()  # Load environment variables from .env file
    deploy()
