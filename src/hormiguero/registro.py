"""
El registro de eventos — lo que después se convierte en el mapa de procedencia.

Un objeto por episodio, un archivo por episodio. El `step` es un contador
causal global del episodio, no un timestamp de reloj: con timestamps no se
puede ordenar de forma fiable ni imponer el tope de pasos.
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Optional


class Registro:
    def __init__(self, ruta_log, episode: str, seed: int, condition: str):
        self.ruta_log = Path(ruta_log)
        self.episode = episode
        self.seed = seed
        self.condition = condition
        self._lock = threading.Lock()
        self._step = 0
        self._tokens = 0
        self._pasos_por_agente: dict[str, int] = {}
        self.ruta_log.parent.mkdir(parents=True, exist_ok=True)
        self.ruta_log.write_text("", encoding="utf-8")   # un episodio, un archivo

    # -- presupuesto -------------------------------------------------------

    def sumar_tokens(self, n: int) -> int:
        with self._lock:
            self._tokens += n
            return self._tokens

    @property
    def tokens(self) -> int:
        return self._tokens

    def pasos_de(self, agent_id: str) -> int:
        """Cuántos EVENTOS escribió este agente. No es lo mismo que turnos del
        modelo: un `leer_canal` que absorbe 7 mensajes escribe 7 eventos en un
        solo turno. El tope de presupuesto va sobre turnos (ver SesionAgente),
        no sobre esto."""
        return self._pasos_por_agente.get(agent_id, 0)

    @property
    def step_global(self) -> int:
        return self._step

    # -- escritura ---------------------------------------------------------

    def escribir(
        self,
        *,
        agent_id: str,
        source_container: str,
        type_: str,
        content,
        ancestors: list[str],
        cited_by_agent: Optional[list[str]] = None,
        exact_parts_used: Optional[list[str]] = None,
        success: Optional[bool] = None,
        monitor_agent_score: Optional[int] = None,
    ) -> str:
        evt_id = f"evt_{agent_id}_{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._step += 1
            self._pasos_por_agente[agent_id] = self._pasos_por_agente.get(agent_id, 0) + 1
            entry = {
                "event_id": evt_id,
                "episode": self.episode,
                "seed": self.seed,
                "condition": self.condition,
                "step": self._step,
                "paso_del_agente": self._pasos_por_agente[agent_id],
                "agent_id": agent_id,
                "source_container": source_container,
                "type": type_,
                "content": content,
                "ancestors": list(ancestors),
                "cited_by_agent": cited_by_agent,
                "exact_parts_used": exact_parts_used,
                "success": success,          # al primer nivel, no dentro de content
                "monitor_agent_score": monitor_agent_score,
                "tokens_acumulados": self._tokens,
            }
            with open(self.ruta_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return evt_id
