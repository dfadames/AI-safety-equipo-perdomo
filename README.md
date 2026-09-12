# Hormiguero

**Containment Does Not Compose** — fallas a nivel de población en el aislamiento, el monitoreo y el escalamiento de agentes.

AI Incident Response Sprint · Hub Bogotá · 12–13 de septiembre de 2026

---

## Empezar

```sh
sh setup.sh
```

Una vez por persona, al clonar. Activa el hook de pre-commit, crea tu `.env` desde la plantilla y verifica que el bloqueo de secretos funciona.

> **Los hooks de git no viajan con `git clone`.** Si no corres `setup.sh`, tu copia del repo no tiene ninguna protección. Es el paso que más se olvida.

Después abre `.env` y pon tu llave.

---

## Reglas de seguridad — cortas y en serio

1. **Las llaves van en `.env`.** Está en `.gitignore` y el hook bloquea el commit si alguien lo agrega a la fuerza.
2. **Nunca una llave en el código.** Usa `entorno.py`:
   ```python
   from entorno import LLAVE_OPENAI, cfg
   cliente = OpenAI(api_key=str(LLAVE_OPENAI))
   pasos   = cfg("HORMIGUERO_MAX_PASOS", 10, int)
   ```
3. **Si una llave se sube por accidente: rotarla primero.** Borrarla del repo no la des-filtra — ya quedó en la historia, en los clones de los demás y posiblemente en el remoto. Primero se revoca en el proveedor, después se limpia.
4. **`--no-verify` solo si miraste qué te marcó.** El hook te dice exactamente qué línea y por qué.

Falso positivo puntual: agrega `# permitido: no-es-secreto` al final de esa línea.

---

## Qué hay acá

| | |
|---|---|
| `ARRANQUE.html` | **Empieza por acá.** Objetivo, la tarea de cada quien ahora mismo, compuertas y el plan completo |
| `PLAN.md` | El plan en Markdown — la versión editable, la que se actualiza durante el fin de semana |
| `EXPERIMENTOS.md` | Qué le decimos a los agentes, las herramientas, la matriz de corridas |
| `contraste-planes.html` | Qué se adoptó del plan de Gemini, qué se le corrigió y por qué |
| `CS/` | **El sistema completo y conectado, listo para correr experimentos.** Reemplaza `DA/`, `CC/` y `EC/` — ver `CS/README.md` |
| `DA/` `CC/` `EC/` | Versiones previas/dispersas (grafo, entorno, trazas). Historicas: no se les hacen más cambios, todo sigue en `CS/` |
| `entorno.py` | Carga de configuración y secretos, sin dependencias |
| `.githooks/` | El hook que impide subir secretos |

---

## Correr el análisis del grafo

El código vivo está en `CS/` (ver `CS/README.md` para el detalle completo):

```sh
cd CS
pip install -r requirements.txt
py -3.11 -m tests.test_todo                                   # valida todo el sistema sin Docker ni LLM
py -3.11 -m hormiguero.runner barrido --N 1 2 4 8 --episodios 3 --sin-docker --logs runs
py -3.11 -m hormiguero.grafo.agregar runs --csv resultados.csv
```

`grafo.agregar` saca la tabla por episodio, la lista de bloqueo para la réplica contrafactual (consumible con `runner repetir`), y **chequeos de cordura** que avisan si los logs vienen mal. Córrelo después de la primera tanda, antes de lanzar el barrido completo.

---

## Entrega

Lunes 14 de septiembre, 6:59 a.m. hora de Colombia. La v1 se sube el domingo a las 16:00, esté como esté.
