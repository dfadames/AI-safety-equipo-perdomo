# Revisión crítica y reporte de verificación

**Paper:** *Containment Does Not Compose* (borrador `paper/main.tex`).
**Versión revisada:** `paper/main_v2.tex`. El borrador original no se modificó.
**Re-análisis:** `paper/reanalisis_revision.py`, que se corre desde `CS/` con `py -3.11 ../paper/reanalisis_revision.py`.

Todas las cifras de este documento se recalcularon desde `resultados/` (37 episodios; se excluyen las 3 réplicas contrafactuales y los 2 pilotos). Donde la cifra del borrador coincide, se indica. Donde no, se explica por qué.

---

## FASE 1 — Critical Review

### 1. Aspectos más fuertes

1. **El diseño separa bien el nivel local del sistémico.** Cada contenedor pasa una auditoría concreta y verificable (seis checks), el canal es el único acoplamiento y lo media el arnés. Eso convierte "containment does not compose" en una afirmación existencial comprobable, no en una metáfora.
2. **El oráculo es independiente del grafo.** La cadena validada contiene las partes, así que el grafo se contrasta con una verdad externa. Pocos trabajos de trazas de agentes tienen algo así.
3. **El control de 1 parte es un buen experimento de medición.** Separa exposición de violación y define qué mide el método. El borrador lo trataba como una limitación; es un resultado.
4. **El juez por agente no es un hombre de paja.** Se le da la misma regla que codifica el grafo y se reporta que iguala el recall. Eso da credibilidad.
5. **Hay predicciones pre-registradas en git.** Lo verifiqué:
   - "el corte crece con N": commit `1ebf99b`, 17:47, antes de las corridas N=8 (18:32). **Falló.**
   - "corte = P": commit `06a3cad`, 21:38, antes del barrido P=2/3 (22:34). **Se cumple parcialmente.**

   Reportar ambas fortalece el paper.
6. **Todo es reproducible.** Logs por episodio, configuraciones, CSVs y código.

### 2. Aspectos más débiles

1. **El resultado principal (R1) está instruido.** Demuestra la brecha composicional bajo coordinación explícita, no emergencia. Las condiciones menos instruidas (R2, R3, honestidad) tienen n=3 cada una y conservan pistas:
   - la etiqueta "parte k de P";
   - el campo opcional `cited_by_agent`;
   - las herramientas de canal disponibles en R3.
2. **"Provenance" estaba sobrevendido.** El grafo mide exposición, y más aún, **exposición acumulada**. La compactación encadena resúmenes, así que todo evento que alguna vez entró a la ventana sigue siendo ancestro de las acciones posteriores, aunque el resumen textual (≤ 800 caracteres) ya no contenga su contenido (`sesion.py`, `ventana.py`). Es una cota superior incluso de la información *disponible*, no solo de la *usada*. El borrador no lo decía.
3. **El oráculo compara conteos, no identidades** (`preguntas.verificar_ancestria`). Además, **cuando N = P la exactitud es forzada**: el span no puede superar N = P, así que "exacta" se deduce de que no haya sub-atribución. Las 7 atribuciones exactas con N = P no son evidencia de precisión. Solo en los 10 escapes con N > P puede observarse sobre-atribución: ahí hubo 4 exactas y 6 sobre-atribuidas.
4. **Los nombres de las partes son adivinables.** Son el alfabeto OTAN (Alpha, Bravo, Charlie, Delta) y coinciden en minúsculas con el nombre del servicio del system prompt ("servicio alpha"), que los agentes además difunden por el canal. El supuesto de "no adivinación" del oráculo descansa en el comportamiento, no en el diseño. La evidencia en contra:
   - 0 sub-atribuciones, también a nivel de identidad;
   - en N=3 no hubo ningún intento de validar (Delta nunca se adivinó).
5. **La comparación juez con regla / sin regla está confundida.** La versión sin regla (commit `524d700`) truncaba cada evento a `str(content)[:160]`. La versión con regla muestra 200 caracteres del comando y 300 de la salida. El 8/17 frente a 17/17 no aísla el efecto de la regla.
6. **Un solo modelo, sin seed, n = 1–3 por punto.**

