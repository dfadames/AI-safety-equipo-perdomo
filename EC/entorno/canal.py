import os
import json
import subprocess

# Diccionario dinámico: si llega un agente nuevo, su puntero empieza en 0
pointers = {} 

def escribir_canal(agent_id, msg, event_id_del_write):
    msg_data = {
        "event_id": event_id_del_write, 
        "agent_id": agent_id,
        "content": msg
    }
    with open("shared/canal.jsonl", "a") as f:
        f.write(json.dumps(msg_data) + "\n")
    return "Mensaje enviado al canal de coordinación."

def leer_canal(agent_id):
    canal_path = "shared/canal.jsonl"
    if not os.path.exists(canal_path):
        return []
        
    with open(canal_path, "r") as f:
        lines = f.readlines()
        
    # Inicializar el puntero si este agente consulta por primera vez
    if agent_id not in pointers:
        pointers[agent_id] = 0
        
    new_lines = lines[pointers[agent_id]:]
    pointers[agent_id] = len(lines) 
    
    mensajes_nuevos = []
    for line in new_lines:
        msg = json.loads(line)
        if msg["agent_id"] != agent_id:
            mensajes_nuevos.append(msg)
            
    return mensajes_nuevos

def ejecutar_en_contenedor(agent_id, comando):
    container_name = f"caja_{agent_id}"
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "sh", "-c", comando],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"Error: {result.stderr.strip()}"
    except Exception as e:
        return f"Error de ejecución: {str(e)}"