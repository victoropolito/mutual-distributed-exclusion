import requests
import time
import random
import os

NODE_ID = os.getenv("NODE_ID", "0")

SERVER_URL = "http://server:5000"


def get_timestamp():
    return time.time()


def request_access():
    timestamp = get_timestamp()
    payload = {"node_id": NODE_ID, "timestamp": timestamp}
    response = requests.post(f"{SERVER_URL}/access", json=payload)
    return response.json()


def release_resource():
    response = requests.post(f"{SERVER_URL}/release")
    return response.json()


if __name__ == "__main__":
    while True:
        # Aguarda um tempo aleatório para solicitar o acesso ao recurso
        time.sleep(random.randint(8, 12))

        print(f"Node {NODE_ID} requesting access to resource...")
        access_response = request_access()

        if access_response["status"] == "granted":
            print(f"Node {NODE_ID} accessed the resource.")
            time.sleep(random.randint(1, 3))  # Simula o uso do recurso
            release_response = release_resource()
            print(f"Node {NODE_ID} released the resource.")
        else:
            print(f"Node {NODE_ID} queued for resource access.")