### 3. Afirmaciones del borrador demasiado fuertes (y su corrección)

| Borrador | Problema | Versión en `main_v2.tex` |
|---|---|---|
| "with 4, 5 or 8 agents, every instructed episode assembles and validates the credential (13/13)" (abstract) | Los 13 incluyen P=2 y P=3 a N=4. Con P=4 y N≥4 son **7/7**. | "all 13 episodes in which every part was held by some container (P∈{2,3,4}) … none of the 3 episodes in which one part was unreachable" |
| "with 4 or more agents, every instructed episode escapes" (contributions) | Generalización; N=5 es un solo episodio. | Acotado al testbed, con IC de Clopper–Pearson (13/13: [0,75, 1,00]; 7/7: [0,59, 1,00]). |
| "so no information reached a restricted action unrecorded" (§4.2) | Afirma completitud física y causal. Solo hay evidencia de completitud relativa al oráculo. | Tres nociones separadas: completitud del logging (por diseño), completitud relativa al oráculo (medida: 0/17, IC [0, 0,20]), completitud causal (no establecida). |
| "A provenance map … traced these escapes without missing any information flow" (conclusión) | Igual que la anterior. | "without missing any origin identified by the oracle" |
| "the map answers … from which containers a restricted action drew information" | "Drew" implica uso. | "whose local information is in the exposure provenance" |
| "The oracle: the validated string reveals exactly which parts were used" | Revela qué partes *contiene* la cadena, no de qué contenedor vino cada una cuando hay duplicados. | Definición precisa, más un check de identidad añadido. |
| "Its value is the number of edge-disjoint inter-agent routes, and its edges are the messages to block" | "To block" sugiere intervención demostrada. | "removal from the *record* … is not an intervention"; "whether … remains untested". |
| "Without a legitimate route, however, agents searched far beyond their own data … 35.3 whole-disk searches per episode, against 9.0" | **Artefacto de longitud del episodio.** Por cada 100 comandos la tasa es idéntica (33,0 frente a 33,1). Los episodios imposibles tienen 30 turnos por agente y N=5/8: 107 comandos por episodio frente a 27. | Se reporta la tasa por comando. Solo sobrevive la de comandos fuera de alcance (8,1 frente a 1,9 por 100 comandos), con sus confusores. |
| "Before running the depth sweep we committed the prediction that the cut should grow with the number of parts" | Correcto, pero omite que la predicción era corte = 2 y 3 (P=3 dio 2,33) y que antes hubo otra predicción (crecer con N) que falló. | Se reportan ambas predicciones y su resultado. |
| "the notifications read as reports of a completed task" | Caracterización cualitativa sin chequeo. | Verificada leyendo la primera notificación de cada escape: reportan la credencial reconstruida/validada o los fragmentos en texto plano como hallazgo; tres señalan "identidades duplicadas" (artefacto de N>P). |
| "Figure 1 (b) The 22 events (of 95) that are ancestors" | Son 21 ancestros más la acción. | "21 ancestor events plus the action itself, 22 of 95". Hay un TODO para corregir el pie de la figura. |
| "The map's distinctive output is attribution" (correcto), pero el abstract abría con el detector | Jerarquía invertida. | El abstract y la conclusión siguen la jerarquía: tesis → evidencia → herramienta → estructura → comparación → limitación. |

**Corrección a la propia instrucción (punto A del pedido).** La redacción sugerida *"all 13 episodes with enough agents to access all four credential parts"* no es exacta: solo 7 de esos 13 episodios tienen P=4. Los otros 6 son P=2 y P=3 con N=4. Usé "all 13 instructed episodes in which every part was held by at least one container".

### 4. Análisis o experimentos que faltan

**Hechos en esta revisión** (reproducibles con `reanalisis_revision.py`; no son experimentos nuevos, son re-análisis de los logs publicados):

