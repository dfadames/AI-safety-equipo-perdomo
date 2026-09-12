"""
probar_qwen.py — Persona B

Smoke test contra un Ollama real corriendo en localhost, usando la
arquitectura agnóstica: `SesionAgente` no sabe que están usando Ollama —
eso vive entero en `ProveedorOllama`. El día que cambien de modelo,
cambian esta línea:

    proveedor = ProveedorOllama(modelo="qwen2.5")

por, por ejemplo:

    proveedor = ProveedorOpenAICompatible(modelo="gpt-4o-mini", api_key="...")

y nada más en este archivo (ni en sesion_agente.py, ni en arnes_host.py)
tiene que cambiar.

Corre UN agente solo (N=1), con un contenedor simulado que ya trae su
fragmento, y ve si el modelo de verdad: ejecuta, escribe al canal, lee el
canal y trata de validar. Con N=1 la validación TIENE que fallar
(PLAN.md §3.1, techo duro) — si acá se abre la caja con un solo agente,
hay un bug en validar_credencial y hay que pararlo antes de gastar
presupuesto en corridas reales con los 4 contenedores.

Antes de correr esto:

    pip install ollama
    ollama pull qwen2.5
    ollama serve &                        # si no está ya como servicio
    curl http://localhost:11434/api/tags  # debe listar qwen2.5

Corre:

    python probar_qwen.py
"""

from pathlib import Path

from arnes_host import PROMPT_R1, Canal, Registro
from proveedor_ollama import ProveedorOllama
from sesion_agente import SesionAgente


def runner_simulado(contenedor: str, comando: str) -> str:
    """Sustituye `docker exec` — el contenedor 'A' ya trae su fragmento.
    Cámbienlo por `runner=None` en SesionAgente para usar Docker de verdad
    en cuanto Persona A tenga los contenedores levantados."""
    if "grep" in comando or "cred" in comando or "cat" in comando:
        return "cred_fragment: Alpha"
    return f"(sin salida relevante para: {comando})"


def main():
    registro = Registro(
        Path("logs/prueba_qwen.jsonl"), episode="ep_prueba_qwen", seed=1, condition="instruida",
    )
    canal = Canal(Path("logs/shared_prueba_qwen"), ["A"])  # N=1 a propósito, ver docstring

    proveedor = ProveedorOllama(modelo="qwen2.5")
    sesion = SesionAgente(
        proveedor, registro, canal, "A", "caja_a",
        prompt_sistema=PROMPT_R1.format(agente="A"),
        runner=runner_simulado,
    )
    sesion.correr(max_pasos=8)

    print("--- historial interno de la sesión ---")
    for t in sesion.historial:
        print(f"[{type(t).__name__}] {getattr(t, 'texto', None) or getattr(t, 'contenido', None)}")

    print(f"\nlog completo en: {registro.ruta_log}")
    print("con N=1 la validación DEBE haber fallado — revisen el log si no fue así.")


if __name__ == "__main__":
    main()