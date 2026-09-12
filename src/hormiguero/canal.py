"""
El canal compartido.

Vive SOLO en el host. Los contenedores no lo tienen montado: si lo tuvieran,
un agente podría leerlo con `ejecutar("cat ...")` sin pasar por la herramienta,
la transferencia no quedaría registrada, y el mapa saldría mal sin avisar.
Ver CANAL.md.

Un archivo por agente, no uno compartido: así cada archivo tiene exactamente
un escritor y la corrupción por escritura concurrente deja de ser posible, no
solo improbable.

Los tres parámetros del barrido del domingo se aplican acá, como política.
No hacen falta servicios ni infraestructura: son tres `if`.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .config import Config


class Canal:
    def __init__(self, carpeta, cfg: Config):
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.cfg = cfg
        self._agentes = list(cfg.agentes)
        for a in self._agentes:
            self._archivo(a).write_text("", encoding="utf-8")
        self._locks = {a: threading.Lock() for a in self._agentes}
        self._offsets: dict[tuple[str, str], int] = {
            (lector, fuente): 0 for lector in self._agentes for fuente in self._agentes
        }
        self._enviados: dict[str, int] = {a: 0 for a in self._agentes}

    def _archivo(self, agent_id: str) -> Path:
        return self.carpeta / f"canal_{agent_id}.jsonl"

    # -- escritura ---------------------------------------------------------

    def publicar(self, agent_id: str, event_id: str, mensaje: str,
                 step: int, para: str | None = None) -> str:
        """Aplica los topes de ancho de banda. Devuelve el texto de resultado
        que ve el agente — si lo truncaron o lo rechazaron, se entera."""
        aviso = ""

        if self._enviados[agent_id] >= self.cfg.canal_max_mensajes:
            return (f"No enviado: alcanzaste el tope de {self.cfg.canal_max_mensajes} "
                    "mensajes para este episodio.")

        if len(mensaje) > self.cfg.canal_max_chars:
            mensaje = mensaje[: self.cfg.canal_max_chars]
            aviso = f" (truncado a {self.cfg.canal_max_chars} caracteres)"

        linea = json.dumps(
            {"event_id": event_id, "agent_id": agent_id, "msg": mensaje,
             "step": step, "para": para},
            ensure_ascii=False,
        )
        with self._locks[agent_id]:
            with open(self._archivo(agent_id), "a", encoding="utf-8") as f:
                f.write(linea + "\n")
            self._enviados[agent_id] += 1
        return "Mensaje enviado." + aviso

    # -- lectura -----------------------------------------------------------

    def leer_nuevos(self, lector: str, step_actual: int) -> list[tuple[str, str, str]]:
        """Solo lo nuevo desde la última lectura DE ESTE lector.
        Devuelve [(remitente, event_id_del_write, mensaje), ...].

        Aplica persistencia y direccionamiento."""
        nuevos: list[tuple[str, str, str]] = []
        for fuente in self._agentes:
            if fuente == lector:
                continue
            ruta = self._archivo(fuente)
            if not ruta.exists():
                continue
            lineas = ruta.read_text(encoding="utf-8").splitlines()
            desde = self._offsets[(lector, fuente)]
            for linea in lineas[desde:]:
                if not linea.strip():
                    continue
                d = json.loads(linea)

                # persistencia: en modo efímero, los mensajes viejos caducan
                if self.cfg.canal_persistencia == "efimero":
                    if step_actual - d.get("step", 0) > self.cfg.canal_ttl:
                        continue

                # direccionamiento: punto a punto respeta el destinatario
                if self.cfg.canal_direccionamiento == "punto_a_punto":
                    if d.get("para") not in (None, lector):
                        continue

                nuevos.append((d["agent_id"], d["event_id"], d["msg"]))
            self._offsets[(lector, fuente)] = len(lineas)
        return nuevos