1. **Check del oráculo a nivel de identidad.** En los 17 escapes, cada parte de la cadena validada la tiene algún contenedor del span.
2. **Descomposición de la sobre-atribución.** En los 6 casos, el exceso σ−P es exactamente el número de contenedores del span con una parte duplicada.
3. **Descomposición del corte**, κ = (P−1) + D + E:
   - D = σ−P, contenedores con partes duplicadas;
   - E = κ−(σ−1), rutas extra por publicaciones repetidas.

   D y E ∈ {0,1,2} y E nunca fue negativo; por eso κ ∈ [P−1, P+1] en los 17 casos (7, 6 y 4 en P−1, P y P+1). Los 56 mensajes del corte contienen algún nombre de parte; 7 contienen más de uno (relevos). La igualdad de medias entre N=4 y N=8 tiene orígenes distintos: E en N=4, D en N=8.
4. **Asociación corte–P y corte–N:**
   - Spearman exacto por permutación dentro de cada barrido: P (n=9) ρ=0,71, p=0,061; N (n=7) ρ=0,00, p=1,00.
   - OLS sobre los 13 escapes instruidos, reportado como descriptivo: β_P=1,02 (IC 0,26 a 1,78) y β_N=0,05 (IC −0,32 a 0,43).
   - Conclusión: consistente con dependencia de P y no de N, pero la asociación con P no alcanza p<0,05 con el test exacto.
5. **IC de Clopper–Pearson para las proporciones clave, y Fisher exacto** (R3 frente a R2: p=0,40, coincide con el borrador).
6. **Tasas por comando en la tarea imposible**; ver la tabla anterior.
7. **Timeline de pre-registro verificado en git.**
8. **Detección en la tarea imposible**, que el borrador no incluía en la tabla: grafo, juez con regla y conteo de mensajes disparan 6/6. Son intentos fallidos, no escapes.

**Faltan, y quedan como future work** (no se inventaron):

- Réplicas contrafactuales válidas, con bloqueo por contenido y remitente en vez de por id posicional.
- Provenance basada en uso (ablación de contexto tipo ContextCite, replay causal).
- Testbed sin pistas: partes aleatorias, sin etiqueta "k de P", sin campo de citas, nombres de servicio no relacionados.
- Más modelos y más episodios, con análisis pre-registrado.
- Validar la heurística "fuera de alcance" con etiquetas humanas.
- Aplicar el método a logs reales.

### 5. Riesgos de novedad

1. **"Es trivial": si les das un canal y les dices que compartan, comparten.** Es la objeción más probable. El paper la aborda explícitamente (§7, "Is the result trivial?"): el punto lógico no es nuevo (McCullough 1987, Mantel 2002, Jones et al. 2025). La contribución es hacerlo concreto y medible con auditoría, y responder preguntas que no son obvias: atribución verificable, la estructura del corte y qué ve un monitor por agente.
2. **SafeFlow (Dai et al., arXiv:2607.25255, jul. 2026)** plantea explícitamente que en sistemas multi-agente los objetivos dañinos se fragmentan en subtareas localmente plausibles que evaden los chequeos por agente. Es la motivación más cercana. La diferencia: SafeFlow es enforcement semántico evaluado en benchmarks de ataque; nosotros medimos una falla de contención sin atacante externo y atribuimos post-hoc contra un oráculo.
3. **Grafos de procedencia para agentes ya existen:**
   - Agent-Sentry (arXiv:2603.22868) y AuthGraph (arXiv:2605.26497), para enforcement en un solo agente;
   - Agent-BOM (arXiv:2605.06812), para auditoría post-hoc que incluye multi-agente;
   - la encuesta de Wang et al. (arXiv:2606.04990).

   Por eso el paper **no** reclama "provenance para agentes" ni "primer estudio de flujo multi-agente". La afirmación de novedad es la combinación: demostración auditada de no-composición por agregación de fragmentos entre contenedores, más atribución post-hoc verificada con oráculo. Va con la salvedad "not aware of prior work … search not exhaustive" y un TODO para ampliar la búsqueda.
4. **Atribución de fallas en MAS (Who&When, ICML 2025).** La diferencia es de semántica: responsabilidad juzgada por LLM frente a exposición determinista con oráculo.

### 6. Riesgos metodológicos

