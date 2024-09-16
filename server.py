from flask import Flask, request, jsonify
import os
import time
from queue import Queue
from threading import Lock, Timer
from datetime import datetime

app = Flask(__name__)

# Estado do recurso e sincronização
resource_in_use = False
queue = Queue()
lock = Lock()  # Para sincronizar o acesso ao recurso
queue_list = []  # Lista para armazenar os nós na fila
MAX_USAGE_TIME = 10  # Tempo máximo de uso do recurso em segundos

# Nome do arquivo compartilhado
SHARED_FILE = "./shared/resource.txt"


def format_timestamp(timestamp):
    """Formata o timestamp no formato hh:mm:ss:ms"""
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%H:%M:%S:%f")[
        :-3
    ]  # Retira os microsegundos e fica com milissegundos


def release_after_timeout():
    """Função para liberar o recurso automaticamente após o tempo limite"""
    with lock:
        if queue.empty():
            next_node, next_timestamp = queue.get()
            queue_list.remove(next_node)
            log_access(
                f"Next access granted to Node {next_node} at {format_timestamp(next_timestamp)}"
            )
        else:
            global resource_in_use
            resource_in_use = False
            log_access("Resource released after timeout.")


# Rota para acessar o arquivo
@app.route("/access", methods=["POST"])
def access_resource():
    global resource_in_use
    data = request.json
    node_id = data["node_id"]
    timestamp = data["timestamp"]

    log_access(f"Node {node_id} is requesting access at {format_timestamp(timestamp)}")

    with lock:
        # Se o recurso não está em uso, concede acesso
        if not resource_in_use:
            resource_in_use = True
            log_access(
                f"Access granted to Node {node_id} at {format_timestamp(timestamp)}"
            )

            # Configura um temporizador para liberar o recurso após o tempo máximo de uso
            Timer(MAX_USAGE_TIME, release_after_timeout).start()
            return jsonify({"status": "granted"}), 200
        else:
            # Se o recurso está em uso, coloca na fila
            queue.put((node_id, timestamp))
            queue_list.append(node_id)  # Adiciona o nó na lista de fila
            log_access(f"Node {node_id} queued at {format_timestamp(timestamp)}")
            log_access(f"Current queue: {queue_list}")  # Exibe a fila atualizada
            return jsonify({"status": "queued"}), 202


# Rota para liberar o recurso manualmente
@app.route("/release", methods=["POST"])
def release_resource():
    with lock:
        # Libera o recurso e dá permissão ao próximo da fila (se houver)
        if not queue.empty():
            next_node, next_timestamp = queue.get()
            queue_list.remove(next_node)
            log_access(
                f"Next access granted to Node {next_node} at {format_timestamp(next_timestamp)}"
            )
            log_access(f"Current queue after release: {queue_list}")
        else:
            global resource_in_use
            resource_in_use = False
            log_access("Resource manually released, no more nodes in queue.")

    return jsonify({"status": "released"}), 200


def log_access(message):
    """Função para logar o acesso no arquivo de texto"""
    with open(SHARED_FILE, "a") as f:
        f.write(message + "\n")
    print(message)  # Também loga no console para depuração


if __name__ == "__main__":
    if not os.path.exists("./shared"):
        os.makedirs("./shared")
    app.run(host="0.0.0.0", port=5000)
