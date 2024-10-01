import requests
import time
import random
import os
import socket
from threading import Lock
from flask import Flask, request, jsonify
from multiprocessing import Process

# Variáveis de ambiente
NODE_ID = os.getenv("NODE_ID", "0")
NODE_PORT = os.getenv("NODE_PORT", "5000")
NODE_URLS = os.getenv("NODE_URLS").split(",")  # URLs dos outros nós
SHARED_FILE = "./shared/resource.txt"  # Caminho do arquivo compartilhado

# Estados e estrutura para gerenciar a exclusão mútua
access_queue = []  # Fila local para gerenciar requisições de acesso
accessing_resource = False  # Indica se o nó está acessando o recurso
waiting_for_access = False  # Indica se o nó está esperando acesso
lock = Lock()  # Para proteger a fila e o status de acesso
last_granted_timestamp = None

app = Flask(__name__)  # Instancia o servidor Flask

def get_timestamp():
    """Retorna o timestamp atual formatado."""
    return time.strftime("%d-%m-%Y %H:%M:%S", time.localtime()) + f".{int(time.time() % 1 * 1000000):06d}"

def get_hostname():
    """Retorna o hostname da máquina."""
    return socket.gethostname()

def get_ip():
    """Retorna o IP da máquina."""
    return socket.gethostbyname(get_hostname())

def log_access(message):
    """Função para logar o acesso no arquivo compartilhado."""
    log_message = (
        f"device_id = {NODE_ID} | "
        f"hostname = {get_hostname()} | "
        f"ip = {get_ip()} | "
        f"timestamp = {get_timestamp()} | {message}\n"
    )
    
    with open(SHARED_FILE, "a") as f:
        f.write(log_message)
    
    print(log_message)

def send_request_to_all():
    """Envia requisição para todos os outros nós e espera respostas."""
    timestamp = get_timestamp()
    payload = {"node_id": NODE_ID, "timestamp": timestamp}
    responses = []

    # Envia requisição para todos os outros nós
    for node_url in NODE_URLS:
        try:
            response = requests.post(f"{node_url}/request_access", json=payload, timeout=15)
            response_data = response.json()
            log_access(f"Sent request to Node {NODE_ID}. Response: {response_data['status']}")
            responses.append(response_data)
        except requests.exceptions.RequestException as e:
            log_access(f"Failed to contact {node_url}: {e}")

    return responses

def request_access():
    global accessing_resource, waiting_for_access

    log_access("Requesting access to the resource...")

    while True:  # Loop para tentar acessar o recurso até conseguir
        responses = send_request_to_all()

        with lock:
            if all(r['status'] == 'ok' for r in responses):
                # Envia notificação de acesso aos outros nós
                notify_access_granted()

                accessing_resource = True
                log_access("Access granted to the resource.")
                use_resource()
                break  # Sai do loop após usar o recurso
            else:
                log_access("Waiting for access to the resource.")
                waiting_for_access = True
                time.sleep(5) 

def notify_access_granted():
    """Notifica os outros nós que este nó está acessando o recurso."""
    payload = {"node_id": NODE_ID}

    for node_url in NODE_URLS:
        try:
            response = requests.post(f"{node_url}/access_granted", json=payload)
            log_access(f"Sent access granted to Node {NODE_ID}. Response: {response.status_code}")
        except Exception as e:
            log_access(f"Failed to notify {node_url}: {e}")

@app.route("/access_granted", methods=["POST"])
def handle_access_granted():
    """Lida com notificações de acesso concedido de outros nós."""
    global accessing_resource

    data = request.json
    granted_node = data["node_id"]

    with lock:
        accessing_resource = True  # Flag de que outro nó está acessando o recurso

    log_access(f"Node {granted_node} has been granted access to the resource.")
    return jsonify({"status": "ok"})

def use_resource():
    """Simula o uso do recurso."""
    log_access("Using the resource...")
    time.sleep(random.randint(5, 7))  # Simula o tempo de uso do recurso
    release_resource()

def release_resource():
    """Libera o recurso compartilhado e concede acesso ao próximo nó na fila."""
    global accessing_resource, waiting_for_access

    accessing_resource = False
    waiting_for_access = False
    log_access("Released the resource.")

    time.sleep(1)

    with lock:
        if access_queue:
            next_node, _ = access_queue.pop(0)
            log_access(f"Granting access to Node {next_node}.")
            notify_next_node(next_node)  # Notifica o próximo nó na fila
        else:
            log_access("No nodes waiting in the queue.")


def notify_next_node(node_id):
    """Notifica o próximo nó na fila para acessar o recurso."""
    payload = {"node_id": NODE_ID}
    next_node_port = 5000 + int(node_id)

    try:
        url = f"http://node{node_id}:{next_node_port}/access_granted"  # Corrigir o endpoint
        response = requests.post(url, json=payload)
        log_access(f"Sent release notification to {url}. Response: {response.status_code}, {response.text}")
    except Exception as e:
        log_access(f"Failed to notify Node {node_id}: {e}")


@app.route("/request_access", methods=["POST"])
def handle_access_request():
    """Lida com requisições de acesso recebidas de outros nós."""
    global accessing_resource, waiting_for_access, last_granted_timestamp

    data = request.json
    requesting_node = data["node_id"]
    requesting_timestamp = data["timestamp"]

    with lock:
        if accessing_resource:
            log_access(f"Received request from Node {requesting_node}. Sending denied (resource in use).")
            return jsonify({"status": "denied"})
        elif waiting_for_access:
            access_queue.append((requesting_node, requesting_timestamp))
            log_access(f"Received request from Node {requesting_node}. Queued request.")
            return jsonify({"status": "queued"})
        # Compara o timestamp da requisição com o último timestamp concedido
        elif last_granted_timestamp is not None and requesting_timestamp < last_granted_timestamp:
            log_access(f"Received request from Node {requesting_node}. Sending denied (timestamp too old).")
            return jsonify({"status": "denied"})
        else:
            log_access(f"Received request from Node {requesting_node}. Sending OK.")
            last_granted_timestamp = requesting_timestamp  # Atualiza o último timestamp concedido
            return jsonify({"status": "ok"})


@app.route("/release", methods=["POST"])
def handle_release_request():
    """Lida com a liberação do recurso por outros nós."""
    global accessing_resource

    data = request.json
    releasing_node = data["node_id"]
    log_access(f"Received release notification from Node {releasing_node}")

    with lock:
        accessing_resource = False  # Libera o recurso

        if access_queue:
            # Remove o próximo nó da fila e concede acesso
            next_node, _ = access_queue.pop(0)
            log_access(f"Granting access to Node {next_node}.")
            notify_next_node(next_node)

    return jsonify({"status": "ok"})

def start_flask():
    """Função que inicia o servidor Flask."""
    app.run(host="0.0.0.0", port=int(NODE_PORT))

def request_access_loop():
    """Função que simula requisições aleatórias de acesso ao recurso."""
    while True:
        time.sleep(random.randint(7, 10))  # Atraso aleatório antes de solicitar acesso
        request_access()

if __name__ == "__main__":
    # Cria processos paralelos: um para o Flask e outro para o loop de requisição
    flask_process = Process(target=start_flask)
    access_process = Process(target=request_access_loop)

    # Inicia ambos os processos
    flask_process.start()
    access_process.start()

    # Aguarda ambos os processos finalizarem (em caso de interrupção)
    flask_process.join()
    access_process.join()