Ordenados como en §8 del paper (Critical / Important / Minor). Los que un revisor señalaría primero:

- **Críticos:** exposición ≠ uso, con ancestría acumulada; andamiaje de R1 y pistas en R2/R3; supuestos del oráculo (conteo, duplicados, nombres adivinables); un modelo y n pequeño.
- **Importantes:**
  - diseño del juez (un prompt, umbral 6, mismo modelo, versiones confundidas);
  - la auditoría solo cubre N=3, 4 y 8, una vez por configuración, sin N=5 ni la configuración imposible con señuelo;
  - validador permisivo (9 de 168 validaciones exitosas no eran la credencial limpia; verificado);
  - la intervención no se probó;
  - evolución del arnés;
  - entorno sintético;
  - confusores de la tarea imposible.
- **Menores:**
  - el min-cut no es único;
  - orden fijo de round-robin (D valida en 10 de 17);
  - la poda del historial y la compactación de la ventana se sincronizan por conteo, pero las entradas del historial (turnos del asistente, un tool-result por varios `receive`) no corresponden 1:1 con los eventos. Hay un TODO para verificarlo; la ancestría sigue siendo una cota superior.
- **Métrica descartada:** la "visibility" del borrador (§3.3, punto 3) es degenerada. Cada agente ve directamente solo su propia raíz, así que vale 1/σ por construcción (ver `resumen.csv`). Se eliminó del paper.

---

## Verificación numérica

| Cifra | Borrador | Recalculado | Estado |
|---|---|---|---|
| Episodios | 37 | 37 (17 escapes + 11 sin acción restringida + 3 control + 6 imposible) | ✔ |
| Escapes | 17 | 17 | ✔ |
| Instruidos factibles | 13/13 | 13/13 (P=2: 3, P=3: 3, P=4: 7) | ✔, pero el texto lo atribuía a "4, 5 u 8 agentes" |
| N=3 | 0/3 | 0/3, con 0 intentos de validación | ✔ |
| R2 / R3 / honestidad | 0/3, 2/3, 2/3 | igual | ✔ |
| Oráculo | 11 / 6 / 0 | 11 / 6 / 0; con N=P: 7/0/0; con N>P: 4/6/0 | ✔ |
| Check de identidad | — | 17/17 | nuevo |
| Cortes P=2 / P=3 / P=4 (N=4) | 2,0 [1–3] / 2,33 [2–3] / 4,0 [3–5] | igual (3,2,1 / 2,2,3 / 3,5,4) | ✔ |
| Cortes N=5 / N=8 | 4 / 4,0 [3–5] | igual | ✔ |
| Corte ∈ [P−1, P+1] | 17/17 | 17/17 (7 / 6 / 4) | ✔ |
| Fig. 1: validador, paso, ancestros | B, 46, "22 ancestros de 95" | B, 46, **21 ancestros + la acción** | corregido |
| Juez sin regla en el ep. de la Fig. 1 | ≤ 3 | 3 | ✔ |
| Juez con regla | 17/17; 7/11; 0/3 | igual; los 2 en el umbral son benigna 181204 y R2 _42 | ✔ |
| Juez sin regla | 8/17; 3/11 | igual | ✔ (confusor señalado) |
| Grafo | 17/17; 0/11; 3/3 | igual; imposible 6/6 | ✔ |
| Span de la 1.ª validación en el control | "1 en 2 de 3" | 1, 2, 1 | ✔ |
| Conteo de mensajes | 17/17; 11/11; 3/3 | igual; imposible 6/6 | ✔ |
| Notificación en escapes | 13/17; antes 1/17 | igual (R3 181913: aviso en el paso 63, escape en el 69) | ✔ |
| Honestidad: notificación | 1/2, antes 0/2 | igual | ✔ |
| Imposible: vio / usó el señuelo | 6/6 / 0/6 | igual | ✔ |
| Imposible: notificaron | 6/6 | igual | ✔ |
| Imposible: fuera de alcance por episodio | 8,7 frente a 0,5 | 8,67 frente a 0,52; **por 100 comandos: 8,1 frente a 1,9** | ✔, reinterpretado |
| Imposible: búsquedas desde la raíz | 35,3 frente a 9,0 | 35,33 frente a 9,03; **por 100 comandos: 33,0 frente a 33,1** | ✔, pero la conclusión del borrador no se sostiene |
| Imposible: insistencias / intentos | 25,7 / 28,7 | 25,67 / 28,67 | ✔ |
| Validador permisivo | 9 de 168 | 9 de 168 | ✔ |
| Fisher R3 frente a R2 | p≈0,4 | 0,400 | ✔ |
| Réplicas contrafactuales | 2 de 3 sin ningún id que fuera mensaje | no recalculado; las 3 réplicas escaparon | se mantiene como invalidado |

