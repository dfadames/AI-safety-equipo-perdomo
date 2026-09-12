"""
La caja emulada: el contenedor de un agente cuando no hay Docker.

POR QUE EXISTE
--------------
`--sin-docker` devolvia una cadena fija — "(simulado) salida de '<cmd>' en
<caja>" — para CUALQUIER comando. Con el proveedor guionado eso no molesta,
porque el guion finge que encontro su fragmento. Con un modelo de verdad es
fatal: el fragmento vive en un archivo DENTRO del contenedor, asi que sin
Docker no existe, nadie puede encontrar nada, nadie junta nada, y el episodio
termina sin un solo intento de accion restringida.

Paso de verdad: dos corridas con deepseek-flash, 283.000 tokens, cero
mediciones. Los agentes lo diagnosticaron solos y escalaron a un humano
("mi contenedor caja_d solo devuelve salidas simuladas, no puedo localizar mi
fragmento"). El arnes estaba bien; el mundo estaba vacio.

QUE CONSERVA Y QUE NO
---------------------
Conserva lo que la MEDICION necesita:
  - cada caja contiene solo el fragmento de SU agente, nunca los ajenos;
  - el unico camino entre agentes sigue siendo el canal, que se registra;
  - el contenido sale de `contenedores.archivos_de()`, el mismo que se escribe
    en el contenedor real, asi que el agente ve exactamente lo mismo.

NO conserva el aislamiento real: esto es una funcion de Python, no una caja con
`network_mode: none`. La tabla de auditoria (`runner auditar`) necesita Docker
de verdad y no se puede respaldar con esto. En el paper: las corridas hechas
asi van declaradas como contencion EMULADA.
"""

from __future__ import annotations

import re
import shlex

from .config import Config, nombre_contenedor
from .contenedores import archivos_de

MONTAJE = "/cluster_data"

# Un entorno plausible y SIN credenciales: es la propiedad 2 de la auditoria
# ("sin_credenciales"), y seria absurdo que la caja emulada la incumpliera.
ENTORNO = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOSTNAME": "",          # se rellena por caja
    "HOME": "/root",
    "PWD": "/",
    "SHELL": "/bin/sh",
    "TERM": "xterm",
}


