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
from typing import Iterable, Optional

from .config import Config, normalizar_credencial


class Canal:
    def __init__(self, carpeta, cfg: Config, bloqueados: Optional[Iterable[str]] = None,
                 bloqueo_contenido: Optional[dict] = None):
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.cfg = cfg
        # La replica contrafactual: los event_id de `lista_de_bloqueo.json`.
        # Bloquear un mensaje aca es simular que la transferencia nunca llego
        # al lector — el escritor sigue publicando, el lector nunca lo ve.
        #
        # Por event_id ya no sirve: los ids son posicionales (`evt_A_008` es el
        # octavo evento de A) y al repetir con un modelo no determinista caen en
        # otro evento. En 2 de las 3 replicas del 12-sep no se bloqueo ningun
        # mensaje. Se conserva para releer bloqueos viejos y nada mas.
        self._bloqueados = set(bloqueados or ())
        # Lo que si sirve: remitente -> fragmentos. Se retiene el mensaje de ESE
        # agente que lleve ESE contenido, le toque el event_id que le toque.
        self._por_contenido = {a: set(f) for a, f in (bloqueo_contenido or {}).items() if f}
        # Los event_id que no se entregaron. Si al final esto queda vacio, la
        # replica no bloqueo nada y no dice nada: es el chequeo que faltaba.
        self.retenidos: set[str] = set()
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

    def _retener(self, d: dict) -> bool:
        """El bloqueo por CONTENIDO: este remitente no puede entregar este
        fragmento. Se compara sobre el texto normalizado, asi que partirlo con
        guiones o espacios tampoco lo pasa."""
        fragmentos = self._por_contenido.get(d.get("agent_id"))
        if not fragmentos:
            return False
        texto = normalizar_credencial(d.get("msg", ""))
        return any(f in texto for f in fragmentos)

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

        Aplica persistencia, direccionamiento y el bloqueo de la réplica
        contrafactual."""
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

                # réplica contrafactual: este mensaje esta bloqueado, se
                # descarta como si nunca hubiera llegado
                if d["event_id"] in self._bloqueados or self._retener(d):
                    self.retenidos.add(d["event_id"])
                    continue

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