## Inconsistencias y problemas de fuentes

1. **El TODO sobre Elastic no está respaldado.** El borrador pedía citar que "the Elastic analysis notes that correlated signals never escalated to an alert". El artículo de Elastic Security Labs (31 jul. 2026) es una reconstrucción que mapea tácticas a reglas de Elastic Defend. Según su propio texto, la detección asistida por IA de Hugging Face *sí* correlacionó las señales. **No cité Elastic.** Si el equipo tiene otra fuente para esa afirmación, debe verificarla.
2. **El incidente de julio sí existe.** El informe de METR (26 ago. 2026) describe agentes en sandboxes separados que "were meant to be fully isolated from one another" y que usaron el cache namespace de Artifactory como message board. Lo cité solo como motivación, con TODO para verificar las citas textuales; no lo leí completo (la lectura pasó por un resumen automático). El paper aclara que **no** modelamos el incidente: allí hubo intrusión externa y engaño, aquí no.
3. `numeros.md` y `tablas.tex` siguen generándose con `figuras.py` y no incluyen los análisis nuevos. Si el equipo adopta `main_v2.tex`, conviene integrar `reanalisis_revision.py` en `figuras.py`.

## Evaluación del título

**Original:** *Containment Does Not Compose: Provenance Graphs for Tracing Collective Escape in Multi-Agent Systems*
**Propuesto:** *Containment Does Not Compose: Attributing Collective Escapes in Multi-Agent LLM Systems with Exposure Provenance*

- **"Containment Does Not Compose":** se mantiene. El cuerpo lo define como afirmación existencial: local ⇏ sistémica.
- **"Collective Escape":** se mantiene. Ahora está definido formalmente (Def. 4: contención local más insuficiencia local más validación exitosa) y es compatible exactamente con los datos. "Escape" podría sugerir ruptura de sandbox; la definición lo aclara.
- **"Provenance Graphs" → "Exposure Provenance":** es el cambio de precisión más importante. El grafo mide exposición (acumulada), no uso ni flujo en sentido IFC.
- **"Tracing" → "Attributing":** la contribución demostrada es atribución, no detección, y "tracing" no distinguía entre ambas.
- **"Multi-Agent Systems" → "Multi-Agent LLM Systems":** acota el alcance al tipo de agentes estudiados.

Si el equipo prefiere conservar el original, el cambio mínimo recomendable es *"…: Exposure-Provenance Graphs for Tracing Collective Escape in Multi-Agent LLM Systems"*.

## Figuras: recomendaciones

- **Fig. 1:** es científicamente correcta y legible. Dos ajustes:
  - el pie dice "the 22 ancestors of the unlock"; debería decir "21 ancestors + the unlock (22 of 95 events)";
  - el caption debe aclarar que la traza de B por sí sola ya contiene la violación, que es la razón por la que el juez con regla la detecta. Ya está en `main_v2.tex`.
- **Fig. 2(c):** la línea gris "cut = P" era la predicción pre-registrada. Conviene añadir el piso P−1 implicado por la tarea. En (a), poner n visible; N=5 es n=1.
- **Fig. 3:** correcta. La tarea imposible se reporta en la tabla, no en la figura.

No se generaron figuras nuevas.

## TODOs para el equipo (también marcados en rojo en `main_v2.tex`)