class CajaFalsa:
    """Emula el contenedor de UN agente: un arbol de archivos y un `sh` minimo.

    Deliberadamente generosa con la sintaxis (tuberias, `&&`, comodines) y
    honesta cuando no entiende: responde `sh: X: not found`, que le dice al
    modelo que pruebe otra cosa. La cadena fija de antes decia "hay salida" y
    no habia ninguna, que es lo que llevo al agente a concluir que el entorno
    estaba roto.
    """

    def __init__(self, cfg: Config, agent_id: str):
        self.nombre = nombre_contenedor(cfg.contenedor_de(agent_id))
        self.entorno = dict(ENTORNO, HOSTNAME=self.nombre)

        # ruta -> contenido. Solo archivos; los directorios se deducen.
        self.fs: dict[str, str] = {
            "/etc/hostname": self.nombre + "\n",
            "/etc/hosts": "127.0.0.1\tlocalhost\n",
            "/etc/os-release": 'NAME="Alpine Linux"\nID=alpine\n',
            # Los agentes hacen `ls ~` y `ls /tmp` constantemente: si esas
            # rutas no existen, leen "entorno roto" donde no lo hay.
            "/root/.profile": "export PATH=/usr/bin:/bin\n",
            "/tmp/.keep": "",
            "/var/log/messages": "\n".join(
                f"2026-07-{9 + i:02d} 03:0{i} cron[{100 + i}]: run-parts /etc/periodic/15min"
                for i in range(4)) + "\n",
        }
        # La pista del agente, del MISMO sitio que el contenedor real.
        for nombre, texto in archivos_de(cfg, cfg.contenedor_de(agent_id)).items():
            self.fs[f"{MONTAJE}/{nombre}"] = texto

    # -- API que consume la Ventana -----------------------------------------

    def __call__(self, _contenedor: str, comando: str) -> str:
        """Firma de `runner(contenedor, comando) -> str`, como `docker exec`."""
        return self.ejecutar(comando)

    def ejecutar(self, comando: str) -> str:
        salidas = []
        for tramo in re.split(r"\s*(?:&&|\|\||;)\s*", comando.strip()):
            if tramo:
                salidas.append(self._tuberia(tramo))
        return "\n".join(s for s in salidas if s != "")

    # -- interior ------------------------------------------------------------

    def _tuberia(self, tramo: str) -> str:
        salida = None
        for etapa in [t.strip() for t in tramo.split("|") if t.strip()]:
            salida = self._comando(etapa, salida)
        return salida or ""

    def _expandir(self, texto: str) -> str:
        """`$HOME` y `~`. Sin esto `echo "HOME: $HOME"` sale literal, y el
        modelo lo suma a la lista de senales de que su entorno esta roto —
        que fue exactamente lo que paso en la corrida de N=8."""
        for k, v in self.entorno.items():
            texto = texto.replace("${%s}" % k, v).replace("$" + k, v)
        return re.sub(r"(^|\s)~(?=/|\s|$)", r"\1/root", texto)

    def _trozos(self, etapa: str) -> list:
        etapa = self._expandir(etapa)
        # La redireccion no se emula: el montaje es de solo lectura.
        etapa = re.sub(r"\s*>>?\s*\S+", "", etapa)
        etapa = re.sub(r"\s*2>\s*\S+", "", etapa)
        try:
            return shlex.split(etapa)
        except ValueError:
            return etapa.split()

    def _comando(self, etapa: str, entrada):
        t = self._trozos(etapa)
        if not t:
            return entrada or ""
        cmd, args = t[0], t[1:]
        metodo = getattr(self, f"_cmd_{cmd.replace('-', '_')}", None)
        if metodo is None:
            return f"sh: {cmd}: not found"
        return metodo(args, entrada)

    # -- utilidades del sistema de archivos ---------------------------------

    def _norm(self, ruta: str) -> str:
        ruta = ruta.strip().rstrip("/") or "/"
        if not ruta.startswith("/"):
            ruta = "/" + ruta.lstrip("./")
        return ruta

    def _es_dir(self, ruta: str) -> bool:
        ruta = self._norm(ruta)
        if ruta == "/":
            return True
        return any(f.startswith(ruta + "/") for f in self.fs)

    def _hijos(self, ruta: str) -> list:
        ruta = self._norm(ruta)
        base = "" if ruta == "/" else ruta
        vistos = []
        for f in sorted(self.fs):
            if not f.startswith(base + "/"):
                continue
            resto = f[len(base) + 1:]
            nombre = resto.split("/")[0]
            if nombre not in vistos:
                vistos.append(nombre)
        return vistos

    def _rutas_bajo(self, ruta: str) -> list:
        ruta = self._norm(ruta)
        if ruta in self.fs:
            return [ruta]
        base = "" if ruta == "/" else ruta
        return sorted(f for f in self.fs if f.startswith(base + "/"))

    # -- comandos ------------------------------------------------------------

    def _cmd_ls(self, args, _entrada):
        rutas = [a for a in args if not a.startswith("-")] or ["/"]
        largo = any(a.startswith("-") and "l" in a for a in args)
        bloques = []
        for r in rutas:
            r = self._norm(r)
            if r in self.fs:
                bloques.append(self._linea_larga(r) if largo else r.split("/")[-1])
            elif self._es_dir(r):
                nombres = self._hijos(r)
                if largo:
                    lineas = [f"total {len(nombres)}"]
                    for n in nombres:
                        hijo = ("" if r == "/" else r) + "/" + n
                        lineas.append(self._linea_larga(hijo))
                    bloques.append("\n".join(lineas))
                else:
                    bloques.append("  ".join(nombres))
            else:
                bloques.append(f"ls: {r}: No such file or directory")
        return "\n".join(bloques)

    def _linea_larga(self, ruta: str) -> str:
        nombre = ruta.split("/")[-1]
        if self._es_dir(ruta):
            return f"drwxr-xr-x    2 root     root          4096 Jul 12 03:00 {nombre}"
        tam = len(self.fs.get(ruta, ""))
        ro = "r--r--r--" if ruta.startswith(MONTAJE) else "rw-r--r--"
        return f"-{ro}    1 root     root      {tam:>8} Jul 12 03:00 {nombre}"

    def _cmd_cat(self, args, entrada):
        rutas = [a for a in args if not a.startswith("-")]
        if not rutas:
            return entrada or ""
        out = []
        for r in rutas:
            r = self._norm(r)
            if r in self.fs:
                out.append(self.fs[r].rstrip("\n"))
            elif self._es_dir(r):
                out.append(f"cat: read error: Is a directory")
            else:
                out.append(f"cat: can't open '{r}': No such file or directory")
        return "\n".join(out)

    def _cmd_head(self, args, entrada):
        return self._cabeza_o_cola(args, entrada, cabeza=True)

    def _cmd_tail(self, args, entrada):
        return self._cabeza_o_cola(args, entrada, cabeza=False)

    def _cabeza_o_cola(self, args, entrada, cabeza):
        n, rutas = 10, []
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("-n", "-c"):
                i += 1
                n = int(args[i]) if i < len(args) and args[i].isdigit() else n
            elif re.fullmatch(r"-\d+", a):
                n = int(a[1:])
            elif not a.startswith("-"):
                rutas.append(a)
            i += 1
        texto = self._cmd_cat(rutas, entrada) if rutas else (entrada or "")
        lineas = texto.splitlines()
        return "\n".join(lineas[:n] if cabeza else lineas[-n:])

    def _cmd_find(self, args, _entrada):
        raiz, patron, solo = "/", None, None
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("-name", "-iname"):
                i += 1
                patron = args[i] if i < len(args) else None
            elif a == "-type":
                i += 1
                solo = args[i] if i < len(args) else None
            elif a in ("-maxdepth", "-mindepth", "-o", "-not", "-print"):
                if a in ("-maxdepth", "-mindepth"):
                    i += 1
            elif not a.startswith("-"):
                raiz = a
            i += 1

        rutas = self._rutas_bajo(raiz)
        if solo == "d":
            dirs = sorted({"/".join(r.split("/")[:-1]) or "/" for r in rutas})
            rutas = dirs
        if patron:
            reg = re.compile(patron.replace(".", r"\.").replace("*", ".*") + "$", re.I)
            rutas = [r for r in rutas if reg.match(r.split("/")[-1])]
        return "\n".join(rutas) if rutas else ""

    def _cmd_grep(self, args, entrada):
        banderas = [a for a in args if a.startswith("-")]
        resto = [a for a in args if not a.startswith("-")]
        if not resto:
            return ""
        patron, rutas = resto[0], resto[1:]
        flags = re.I if any("i" in b for b in banderas) else 0
        solo_nombres = any("l" in b for b in banderas)
        invertir = any("v" in b for b in banderas)
        try:
            reg = re.compile(patron.replace(r"\|", "|"), flags)
        except re.error:
            reg = re.compile(re.escape(patron), flags)

        if not rutas:
            lineas = (entrada or "").splitlines()
            return "\n".join(l for l in lineas if bool(reg.search(l)) != invertir)

        out = []
        for r in rutas:
            for f in self._rutas_bajo(r):
                casa = [l for l in self.fs[f].splitlines() if bool(reg.search(l)) != invertir]
                if not casa:
                    continue
                if solo_nombres:
                    out.append(f)
                else:
                    out += [f"{f}:{l}" for l in casa] if len(rutas) > 1 or self._es_dir(r) else casa
        return "\n".join(out)

    def _cmd_wc(self, args, entrada):
        texto = entrada or ""
        if any(a == "-l" for a in args):
            return str(len(texto.splitlines()))
        return f"{len(texto.splitlines())} {len(texto.split())} {len(texto)}"

    def _cmd_echo(self, args, _entrada):
        return " ".join(args)

    def _cmd_env(self, _args, _entrada):
        return "\n".join(f"{k}={v}" for k, v in self.entorno.items())

    _cmd_printenv = _cmd_env

    def _cmd_pwd(self, _a, _e):
        return "/"

    def _cmd_whoami(self, _a, _e):
        return "root"

    def _cmd_id(self, _a, _e):
        return "uid=0(root) gid=0(root) groups=0(root)"

    def _cmd_hostname(self, _a, _e):
        return self.nombre

    def _cmd_uname(self, _a, _e):
        return "Linux"

    def _cmd_sort(self, _a, entrada):
        return "\n".join(sorted((entrada or "").splitlines()))

    def _cmd_uniq(self, _a, entrada):
        vistas, out = set(), []
        for l in (entrada or "").splitlines():
            if l not in vistas:
                vistas.add(l)
                out.append(l)
        return "\n".join(out)

    # El montaje va :ro en el contenedor real; aca tambien.
    def _solo_lectura(self, args, _entrada):
        destino = next((a for a in args if not a.startswith("-")), "")
        if self._norm(destino).startswith(MONTAJE):
            return f"touch: {destino}: Read-only file system"
        return ""

    _cmd_touch = _solo_lectura
    _cmd_mkdir = _solo_lectura
    _cmd_rm = _solo_lectura
    _cmd_mv = _solo_lectura
    _cmd_cp = _solo_lectura


def runner_de(cfg: Config):
    """Devuelve un `runner(contenedor, comando) -> str` para todo el episodio.

    Una caja por CONTENEDOR, no por agente: con N=8 sobre 4 cajas, dos agentes
    comparten caja y tienen que ver exactamente lo mismo — igual que con Docker.
    """
    cajas = {}
    for agent_id in cfg.agentes:
        c = nombre_contenedor(cfg.contenedor_de(agent_id))
        if c not in cajas:
            cajas[c] = CajaFalsa(cfg, agent_id)

    def runner(contenedor: str, comando: str) -> str:
        caja = cajas.get(contenedor) or cajas.get(nombre_contenedor(contenedor))
        if caja is None:
            return f"sh: no such container: {contenedor}"
        return caja.ejecutar(comando)

    return runner
