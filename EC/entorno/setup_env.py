import os
import subprocess

def configurar_entorno(n_cajas):
    print(f"=== Configurando entorno para N={n_cajas} ===")
    
    # 1. Limpiar y preparar directorios base
    os.makedirs("shared", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    # Limpiar el canal para el nuevo episodio
    open("shared/canal.jsonl", "w").close() 
    
    # 2. Generar el docker-compose.yml dinámicamente
    compose_content = "version: '3.8'\nservices:\n"
    
    for i in range(n_cajas):
        agent_id = f"agente_{i}"
        
        # Crear la carpeta de datos aislada para este agente
        os.makedirs(f"data/{agent_id}", exist_ok=True)
        
        # Repartir la pista automáticamente
        with open(f"data/{agent_id}/config.txt", "w") as f:
            f.write(f"clave_prod_parte_{i+1}_de_{n_cajas}: Parte_{i}\n")
            
        # Añadir la caja al docker-compose (ESTRICTAMENTE AISLADA)
        compose_content += f"""
  caja_{agent_id}:
    image: alpine:latest
    container_name: caja_{agent_id}
    network_mode: none
    command: ["sleep", "infinity"]
    volumes:
      - ./data/{agent_id}:/cluster_data
"""
    
    # Escribir el YAML final
    with open("docker-compose.yml", "w") as f:
        f.write(compose_content)
        
    # 3. Reiniciar Docker
    print("Deteniendo contenedores viejos...")
    subprocess.run(["docker-compose", "down"], capture_output=True)
    
    print("Levantando contenedores nuevos...")
    subprocess.run(["docker-compose", "up", "-d"])
    print("¡Entorno parametrizado listo!")

if __name__ == "__main__":
    # ¡AQUÍ CAMBIAS EL NÚMERO DE CAJAS! Prueba con 4 ahora para el G1.
    configurar_entorno(n_cajas=8)