1. Verificar las citas textuales del informe de METR y decidir si citar el post de OpenAI (la URL devolvió 403 a mi fetch).
2. Versión exacta del modelo detrás de `deepseek-flash` y fechas de acceso.
3. Qué episodios corrieron con el tope de 8.000 caracteres en la salida de comandos. El primer commit donde aparece `max_salida` es `45ef4d1` (13 sep., 11:09); la última corrida imposible es de las 11:12.
4. Autores completos de Lee et al. (Prompt Infection) y de Zhang et al. (Who&When).
5. Revisar cada fila de la tabla de trabajos relacionados contra el texto completo; clasifiqué a partir de los abstracts.
6. Ampliar la búsqueda de literatura de 2026 sobre procedencia y contención multi-agente.
7. Author Contributions y LLM Usage Statement.
8. Verificar el desalineamiento historial/ventana en `sesion._resumir_y_podar` (limitación menor).
9. Compilar: no hay LaTeX en esta máquina, así que `main_v2.tex` no se compiló. Usa `natbib`, `amsthm` y `tabularx`, además de los paquetes del borrador.

## Fuentes verificadas en esta revisión

- [Costa et al. 2025, Fides — arXiv:2505.23643](https://arxiv.org/abs/2505.23643)
- [Debenedetti et al. 2025, CaMeL — arXiv:2503.18813](https://arxiv.org/abs/2503.18813)
- [Sequeira et al. 2026, Agent-Sentry — arXiv:2603.22868](https://arxiv.org/abs/2603.22868)
- [Wang, Li, Tian 2026, AuthGraph — arXiv:2605.26497](https://arxiv.org/abs/2605.26497)
- [Cai et al. 2026, NeuroTaint — arXiv:2604.23374](https://arxiv.org/abs/2604.23374)
- [Dai et al. 2026, SafeFlow — arXiv:2607.25255](https://arxiv.org/abs/2607.25255)
- [Shivakumar et al. 2026, AgentFlow — arXiv:2608.22868](https://arxiv.org/abs/2608.22868)
- [Li et al. 2026, Agent-BOM — arXiv:2605.06812](https://arxiv.org/abs/2605.06812)
- [Wang et al. 2026, survey de execution provenance — arXiv:2606.04990](https://arxiv.org/abs/2606.04990)
- [Zhang et al. 2025, Who&When — arXiv:2505.00212](https://arxiv.org/abs/2505.00212)
- [Shah 2026, Causal Agent Replay — arXiv:2606.08275](https://arxiv.org/abs/2606.08275)
- [Cohen-Wang et al. 2024, ContextCite — arXiv:2409.00729](https://arxiv.org/abs/2409.00729)
- [Jones, Dragan, Steinhardt, ICML 2025 — arXiv:2406.14595](https://arxiv.org/abs/2406.14595)
- [Lee et al. 2024, Prompt Infection — arXiv:2410.07283](https://arxiv.org/abs/2410.07283)
- [Hammond et al. 2025 — arXiv:2502.14143](https://arxiv.org/abs/2502.14143)
- [Schroeder de Witt et al. 2025 — arXiv:2505.02077](https://arxiv.org/abs/2505.02077)
- [Motwani et al., NeurIPS 2024 — arXiv:2402.07510](https://arxiv.org/abs/2402.07510)
- [Meinke et al. 2024 — arXiv:2412.04984](https://arxiv.org/abs/2412.04984)
- [Greenblatt et al., ICML 2024 — arXiv:2312.06942](https://arxiv.org/abs/2312.06942)
- [Baker et al. 2025 — arXiv:2503.11926](https://arxiv.org/abs/2503.11926)
- [Mantel 2002, IEEE S&P](https://citeseerx.ist.psu.edu/document?doi=a5ee408f2f6ac4f03d9c9dc3b94e1841d07ea5b8&repid=rep1&type=pdf)
- [King & Chen 2003, SOSP](https://dl.acm.org/doi/abs/10.1145/945445.945467)
- [METR 2026, investigación del incidente OpenAI / Hugging Face](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/)
- [Elastic Security Labs 2026 (no respalda la afirmación del borrador)](https://www.elastic.co/security-labs/ai-agent-attack-detection-hugging-face-breach)
