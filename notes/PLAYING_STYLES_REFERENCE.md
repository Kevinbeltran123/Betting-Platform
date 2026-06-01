# Estilos de Juego por Alineación — Referencia de Análisis

> **Propósito.** Capa de conocimiento (no código) para leer mejor un partido cuando llega la
> **alineación confirmada** (formación + 11). Dos capas:
> - **Capa 1 — Base genérica por formación** (durable, reutilizable para cualquier equipo).
> - **Capa 2 — Overlay por selección** (plantilla + ejemplos; se profundiza on-demand por rival).
>
> Investigado de fuentes confiables (The Coaches' Voice / CV Academy, Premier League tactics,
> Spielverlagerung, The FA, The Football Analyst, Total Football Analysis, Michael Cox/Zonal
> Marking, + 2 papers empíricos). Cada afirmación táctica está atribuida; ver §7 Fuentes.
>
> Alineado con el enfoque **analista** (`feedback_analyst_approach`): esto es *evidencia que tú
> interpretas*, no un score automático.

---

## 0. Cómo usar este documento

1. Llega el XI confirmado vía API-Football (`39_analyze` → `fetch_confirmed_lineup`).
2. **Gap actual a tener en cuenta:** el flujo hoy extrae **solo los nombres** de los 11 y
   **descarta la formación** (`intel_io.py:203-209` ignora el campo `formation` y las coordenadas
   `grid`). Hasta que se cablee, **lee la formación manualmente** de la fuente (API-Football la
   trae como `"4-3-3"`, `"3-5-2"`, etc., y los medios la publican ~60' antes).
3. Con la formación en mano → **Capa 1** te da el arquetipo y, sobre todo, **dónde concede
   ocasiones** esa forma.
4. Cruza con los 11 reales (perfiles de jugador) → la forma cambia según el personal (un 4-3-3 con
   pivote único ≠ con doble pivote camuflado; carrileros ofensivos vs defensivos).
5. Cruza ambas formaciones entre sí → **§5 dinámica formación-vs-formación** (free man, batalla de
   banda, half-space).
6. Traduce a mercado con la **regla de oro** de abajo.

---

## 1. REGLA DE ORO (ancla empírica — leer primero)

La formación es **señal barata pero perecedera y de efecto pequeño**. La evidencia cuantitativa:

| Mercado | ¿La formación lo mueve? | Fuente |
|---|---|---|
| **Córners / posesión** | Sí, **modestamente** (formaciones ofensivas 4-3-3 / 4-2-3-1) | DML 22k partidos (Ruiz-Menárguez & Badiella) |
| **Goles / O-U total** | **Débilmente** — no apostar O/U solo por la forma | DML + competing-risk (PMC11208451) |
| **Team totals / AH** | Tilt modesto hacia el lado de forma más ofensiva (4-3-3/4-2-3-1 = HR de gol favorable) | competing-risk 8 torneos |
| **Tarjetas / rojas** | **NO. Empíricamente inerte.** "other behavioral factors dominate" | DML 22k partidos |

**Consecuencias operativas:**
- Usa la formación como **tilt de córners / team-total / AH no-redondo**, peso pequeño, hacia el
  lado de forma dominante. Nunca como driver principal de 1X2 ni O/U total.
- **Excluye la formación del modelo de tarjetas.** Para cards pesa árbitro, rivalidad/derbi,
  match-status e historial de tarjetas del equipo — no la forma.
- **Córners se modelan mejor con match-status que con forma estática:** el equipo que **persigue**
  gana córners. En vivo, un gol temprano invierte el favorito de córners. (lit. match-status →
  córners: Ashimolowo; PMC4120454; PMC7104793).
- El efecto de forma vale más cuando **coincide** con otras señales del sistema, no aislado.

> ⚠️ Magnitudes: los coeficientes exactos del paper DML (arXiv:2602.16830) se leyeron del abstract
> (el PDF no parseó). Direcciones y los resultados negativos (cards / "park the bus") son fiables;
> verificar magnitudes contra el PDF antes de convertir en feature.

---

## 2. CAPA 1 — Formaciones de línea de 4

Para cada una: forma · con balón · sin balón/presión · transición · fortalezas · **vulnerabilidades
(de dónde salen las ocasiones en contra — la sección clave para apostar)** · dependencia de personal
· lectura de mercado.

### 2.1 — 4-4-2 plano
- **Forma.** Tres líneas rígidas, dos bancos de cuatro, dos delanteros que fijan a ambos centrales. [CV]
- **Con balón.** Amplitud desde los **medios exteriores**; laterales dan apoyo retrasado (overlap/underlap). Los dos puntas enlazan o se desmarcan para vaciar espacio. [CV]
- **Sin balón.** Bloque flexible (alto, medio o bajo — de Hasenhüttl a Simeone/Dyche). Marca híbrida zonal-individual manteniendo compacidad. [CV]
- **Transición.** "El balance perfecto para el contraataque" — bloque compacto + dos puntas para saltar. [CV]
- **Fortalezas.** Fijación central permanente (2 vs 2 CB), compacidad fácil, laterales rara vez en inferioridad. [CV]
- **Vulnerabilidades →** ① **Sobrecarga del mediocampo vs un mediocentro de tres** (la debilidad #1, consenso unánime). ② Pases verticales que rompen líneas en las costuras. ③ Espacio entre líneas cuando un central salta. → *Ocasiones en contra: un mediocentro libre recibiendo entre líneas + balones a la espalda de la línea que saltó.* [CV/consenso]
- **Personal.** Exteriores cruzadores vs interiores; pareja "9+10" vs dos puntas ortodoxos; doble box-to-box vs ancla+llegador (define cuán expuesto está el medio). [CV]
- **Mercado.** Si enfrenta un medio de 3 → cede territorio/córners al rival; pareja de puntas aérea (perfil Dyche/Burnley) → señal *indirecta* de balón parado vía personal, no por la forma.

### 2.2 — 4-4-1-1
> ⚠️ **La peor documentada.** No hay página tier-1 dedicada; CV la describe como la forma **sin balón
> en reposo de un 4-2-3-1**. Perfil apoyado en consenso + formaciones madre — menor confianza.
- **Forma.** 4-4-2 con un punta retrasado al **carril de 10 entre líneas**; spearhead solitario. [consenso]
- **Con balón.** El 10 retrasado es el **conector/creador** principal; amplitud sigue siendo de exteriores + laterales. [consenso]
- **Sin balón.** Cae a 4-4-2 / 4-5-1 compacto; el segundo punta puede gatillar presión sobre el pivote rival. [CV aplicado]
- **Vulnerabilidades →** mismo problema de **dos mediocentros vs un tres**; aislamiento del 9 si el 10 se queda profundo; agujero frente al medio si el 10 no recupera. [consenso]
- **Personal.** Lo define el perfil del 10: creador → forma de construcción; presionador (tipo Müller) → forma de transición/defensa. [CV]

### 2.3 — 4-2-3-1
- **Forma.** Cuatro líneas: defensa, **doble pivote**, tridente de creación, 9 solitario. [CV]
- **Con balón.** Amplitud de **laterales** mientras los extremos entran dentro (a menudo a pie cambiado); el doble pivote abre para cambiar de orientación. 9 + 10 rotan y arrastran marcas. Muy amigable a la posesión (muchos triángulos). [CV]
- **Sin balón.** El 9 inicia presión con el 10 subiendo "como un dos plano"; el doble pivote cubre lateral. En bloque medio/bajo → 4-4-2 / 4-4-1-1 escalonado. [CV]
- **Transición.** Seguridad defensiva alta (el doble pivote es capa extra); un pivote puede salir al contra. Coste: lento para llevar gente arriba → ataques sin apoyo. [CV]
- **Fortalezas.** Tres mediocampistas sobrecargan a un dos rival; base sólida para rotaciones de lateral; difícil de penetrar por el centro. [CV]
- **Vulnerabilidades →** ① **Aislamiento del 9**. ② El "tres" puede ser sobrecargado por un cuatro (p.ej. rombo). ③ **El cambio de orientación que pasa por encima del pivote:** con ambos laterales subidos, un pivote cubre a uno; al deslizarse, el otro pivote queda solo y un cambio rápido pasa por encima de **ambos** — el punto débil clásico. → *Ocasiones en contra: cambios rápidos al espacio detrás del lateral subido.* [CV]
- **Personal.** **La pareja de pivotes define el estilo** (regista+llegador vs ancla pura); laterales overlapping vs lateral invertido (que vuelve la defensa un tres); tridente rotativo vs extremos a pie cambiado. [CV]

### 2.4 — 4-3-3
- **Forma.** Línea de 4 + medio de **tres (pivote único + dos 8s)** + dos extremos alrededor de un 9. Huella alta, ancha, de posesión. [CV]
- **Con balón.** Amplitud múltiple (laterales suben con extremos a pie cambiado); el pivote conecta y dirige los cambios; el central puede pisar el medio → **sobrecarga central**. Los 8s atacan los carriles interiores. Triángulos naturales. [CV]
- **Sin balón.** Hecho para **presión alta** (tres delanteros vs línea de 4). Extremos presionan hacia dentro o hacia fuera según la trampa; puede mutar a "dos ancla + uno adelantado". [CV]
- **Transición.** Amenaza de contra excelente (hasta un frente de cinco) **pero exposición real al contra-contra**: al volcarse arriba quedan cortos atrás → carreras largas de recuperación. [CV]
- **Vulnerabilidades →** ① **El carril lateral-extremo** (la debilidad estrella): el espacio entre lateral y extremo es atacado por contras y cambios directos. ② Exposición al contra cuando se vuelca. ③ Aislamiento del 9. → *Ocasiones en contra: carriles anchos en transición + balones a la espalda del lateral subido.* [CV]
- **Personal — el más rico.** Laterales como motor de amplitud (Liverpool TAA/Robertson) vs asimétrico (Napoli); **extremos a pie cambiado** (Salah/Mané, abren overlap 2v1) vs extremos de banda (fuerzan 1v1); **falso 9** (Firmino) que sobrecarga el medio; pivote único que se vuelve doble pivote al defender. [CV]
- **Mercado.** Lado dominante con sobrecarga central → tilt de córners/shots/team-total; pero ojo BTTS por el carril que concede en transición.

### 2.5 — 4-1-4-1
- **Forma.** Línea de 4 + **un solo mediocentro defensivo** + línea de cuatro (2 centrales + 2 exteriores **más profundos** que en 4-3-3) + 9 solitario. La forma de línea de 4 **más compacta por el centro**. [CV]
- **Con balón.** Un mediocentro baja a doble pivote temporal con el 6; como los exteriores arrancan profundos, **conducen** más; laterales dan apoyo temprano. Se vuelve 4-3-3 al atacar. [CV]
- **Sin balón.** El 9 presiona o tapa el acceso al pivote rival; trío central protege; exteriores cierran. Resultado: **muchísima protección central, muy difícil progresar por dentro** — su fortaleza definitoria. [CV]
- **Transición.** Versátil (muta a 4-3-3 / 3-2-4-1 en un movimiento), pero **contra menos productiva** (exteriores/medios cargados de tarea defensiva); 9 se aísla. [CV]
- **Vulnerabilidades →** invita presión al construir tras recuperar; sacrifica amenaza de contra; aislamiento del 9. → *Ocasiones en contra: por **fuera** y de **segundas jugadas**, no por el centro (que es duro de romper).* [CV]
- **Personal.** El mismo dibujo abarca desde el búnker de Mourinho hasta la presión alta de Klopp — puro personal e instrucción. [CV]

### 2.6 — 4-3-1-2 / rombo (4-4-2 diamond)
- **Forma.** Pivote en la base, **dos 8s** en los lados del rombo, **10** en la punta, **dos puntas**. Estrecho por diseño — ocupa la columna central y **renuncia a las bandas**. [PL]
- **Con balón.** El pivote ayuda a salir/baja a la línea → **los laterales son la única fuente de amplitud**. El 10 ataca la Zona 14; los 8s box-to-box por dentro; dos puntas fijan a los centrales. [PL]
- **Sin balón.** **Trampa de presión central:** puntas presionan de fuera a dentro, el 10 marca/tapa al pivote rival, el 6 protege a los centrales. [PL]
- **Vulnerabilidades → (las más nítidas de todas)** ① **Sin amplitud natural** → el rival gana metros por **fuera** en transición. ② **Laterales sobrecargados** (2v1) sin protección. ③ Acceso restringido a los puntas (centro congestionado) → balones largos predecibles. → *Ocasiones en contra: casi todas por los **carriles anchos**, centros/cut-backs contra laterales aislados, y cambios rápidos a banda.* El mapeo forma→espacio más claro de todos. [PL/consenso]
- **Personal.** **El perfil del lateral es decisivo** (dan toda la amplitud → atléticos, ofensivos); el 10 fija la identidad ofensiva; los puntas fijan o uno se abre a fabricar la amplitud que falta. [PL]
- **Mercado.** El más explotable: **córners y centros** del rival por banda; cambios de orientación.

---

## 3. CAPA 1 — Formaciones de línea de 3 / 5

> **¿Por qué cambiar a línea de 3?** Tres motivos recurrentes en las fuentes: ① **igualar a dos
> puntas** rivales (mantener un +1 atrás); ② **construir con un hombre más vs presión alta** (los
> centrales abiertos generan 2v1 y outlet para el cambio); ③ **subir a los carriles**, liberando a
> los carrileros que recuperan a cinco sin balón. [consenso CV + The FA]
>
> **Trade-off universal:** cubre **menos amplitud horizontal** que la línea de 4 → el espacio
> alrededor de los tres y **detrás de los carrileros altos** es el precio estructural. [consenso]

### 3.1 — 3-5-2
- **Forma.** 3 centrales (carril central + interiores), 2 **carrileros** (única amplitud), medio de 3, 2 puntas que estiran la última línea. [CV]
- **Con balón.** La línea de 3 **da superioridad en la salida** (difícil que el rival comprometa tres a presionar). Carrileros casi extremos → carácter ofensivo; los 8s hacen carreras verticales por los carriles interiores. [CV]
- **Sin balón.** Cae a **5-3-2 / 5-4-1**; el carrilero del lado del balón presiona, el otro entra a cinco. Como bloque presionante puede formar un 4-4-2 que orienta a banda. [CV]
- **Transición.** Dos puntas = outlet de contra integrado; tres centrales protegen. **Vulnerabilidad:** flancos abiertos cuando los carrileros quedan altos. [CV]
- **Vulnerabilidades →** ① **Las bandas** (sin extremo natural → el canal detrás/fuera del carrilero alto es la fuente #1, atacado por extremo + lateral solapando). ② Sobrecargas anchas que abren el half-space. ③ El **tres central puede ser superado** vs un medio numeroso por los cambios. [CV/JobsInFootball]
- **Personal.** Carrileros ofensivos → bloque alto tipo extremos; carrileros defensivos → 5-3-2 reactivo. Centrales con salida habilitan la superioridad; el **fondo del carrilero es la mayor dependencia**. [CV]

### 3.2 — 3-4-3
- **Forma.** 3 centrales, **doble pivote**, 2 carrileros, frente de 3. [CV]
- **Con balón.** El doble pivote conecta defensa-carrileros-frente; **sobrecargas anchas** (carrilero + atacante exterior) y presión central de tres; puede fijar alta la línea rival. [CV/PL]
- **Sin balón.** Se vuelve **5-2-3 / 5-4-1**; el doble pivote cubre entre líneas. Presión viable (estilo Amorim) pero exigente. [CV/TFA]
- **Transición.** Fuerte contra vertical al frente de 3. **Vulnerabilidad:** contras del rival a **zonas anchas** (la línea de 3 cubre menos) y **el doble pivote puede ser sobrecargado** tras perder. [CV]
- **Vulnerabilidades →** ① carriles anchos detrás de carrileros altos (la estrella). ② mediocampo central si sobrecargan a los dos pivotes. ③ ataques rápidos y directos por banda vs la línea de 3. [Murcia FA/CV]
- **Personal.** Bisagra en **carrileros de ida y vuelta** + pivote que tape y progrese; sin cohesión "la forma se cae". [Murcia FA]

### 3.3 — 3-4-2-1
- **Forma.** 3 centrales, doble pivote, 2 carrileros, **dos 10s en los half-spaces**, 1 punta. Los dos 10s son el rasgo definitorio. [JobsInFootball/CV]
- **Con balón.** Flexibilidad posicional para crear sobrecargas: carrileros tras los laterales liberan a los 10s; los 10s atacan el canal central-lateral. Half-spaces difíciles de defender. [JobsInFootball]
- **Sin balón.** Cae a **5-4-1 / 5-2-3**; el doble pivote debe quedarse conectado a la defensa para reducir el espacio entre líneas cuando los carrileros recuperan. [CV]
- **Vulnerabilidades →** ① canales anchos detrás de carrileros ("primera zona a explotar"). ② espacio entre líneas (dos pivotes no cubren tanto → un tercer hombre entre líneas es peligroso). ③ sobrecarga del pivote tras transición. [JobsInFootball]
- **Personal.** El más exigente físicamente para carrileros; los 10s necesitan licencia para flotar; sin centrales con salida y pivote resistente a presión, el esquema se atasca. [JobsInFootball]

### 3.4 — 5-3-2 (cara defensiva del 3-5-2)
- **Forma.** Cinco atrás (carrileros ya defensivos), tres mediocentros tapando todo carril central, dos puntas altas como outlet. [SoccerEDU/CV]
- **Con balón.** Forma de **contraataque**: recuperar → soltar a los dos puntas / subir al carrilero lejano. Amplitud solo de carrileros. [soccercoachlab]
- **Sin balón.** Ocho por detrás del balón; cinco cubren cada canal, tres tapan los carriles centrales. **Superioridad 2v1/3v2 en banda** manteniendo seguridad central. [SoccerEDU/FA]
- **Vulnerabilidades →** ① **sobrecarga del mediocampo** (un tres puede ser superado vs un medio más fuerte; el **cambio de orientación** es la herramienta clave para abrirlo). ② espacio detrás del carrilero al saltar. ③ si el bloque es muy bajo → sin outlet de contra, encerrado. [FA/JobsInFootball]
- **Personal.** Defensores concentrados (los lapsus se castigan); carrileros con motor para cubrir solos; puntas rápidos o el output goleador es bajo. [soccercoachlab/TFA]

### 3.5 — 5-4-1 (bloque bajo más profundo)
- **Forma.** Cinco defensas, cuatro por delante, 9 solitario como primer presionante. La variante más conservadora. [The Football Analyst]
- **Con balón.** Reactivo — absorber y contra. Outlets: 9, carrilero lejano, mediocentro que baja. [TFA]
- **Sin balón.** "Uno de los bloques bajos más fiables." Nueve por detrás; **elimina el acceso central directo**; superioridad ancha 2v1/3v2. [TFA]
- **Vulnerabilidades →** ① **aislamiento del 9 → output bajo (~1.23 goles/partido citado)** — señal *under* estructural genuina. ② carrilero estirado por dos hombres anchos. ③ lapsus de concentración en asedios largos. ④ formas de amplitud (4-3-3 con extremos de banda) estiran la línea de 5 y explotan detrás de los carrileros. [TFA/soccercoachlab]
- **Personal.** Concentración y disciplina sobre talento; carrileros con stamina élite; 9 móvil para que la contra sea viable. [TFA]
- **Mercado.** Cuando un equipo se planta en 5-4-1 → señal *under* / portería a cero rival, salvo que el rival tenga amplitud pura para estirarlo.

### 3.6 — 3-2-5 / "3-box-3" (forma *con balón* en la que muta una línea de 4)
> No es formación de inicio — es la **estructura con balón** a la que un 4-3-3 / 4-2-3-1 / 3-4-3
> **se construye** vía laterales invertidos y rotaciones. [The Football Analyst/SoccerTutor]
- **Forma.** 3 atrás + 2 pivote (a menudo los laterales invertidos) + **5 al frente** cubriendo los cinco carriles. El 3+2 es un escudo central de cinco. [TFA]
- **Con balón.** **Ocupación máxima de carriles:** anchos fijan a los laterales rivales, interiores en los half-spaces, 9 fija a los centrales. Vs una línea de 4: "el frente de 5 fija a los cuatro defensas y aún deja uno o dos libres entre líneas, sobre todo en los half-spaces" — **cuatro no cubren cinco carriles**. [TFA]
- **Rest-defence.** El 3+2 es estructura de **resto defensivo**: protege el centro vs contras directas, controla el momento de la recuperación. Esa es la gracia: sobrecargar el último tercio con 5 manteniendo 5 atrás. [TFA]
- **Vulnerabilidades →** ① **canales anchos en transición** si se pierde arriba con laterales/anchos muy altos sin cobertura (el 3-2 protege el *centro* → duelen las contras **anchas y tempranas**). ② **fragilidad por complejidad** (exige coordinación y ejecución técnica altas). [TFA]
- **Personal.** Requiere **laterales invertidos** cómodos en el medio, interiores que lean el half-space, extremos que sostengan amplitud. Sin ese perfil, degrada. [TFA/SoccerTutor Leverkusen]

---

## 4. Matriz de vulnerabilidad — "¿de dónde salen las ocasiones en contra?"

La sección más útil para apostar. Resumen consolidado:

| Formación | Espacio principal que concede | Lectura de mercado | Fuente |
|---|---|---|---|
| 4-4-2 plano | Mediocentro libre entre líneas; verticales en las costuras | rival con medio de 3 → su córners/territorio | [CV] |
| 4-4-1-1 | Igual + hueco frente al medio si el 10 no recupera | similar a 4-4-2 | [consenso] |
| 4-2-3-1 | **Cambio rápido detrás del lateral subido** (pasa por encima del pivote que desliza) | córners/centros del rival a esa banda | [CV] |
| 4-3-3 | **Carril lateral-extremo** en transición; balones a la espalda | BTTS por transición; córners del lado dominante | [CV] |
| 4-1-4-1 | Por fuera y segundas jugadas (el centro es duro de romper) | tiende a *under* central; córners por banda | [CV] |
| Rombo (4-3-1-2) | **Las bandas** — laterales aislados, centros/cut-backs, cambios | el más claro: córners/centros del rival; *over* lateral | [PL/consenso] |
| 3-5-2 / 3-4-3 / 3-4-2-1 | **Canal detrás/fuera del carrilero alto** (debilidad universal de línea de 3) | córners + crossing del rival con extremo de banda + lateral solapando | [consenso unánime] |
| 5-3-2 | Mediocampo (vía cambio de orientación) + detrás del carrilero al saltar | el cambio de juego es la llave; córners en transición | [FA] |
| 5-4-1 | 9 aislado (output bajo) + carrilero estirado | **señal *under* / portería a cero rival** | [TFA] |
| 3-2-5 (con balón) | Contras **anchas y tempranas** en transición | next-team-to-score = rival al contra; BTTS | [TFA] |

**Hilo recurrente:** todo esquema de **un solo 9** (4-2-3-1, 4-3-3, 4-1-4-1, 5-4-1, 4-4-1-1 defensivo)
comparte el **aislamiento del delantero** como vulnerabilidad ofensiva. [CV, repetido]

**Hilo de línea de 3/5:** la debilidad #1 es siempre **el canal detrás del carrilero**; se ataca con
**extremo de banda + lateral solapando**, sobre todo en transición. La llave para abrir una línea de
5 es **el cambio de orientación** (un medio de tres no se desliza lado a lado lo bastante rápido). [consenso]

---

## 5. Dinámica formación-vs-formación

Para cuando tienes **ambas** alineaciones. Lo que crea ventajas:

- **El "hombre libre" (free man).** Una forma que pone un jugador más en una zona genera un
  desmarcado con tiempo. Casos canónicos:
  - **Línea de 3 vs dos puntas** → defensor de sobra, salida cómoda (principio Bielsa). [Bleacher/consenso]
  - **Presión de tres delanteros vs doble pivote (4-2-3-1 / 3-5-2)** → un punta no puede tapar a
    dos pivotes con su cover-shadow → la presión se rompe por el centro. [Spielverlagerung]
  - **Rombo** → sobrecarga central vs cualquier medio de 2 o 3. [CV]
- **Batalla de banda.** Los **carrileros casi siempre son los más anchos** (ganan la banda por
  defecto vs laterales que solo *pueden* subir) → servicio más consistente al área. Solapes lateral
  + extremo crean superioridades. [CV/The Football Analyst]
- **Half-space.** Ruta primaria para saltarse una presión de primera línea; los 8s/10s fingen
  recibir ahí para abrir el centro (Conte 3-5-2 amenaza half-space + banda a la vez). [Spielverlagerung/CV]
- **Trampas de presión y dónde se rompen:**
  - vs doble pivote / box de medio → presión superada por el centro. [Spielverlagerung]
  - **formas que coinciden (3-4-3 v 3-4-3, 4-3-3 v 4-3-3)** → presión posicional/al hombre, pocos
    hombres libres → **partido más controlado, menos eventos** (lean leve a *under* / menos córners). [Spielverlagerung]
  - vs primera línea más ligera (4-4-2 con dos bancos) → acceso de presión más fácil. [Spielverlagerung]

**Mismatches clásicos (tabla rápida):**

| Mismatch | Mecanismo | Lectura |
|---|---|---|
| Línea de 3 vs dos puntas | defensor de sobra, salida cómoda | control del que tiene el +1 |
| Presión de 3 vs doble pivote | el 9 no tapa a ambos pivotes | BTTS / *over* (presión superada) |
| Rombo vs forma con amplitud | rombo gana el centro pero no tiene bandas → batido por cambios y solapes | **córners/centros** del lado ancho |
| Línea de 5 vs línea de 4 | carrileros ganan banda + corredores al half-space | córners; pero quita sobrecargas centrales |
| Formas que coinciden | pocos hombres libres, presión posicional | partido controlado → *under* leve |

---

## 6. CAPA 2 — Overlay por selección

> La base genérica (§2-§5) dice qué *intenta* una forma. El overlay dice cómo **ese equipo concreto**
> la ejecuta — más preciso pero **perecedero** (cambia con DT, lesiones, forma).
>
> **COMPLETO 2026-05-31: las 48 selecciones de WC2026.** §6.1-6.4 = 4 ejemplos detallados
> (Argentina, Francia, España, Brasil); §6.5 = las 44 restantes en formato compacto por
> confederación. Investigado de fuentes confiables 2024-2026.
>
> **Correcciones de DT que el sistema NO tenía (verificar antes de cualquier análisis):** Túnez =
> **Lamouchi** (no Trabelsi, ces. ene-26) · Arabia = **Donis** (no Renard, ces. abr-26) · Ghana =
> **Queiroz** (reemplazó a Addo, abr-26) · Uzbekistán = **Cannavaro** · Irak = **Graham Arnold** ·
> Jordania = **Sellami** (Ammouta llevó la final de Asian Cup) · Bélgica = **Rudi Garcia** ·
> Suecia = **Potter**. Marcadas 🔴 en §6.5. Irán: **Azmoun vetado**. Canadá: **Davies LCA**.
> Uruguay: **crisis/motín Bielsa**.

### Plantilla por selección
```
SELECCIÓN — DT
1. Formación(es) base (y variantes reales).
2. Identidad con balón — posesión vs directo; dónde construyen; creadores; fuente de amplitud.
3. Sin balón — altura/intensidad de presión (alta / bloque medio / bajo); compacidad.
4. Transición — amenaza de contra + vulnerabilidad al ser pillado.
5. Personal clave que define el estilo (y cómo cambia sin ellos).
6. Tendencias de mercado — dominio (córners/shots), cagey (low-scoring), concede en transición
   (BTTS), balón parado.
7. Arquetipo en una línea.
[+ incertidumbres flagueadas, no suavizadas]
```

### 6.1 — ARGENTINA (Scaloni)
- **Formación.** 4-4-2 sin balón que muta a 4-3-3 fluido; Messi cae al half-space derecho.
- **Con balón.** Posesión dominante con **sobrecarga central**; construye por dentro, triángulos, rotaciones de medio (Mac Allister, De Paul, Enzo). Creador: Messi (eje libre); sin él, Mac Allister/De Paul.
- **Sin balón.** Bloque estructurado y balanceado ("balance estructural sobre estilo"), no gegenpressing; comprime el centro.
- **Transición.** Contra-presión fuerte (difícil de robarles); **vulnerabilidad:** la última línea "estuvo cerca de colapsar bajo presión" — frágil contra ritmo.
- **Personal.** **Messi** (todo el eje creativo se dobla a él). Sin Messi/Di María (retirado): equipo de posesión estructurada más ortodoxo, **buscando fuente de amplitud** que reemplace a Di María.
- **Mercado.** Dominio territorial → córners/shots vs débiles; **cagey/low-scoring** al controlar (muchos 1-0). Fragilidad atrás bajo presión directa = vector BTTS/upset. Menos goles de transición sin Di María.
- **Arquetipo.** *Control de posesión con sobrecarga central y eje libre Messi — élite estructural, frágil en transición atrás.*
- ⚠️ Incertidumbre: solución de amplitud post-Di-María + fiabilidad de centrales sin resolver.

### 6.2 — FRANCIA (Deschamps)
- **Formación.** Familia reducible a **4-2-3-1** (usó 4-3-3, 4-4-1-1, 4-3-1-2 cambiando casi cada partido). Deschamps se va tras WC2026.
- **Con balón.** **Pragmático, eficiencia sobre vistosidad**; cede el balón a menudo; ataque montado en meter a **Mbappé** (izq.) + creador/corredor derecho (Dembélé/Olise) en espacio, no en juego posicional sostenido.
- **Sin balón.** **Bloque medio** por diseño — deja avanzar, compacto, organizado, salta. CBs élite (Saliba/Upamecano/Konaté). Ojo: bache 2025 (7 goles en 4 partidos).
- **Transición.** **El núcleo de su identidad** — absorber y saltar a la espalda CB-lateral con la velocidad de Mbappé. De los más temidos al contra. **Vulnerabilidad:** cuando deben romper un bloque bajo → planos, pocos remates.
- **Personal.** **Mbappé** (todo el contra se construye para él); sin él, aún más conservadores.
- **Mercado.** **Cagey / lean *under*** (Euro 2024 famoso por escaso de goles); **balón parado real** (Olise); riesgo de conceder en transición si se sobre-comprometen + fuga defensiva 2025 = señal BTTS. **No** dominan posesión/córners de forma fiable vs buenos.
- **Arquetipo.** *Contragolpeadores de bloque medio — absorber, soltar a Mbappé, ganar feo; escasos de gol cuando deben crear.*
- ⚠️ Incertidumbre: forma defensiva 2025; el "frente de 4 desatado" es excepción, no default.

### 6.3 — ESPAÑA (de la Fuente)
- **Formación.** **4-3-3 en salida** que muta a 4-2-3-1 con balón (final Euro 2024: doble pivote Rodri-Fabián).
- **Con balón.** **Posesión pero verticalizada** (ruptura con el tiki-taka estéril): mantienen el balón (65% vs Inglaterra) pero meten el pase largo especulativo para pillar en transición. Laterales abren para fijar; amplitud y verticalidad de los **extremos**: **Lamine Yamal** (der.) y **Nico Williams** (izq., regate directo).
- **Sin balón.** **Presión alta + posesión-presión híbrida** — presionan arriba para recuperar y re-establecer control.
- **Transición.** Contra-presión fuerte + contra directa real por la velocidad de los extremos (dimensión nueva). Menos vulnerable que Francia/Argentina porque suelen tener el balón.
- **Personal.** **Yamal + Williams** (motor irreemplazable de la verticalidad); **Pedri** (metrónomo) + **Rodri** como 6 — pero **Rodri lesión larga (LCA)**, midfield 2025 rehecho (Zubimendi/Pedri) = **incertidumbre viva**.
- **Mercado.** **El dominio de posesión + córners + shots más limpio de los cuatro** (récord 15 goles Euro 2024, 10 goleadores). Lean **team-overs / España marca-y-controla**, córners altos vs bloques bajos. Balón parado variado. Riesgo BTTS si explotan su línea alta.
- **Arquetipo.** *Posesión-presión vertical — tener el balón y luego cuchillear por Yamal y Williams.*
- ⚠️ Incertidumbre: pivote sin Rodri en flux.

### 6.4 — BRASIL (Ancelotti, confirmado)
- **Formación.** Fluida, no fija; reciente 4-4-2 (Vinícius + Cunha) y frente de 4 "sin 9 fijo" estilo su Madrid (libertad posicional, sobrecargas anchas). Rol de 9 sin resolver.
- **Con balón.** **Giro de la posesión brasileña tradicional hacia fluidez + sobrecargas anchas**; frente de delanteros rápidos que intercambian en vez de un foco fijo (Vinícius, Raphinha, Rodrygo, Cunha, Estêvão).
- **Sin balón.** **Defensa primero** — Ancelotti "restauró estructura", línea alta con centrales agresivos en recuperación; presión alta a ráfagas (5-0 a Corea, 2-0 a Senegal) pero la base es solidez (0-0 con Ecuador).
- **Transición.** **Defender y contra es la filosofía declarada** (Vinícius: el plan WC es "defender muy bien y salir al contra" — ruptura con la tradición de flair). Amenaza de contra élite. **Vulnerabilidad:** sistema nuevo + **9 sin resolver** → cohesión en último tercio es el riesgo abierto.
- **Personal.** Espina del Madrid (Vinícius, Rodrygo, Casemiro, Militão) + Raphinha, Cunha, Estêvão, Neymar. Sin Vinícius cae la amenaza por izquierda.
- **Mercado.** **Más bajo de goles de lo que sugiere su talento** en fases de control (0-0 Ecuador, 1-0 Paraguay) pero **explosivo en transición/presión** (5-0, 3-0) → perfil de **alta varianza**. Varias **porterías a cero** en quali 2025 → ángulos *under* / Brasil-clean-sheet vs débiles.
- **Arquetipo.** *Brasil "madridizado" — solidez de defender-y-contra con frente fluido sin 9 fijo; flair subordinado a estructura.*
- ⚠️ Incertidumbre: sistema nuevo (2025) + 9/forma del frente genuinamente sin asentar.

### Cross-team (lente de apuestas)
| Equipo | Posesión | Presión | Lean goleador | Riesgo BTTS | Balón parado | Incertidumbre |
|---|---|---|---|---|---|---|
| Argentina | Alta (central) | Bloque estructurado | Cagey/control | Med (defensa frágil) | Moderado | Amplitud post-Di-María; CBs |
| Francia | Media (cede) | Bloque medio | **Bajo/unders** | Med (fuga 7 en 4) | **Bueno (Olise)** | Forma defensiva 2025 |
| España | **La más alta** | **Presión alta** | **Overs/dominio** | Med (línea alta) | Bueno (variado) | Rodri LCA — pivote |
| Brasil | Media (por elección) | Alta a ráfagas | Alta-varianza | Bajo (salvo sobre-presión) | n/a (en desarrollo) | Sistema nuevo; 9 sin asentar |

### 6.5 — Overlay completo WC2026 (las 44 restantes, por confederación)

> Investigado 2024-2026 de fuentes confiables (The Athletic, Coaches' Voice, ESPN, Squawka, TFA,
> CAF/FIFA, prensa regional). Formato compacto: **DT (formación) · con balón/amplitud · sin balón ·
> ataque-vs-defensa · personal · mercado · arquetipo · ⚠️ incertidumbre.** "Bandas" vs "centro" =
> de dónde sale la amplitud/penetración. Verificar XI al inicio; muchas son fluidas.

#### UEFA (14)

- **Inglaterra — Tuchel (4-3-3→3-2-5).** Posesión dominante (>70%), lateral invertido (Lewis-Skelly); creación repartida, no un 10 fijo. Bloque front-foot anti-contra. **MEJOR DEFENDIENDO (rotundo):** clasificación 22 GF / **0 GA**, 6+ porterías a cero. Personal: FB invertido habilita el 3-2-5; Bellingham/Kane referencias. **Mercado: cagey/Under + portería a cero, BTTS-No** vs inferiores. *Control posesional a prueba de contras, gana 1-0/2-0.* ⚠️ 0-GA fue vs grupo flojo → regresa vs élite.
- **Alemania — Nagelsmann (4-2-3-1 flexible).** Posesión **vertical, sobrecarga CENTRAL** (box de medio); FBs no solapan a la vez (Kimmich entra, Raum extremo). Presión alta (PPDA ~8). **MEJOR ATACANDO** (17 goles/5 NL) con defensa mejorada (3 en 5). Personal: **Musiala** (penetración entre líneas), Kimmich estructural. **Mercado: abierto/Over + BTTS, buen balón parado/córner.** *Vertical de sobrecarga central, goles a ambos lados.* ⚠️ Línea alta vulnerable a ritmo élite; situación de portero.
- **Portugal — R. Martínez (4-3-3→3-2-5).** Posesión con fluidez posicional; amplitud de **ambos** (extremos + Nuno Mendes/Cancelo); creación por intercambio. Bloque medio 5-4-1. **Equilibrado, leve MEJOR ATACANDO** (campeón NL 2025). Personal: **Ronaldo** (finisher + imán de balón parado), Vitinha. **Mercado: fuerte balón parado, lean abierto/BTTS; no portería-a-cero fiable.** *Posesión-overload con ventaja individual + ABP.* ⚠️ Minutos de Ronaldo (40); el 3-2-5 deja huecos.
- **Países Bajos — Koeman (4-2-3-1).** Posesión **por el CENTRO** (box-midfield de Jong+Gravenberch); amplitud secundaria (Dumfries/Gakpo). Línea alta + contra-presión. **MEJOR DEFENDIENDO (giro):** mejor defensa del grupo, 6 porterías a cero/10, 1 gol de ABP encajado. Personal: **pivote de Jong/Gravenberch**, Van Dijk. **Mercado: fuerte ABP ambos lados, portería-a-cero/Under, BTTS-No.** *Posesión central ahora sobre porterías a cero + ABP.* ⚠️ Línea alta vs ritmo élite.
- **Bélgica — Rudi Garcia (4-3-3↔4-2-3-1, NUEVO).** Posesión + contra rápida; amplitud **por BANDAS** (Doku 1v1); De Bruyne controla y asiste. Quiere presión alta pero personal verde. **MEJOR ATACANDO (claro) con defensa frágil:** 29 GF / 7 GA pero **encaja 5 en dos partidos vs Gales**; defensa en reconstrucción. Personal: **De Bruyne** (motor + ABP), Doku, Lukaku. **Mercado: abierto/Over + BTTS-Sí (ataca y encaja).** *Ataque front-loaded de bandas con defensa blanda.* ⚠️ ALTA — DT nuevo, defensa sin probar.
- **Croacia — Dalić (4-2-3-1).** Posesión **controlada por el CENTRO** (Modrić ahora de 10); amplitud de apoyo (Perišić). Estructura defensiva excelente, pragmático. **Equilibrado, tira a DEFENDER** (26 GF/4 GA vs grupo flojo); el activo durable es la organización. Personal: **Modrić (40)** + Kovačić; dependiente de veteranos. **Mercado: vs fuertes cagey/Under; vs débiles golea. Lento en transición.** *Control de medio veterano, disciplinado pero lento.* ⚠️ Curva de edad; piernas en transición vs ritmo.
- **Suiza — Yakin (pasó de 3-4-3 a 4-3-3).** Control-posesión metódico; amplitud vía **carrilero invertido** (Aebischer entra al medio). Bloque compacto primero, no presión alta. **MEJOR DEFENDIENDO/organización:** compacidad, ataque funcional no prolífico. Personal: **Aebischer** (define la forma), Xhaka (metrónomo). **Mercado: cagey/low-event, Under; no domina córners vs buenos.** *Compacto control-first con carrilero invertido.* ⚠️ Cambio de forma reciente; flexa por rival.
- **Austria — Rangnick (4-2-3-1 / 4-4-2 presión).** Vertical **por el CENTRO** (extremos entran a sobrecargar); **gegenpressing** de alta intensidad + línea alta. **Equilibrado, la identidad ES la presión** (genera en ambas fases). Personal: **Laimer/Sabitzer** (motores), Alaba (organizador). **Mercado: abierto/Over + BTTS (caos de presión); córner por presión sostenida.** *Gegenpressing vertical por el centro, espacio a la espalda si lo superan.* ⚠️ Edad/fitness de Alaba; depende de intensidad.
- **Noruega — Solbakken (4-4-2/4-3-3).** No posesión; rigidez defensiva → **transición vertical letal**; amplitud por **bandas** (Nusa) pero creación central (Ødegaard entra), Haaland finaliza. Bloque medio compacto. **MEJOR ATACANDO:** 37 goles/8 (máximo UEFA), 8/8. Personal: **Haaland** + **Ødegaard** + Nusa. **Mercado: Over con espacio; equipo de contra → BTTS vs abiertos, portería-a-cero vs débiles; ABP/aéreo Haaland.** *Contragolpeador compacto con finalizadores élite.* ⚠️ Goles inflados por grupo flojo; forma 4-4-2 vs 4-3-3 por rival.
- **Escocia — Clarke (4-1-4-1↔back-3).** Pragmático, no posesión; goles de **medios llegadores + ABP**, no de un 9; amplitud por carrileros (Robertson). Bloque medio/bajo, absorbe y contra. **MEJOR DEFENDIENDO:** organizado, peligro a balón parado; 9 sin resolver. Personal: **McTominay** (gol tardío), McGinn, Robertson. **Mercado: cagey, Under; ABP es edge real (McTominay/aéreo); portería-a-cero vs menores.** *Grinders de ABP y contra, goles desde el medio.* ⚠️ Forma back-4 vs back-3 por rival; delantero sin asentar.
- **Chequia — Koubek (3-4-1-2→back-5, DT desde Dic-25).** **Directo, baja posesión** ("aguanta y golpea"); amplitud por **carrileros + centros** (más centros de UEFA); creación por servicio aéreo a Schick. Back-5 compacto. **Equilibrado/defensivo; el arma es ABP:** **más goles de balón parado de Europa (10).** Personal: **Schick** (9 aéreo+pies), **Souček** (segundas pelotas), Hložek. **Mercado: ABP es el edge claro (córner→gol, headers); córner-over por centros; Under en juego abierto.** *Especialistas de ABP que aguantan y castigan.* ⚠️ DT ~5 meses; forma por rival.
- **Suecia — Potter (3-4-2-1, DT NUEVO Oct-25).** Potter pragmático: posesión + soporte directo; rompió presión por **bandas/pase corto**; final a la pareja de 9. ABP detallada (Georgson). **MEJOR ATACANDO ahora** (playoffs 3-1, 3-2 — defensa la duda con staff nuevo). Personal: **Isak + Gyökeres** (dúo élite, todo se construye para ellos). **Mercado: Over/BTTS (3-1, 3-2); anytime/team-total de los 9; portería-a-cero baja confianza.** *Pragmatismo Potter alrededor de dos 9 letales.* ⚠️ ALTA — DT reciente, sistema nuevo, muestra ínfima.
- **Turquía — Montella (4-2-3-1 fluido).** **Posesión dominante, técnica** (Çalhanoğlu+Kökçü constructores); frente sin 9 fijo rota; amplitud **banda→half-space** (Yıldız izq), no centros. Línea alta, presión NO es su fuerte. **MEJOR ATACANDO (decisivo) pero MUY frágil:** prolífico (10 goles/2 partidos) pero **6-0 vs España**, espacio central a la espalda. Personal: **Güler, Yıldız, Çalhanoğlu (ABP)**. **Mercado: el perfil BTTS+Over más limpio (anota Y encaja); córner/posesión vs débiles; acción 1ª parte.** *Posesión-fluida preciosa adelante, blanda atrás.* ⚠️ Defensa poco fiable ensancha marcadores; riesgo paliza vs élite.
- **Bosnia — Barbarez (4-2-3-1, DT sin experiencia previa).** Físico, **transición rápida**, no posesión lenta; Demirović libera a **Džeko**; servicio al 9. Bloque medio. **Equilibrado/leve DEFENSA sólida** (0.8 GA) que se rompe con fatiga. Personal: **Džeko (40)**, Demirović, Tahirović/Gigović. **Mercado: cagey/grind, partidos tardíos y por penaltis → Under/draw/gol-tardío; Džeko aéreo anytime.** *Grinders de transición con 9 veterano, aguantan y pican tarde.* ⚠️ DT primerizo + Džeko 40 = techo y stamina dudosos.

#### CONMEBOL (4)

- **Uruguay — Bielsa (4-3-3/4-4-2).** Posesión que **no genera ocasiones** (71% pos, 1 remate vs Paraguay); intento vertical por bandas pero salida es el cuello de botella; Valverde lo hace casi todo. Presión alta man-oriented (cara, se desvanece). **MEJOR DEFENDIENDO ahora (inversión):** 7 partidos sin marcar, ataque roto. Personal: **Valverde**, Núñez (errático), Araújo. **Mercado: posesión alta, baja conversión → Under/No-BTTS; córner estéril.** *Dominador estéril en crisis.* ⚠️🔴 ALTA — **motín/crisis** (Suárez crítico, 5 sin ganar) — variable viva.
- **Colombia — Lorenzo (4-2-3-1).** Posesión pragmática; **doble ruta: bandas (Luis Díaz/Arias) + CENTRO (James, 7 asist)**; FBs solapan. Bloque medio, frustra y golpea. **Equilibrado, tira a ATAQUE:** "back four de hierro" + pólvora (5-0, 4-0, 6-3). Personal: **James** (cerebro+ABP), **Luis Díaz** (banda), Davinson. **Mercado: el más Over/BTTS del grupo (puede golear); fuerte ABP; bloque medio filtra.** *Atacante de doble ruta: bandas + cerebro de James.* 
- **Ecuador — Beccacece (back-3↔back-4).** **NO posesión, pragmático/directo**; ataca de contra y ABP; amplitud situacional; carga creativa en Páez (18a). **Presión alta agresiva** sobre bloque compacto. **DEFENDER, ROTUNDO:** **5 goles encajados en 18, 13 porterías a cero** (la más tacaña de CONMEBOL); ataque es la debilidad. Personal: **Caicedo**, Hincapié+Pacho (CBs élite), Páez. **Mercado: el Under/No-BTTS/portería-a-cero más fuerte del grupo; ABP/penal micro-Over.** *Fortaleza de presión: gana 1-0, defensa letal, ataque romo.* 
- **Paraguay — Alfaro (4-2-3-1/4-4-2).** **Directo**, identidad explícita: **ataca por BANDAS + ABP** (Almirón izq, Sosa der → centros al 9). Bloque medio-bajo, compacto. **MEJOR DEFENDIENDO:** mejor defensa (~10 GA) pero **solo 14 goles/18 (el más bajo)**. La transición es su arma. Personal: **Gustavo Gómez** (CB, aéreo/ABP), Almirón. **Mercado: Under/low-scoring fuerte; ABP+aéreo es el ángulo; córner por identidad de centro.** *Dark horse disciplinado: bloque + centros + headers, letal de contra.* ⚠️ Pragmatismo divisivo (crítica de Chilavert).

#### CONCACAF (6)

- **México — Aguirre (4-3-3).** Posesión, **construye desde atrás** (estrés vs presión); amplitud por **BANDAS** (Lozano der, Quiñones), Vega crea; Jiménez referencia. Bloque medio. **Tira a ATAQUE/equilibrado (nivel inflado por rival):** doblete CONCACAF 2025 pero **0-4 en casa vs Colombia**. Personal: Edson Álvarez (pivote), Jiménez, Lozano. **Mercado: domina posesión/córner vs menores; salida-desde-atrás explotable a presión → rivales generan; BTTS moderado.** *4-3-3 de salida, ritmo de banda, dominante regional pero press-vulnerable.* ⚠️ Currículum solo CONCACAF; 0-4 vs Colombia es la alerta.
- **Estados Unidos — Pochettino (3-2-5 construcción / 4-4-2 bloque).** Posesión pragmática "sufrir"; amplitud por **BANDAS** (Weah der, Pulisic half-space izq); crea Pulisic/Tillman. Presión menos efectiva que antes, más bloque medio. **MEJOR ATACANDO; defensa frágil:** 7 encajados en 2 amistosos, CBs lentos. Personal: **Pulisic**, Adams (ancla), Balogun (en forma). **Mercado: domina córner vs menores; frágil atrás → BTTS/Over sube vs calidad; cagey cuando "sufre".** *Anfitrión posesión-capaz pero frágil atrás, vive de calidad individual.* ⚠️ XI titular WC poco rodado (Gold Cup con suplentes).
- **Canadá — Marsch (4-4-2 presión alta).** **Directo/vertical**, no paciente; amplitud por **BANDAS** (Davies, Ahmed, Buchanan); doble pivote Eustáquio-Koné. **"Maplepressing"** alto. **MEJOR DEFENDIENDO:** solo **2 goles de juego abierto en 7** (el problema es marcar); bloque-presión fiable. Personal: **Davies (⚠️LCA marzo-25, dudoso)**, Jonathan David. **Mercado: low-scoring/Under vs bloques; goles de caos por presión; córner situacional.** *Presión-transición que defiende bien pero no crea vs bloque.* ⚠️ Davies fitness; romo vs bloque bajo.
- **Panamá — Christiansen (3-4-2-1↔5-4-1).** Bi-modal: posicional vs inferiores / compacto-contra vs superiores; amplitud por **CARRILEROS** (Murillo, Davis); Carrasquilla tempo. Bloque medio/5-4-1. **Equilibrado, edge DEFENSIVO:** invicto 10 quali, **6 porterías a cero**. Personal: Carrasquilla (hub), Godoy, carrileros. **Mercado: el más maduro de los menores; portería-a-cero/Under vs fuertes; córner vs débiles.** *Pragmático de dos velocidades.* 
- **Curaçao — Advocaat (4-3-3, volvió ~1 mes pre-WC).** **No controla posesión por diseño**; transiciones, duelos, intensidad; amplitud por **FBs + hermanos Bacuna**; Chong con balón. Bloque medio/bajo disciplinado. **DEFENSA-base, ataque también rindió:** **28 GF / 5 GA en 10 invicto.** Personal: L./J. Bacuna, **Chong**, Janga (goleador). **Mercado: low-block, tacaño → Under/portería-a-cero-en-contra como underdog; cede posesión/córner.** *Underdog neerlando-caribeño que defiende en bloque y pica de contra.* ⚠️ Churn de DT; techo de plantilla debutante.
- **Haití — Migné (4-4-2).** **Directo**, intenso/físico, vertical; **pace por BANDAS**; creación de velocidad wide, no control. Off-ball agresivo pero **consistencia defensiva es la duda**. **MEJOR ATACANDO (de contra); defensa más floja:** amenaza de contra, frágil a presión. Personal: **Nazon** (goleador), Isidor (Sunderland), Bellegarde; plantilla diáspora. **Mercado: contra-dependiente, encaja → BTTS/Over-en-contra vs mejores; end-to-end.** *Diáspora rápida y directa, ataque por delante de la defensa.* ⚠️ Defensa se desborda vs posesión/presión.

#### CAF (10)

- **Marruecos — 🔴 Ouahbi (4-1-4-1, DT desde 5-mar-26).** ⚠️ **CAMBIO DE DT:** Regragui depuesto tras perder la final de AFCON 2025; **Ouahbi** (ganó el Mundial Sub-20 2025) intenta un **giro más ofensivo/posesión** vs el bloque pragmático de Regragui — pero **solo ~3 amistosos** (Ecuador 1-1, Paraguay 2-1, Burundi 5-0), **sin asentar**. ADN base heredado: bloque medio-bajo estrecho + amplitud banda-invertida (Brahim entra, **Hakimi** overload der). Personal: **Hakimi (⚠️muscular)**, Amrabat, Brahim, **El Kaabi/Rahimi (En-Nesyri FUERA)**. **Mercado: NO modelar sobre la era Regragui (régimen nuevo, alta varianza); el "dominio territorial" era de Regragui vs rivales débiles, no de Ouahbi. Cautela en totales/team-style.** *Régimen de 3 meses sin probar que intenta ser más atacante que el equipo que perdió la final de AFCON.* ⚠️🔴 ALTA — <3mo, 3 amistosos; legado WC22/AFCON NO predictivo (re-baselinar).
- **Senegal — Pape Thiaw (4-3-3→back-3 build).** Build con back-3, **vertical al recuperar**; amplitud **por BANDAS** (aísla pace), 8s de tercer hombre; der preferida. Olas de presión alta tras pérdida; back-5 para cerrar. **Equilibrado, mejor en TRANSICIÓN que en posesión** (campeón AFCON 2025, portería a cero en final). Personal: **Mané, Jackson, I. Ndiaye, Gueye×2**, É. Mendy. **Mercado: peligro de ABP (artillería al 2º palo); pace → goles en abierto; cagey vs bloque bajo.** *Pace-y-potencia de transición con martillo de ABP.* ⚠️ Rol/minutos de Mané; pareja de CBs (Koulibaly ya no automático).
- **Egipto — Hossam Hassan (4-2-3-1, vs rivales 3-4-1-2).** **Directo/transición, NO posesión**; "organización primero, suelta a Salah/Marmoush"; amplitud por **calidad individual (Salah der)**, FBs cautos. Bloque compacto estrecho, defiende largo. **DEFENDER, claro:** **7 porterías a cero, 2 goles encajados en 10.** Salah-dependiente. Personal: **Salah** (RW/ABP/penales), **Marmoush**. **Mercado: portería-a-cero/Under/low-conceded fuerte; cagey, BTTS-No; Salah anytime/ABP.** *Counterpunchers de bloque alrededor de soltar a Salah, gana 1-0.* ⚠️ 3-4-1-2 por rival; carga de Salah.
- **Argelia — Petković (4-3-3→4-2-3-1/3-5-2).** **Atacante, combinativo**; amplitud **por BANDAS** (Mahrez der, Atal); Bennacer controla. Presión alta (pero la **superaron físicamente** Nigeria). **MEJOR ATACANDO:** ~50 goles/20, Amoura 10 en quali; defensa el lado más flojo. Personal: **Mahrez** (creador), **Amoura** (pace), Gouiri, Bennacer. **Mercado: abierto/Over vs menores; Mahrez/Amoura scorer; BTTS más plausible que Egipto/Túnez.** *Presión de bandas liderada por Mahrez + pace de Amoura; divertido pero "bullyable".* ⚠️ QF AFCON fuera (físico/aéreo); portero sin asentar.
- **Túnez — 🔴 Lamouchi (4-2-3-1, DT desde Ene-26).** ⚠️ **CAMBIO DE DT:** Trabelsi clasificó **sin encajar gol** y fue cesado tras AFCON R16; Lamouchi favorece disciplina defensiva, presión en olas, Skhiri/Laïdouni de doble pivote. **Pragmático, defensa-primero**, ataque el punto débil. **DEFENDER, rotundo.** Personal: **Skhiri** (pivote), Laïdouni, Msakni (verificar). **Mercado: el Under/portería-a-cero/BTTS-No más fuerte de los cinco; cagey ambos lados; Grupo F duro (NED/JPN/SWE).** *Unidad hermética de bajo-evento con ataque romo.* ⚠️ ALTA — DT nuevo, datos era-Trabelsi parcialmente caducos.
- **Costa de Marfil — Faé (4-3-3).** Posesión-capaz pero **directa por BANDAS** (Amad creador wide, 10 ocasiones AFCON); Kessié/Fofana combinan. Bloque compacto excelente. **DEFENDER, más fiable:** **0 goles encajados en quali** (pero les costó marcar). Personal: **Haller** (9), Kessié+Fofana, **Amad**, Pépé (recuperado). **Mercado: low-conceding/portería-a-cero, cagey; córner por presión wide; BTTS-No cuando controla.** *Dark horse de bandas defensivamente élite, se apaga vs bloque bajo.* ⚠️ Rol de Pépé; verificar el "0 encajados".
- **Ghana — 🔴 Queiroz (4-2-3-1/3-4-2-1, DT desde Abr-26).** ⚠️ **CAMBIO DE DT:** Queiroz reemplazó a Addo (que clasificó); identidad = **compresión defensiva, área poblada, presión a banda**, no posesión. **DEFENSA-primero por diseño, PERO defensa heredada porosa** (~2 meses para arreglarla) → ejecución de alto riesgo. Personal: Djiku, Mumin, Seidu (perfiles out-of-possession); ataque de individualidades. **Mercado: low-block/Under vs Grupo L (ING/CRO); pero riesgo de defensa no-gelada → BTTS/Over puede spike. No asumir ABP.** *Pragmático defensivo en plantilla porosa, runway corto.* ⚠️🔴 LA MÁS IMPREDECIBLE — DT nuevo + defensa a reconstruir.
- **Cabo Verde — Bubista (4-2-3-1, debut WC).** **Directo/transición**, no posesión; **pace por BANDAS + contras + ABP**; cede balón y golpea. Presión selectiva → compacto que fuerza a banda. **DEFENSA-led:** clasificó por encima de Camerún, pocas concesiones, porterías a cero clave. Personal: **Ryan Mendes** (capitán, goleador, **córners+FK**), Monteiro (ABP alt), Teixeira. **Mercado: ABP es arma nombrada → mercados ABP/portería-a-cero; low-event/Under, cede córner; BTTS-No sentado.** *El minnow modelo: transición de bandas + ABP peligroso.* ⚠️ Profundidad/techo de debutante.
- **Sudáfrica — Broos (4-2-3-1/4-3-3).** Más posesión (~60%) que el resto CAF pero **penetración por BANDAS** (Mofokeng+Appollis, Pirates); Mokoena dicta. Bloque medio organizado, transición. **DEFENSA/estructura el activo; ATAQUE la debilidad reconocida** (Broos "busca gol"). Personal: **Mokoena** (motor), Foster (9), **Mofokeng** (joven banda). **Mercado: posesión/córner vs débiles, **low-scoring/Under** por problema de gol; team-total-Under; BTTS-No defendiendo ventaja.** *Estructurado posesión-leaning de bandas que controla pero no concreta.* ⚠️ Etiqueta de formación inconsistente (4-2-3-1 vs 4-3-3).
- **RD Congo — Desabre (4-2-3-1, repechaje Mar-26).** Pragmático, **directo/transición**; amplitud más **CENTRAL/controlada** (FBs incl. Wan-Bissaka cautos), penetración por verticalidad rápida. Bloque medio disciplinado, presión selectiva. **DEFENSA-led:** difícil de romper, amenaza de contra. Personal: **Mbemba** (capitán, ancla), **Wissa** (forma-dependiente), Bakambu. **Mercado: low-event/Under, contra-dependiente; portería-a-cero; BTTS-No protegiendo; ABP poco documentado.** *Bloque compacto difícil de romper anclado por Mbemba, pica por Wissa/Bakambu.* ⚠️ Forma de Wissa; "amplitud" teórica (FBs frenados).

#### AFC (9)

- **Japón — Moriyasu (3-4-2-1 fluido→4-3-3).** Circulación controlada, switches; **amplitud POR BANDAS** (aísla 1v1: Mitoma izq, Kubo der), Kamada enlaza. Presión organizada que atrapa a banda. **MEJOR ATACANDO:** calidad de extremos clase mundial; "camaleón" con marcha de bloque bajo vs élite. Personal: **Mitoma, Kubo, Kamada, Ito**. **Mercado: domina posesión/córner vs menores; game-state-dependiente (abierto vs débiles, cagey vs gigantes); Over en matchup favorable.** *Aislamiento de bandas con creadores élite y marcha de bloque bajo en reserva.* ⚠️ Forma por rival, no fijo 3-4-2-1.
- **Corea del Sur — Hong Myung-bo (3-4-2-1, bajo crítica).** Liderado por estrellas, no por sistema; **Son + Lee Kang-in** combinan central y derivan; depende de carrileros para amplitud. **MEJOR ATACANDO por talento, FRÁGIL:** back-3 "expone vulnerabilidades defensivas repetidas". Personal: **Son (34, MLS)**, **Lee Kang-in**, Kim Min-jae. **Mercado: output errático por dependencia de 2; blandura defensiva → BTTS/goles-en-contra vs calidad; ABP presente pero lapsus atrás.** *Top-heavy dependiente de estrellas con back-3 disputado y permeable.* ⚠️ ALTA — puede volver a back-4; forma/edad de Son.
- **Irán — Ghalenoei (4-2-3-1/4-4-2).** No ávido de balón; **servicio DIRECTO a los delanteros**, segundas pelotas; amplitud de wide forwards/FBs pero ruta vertical. Bloque compacto, presión situacional. **MEJOR DEFENDIENDO:** atricional, organización + ABP + porterías a cero. Personal: **Taremi** (foco), Ezatolahi; ⚠️ **Azmoun vetado** → Taremi-dependiente. **Mercado: low-scoring/Under y portería-a-cero fuerte; ABP es edge; no BTTS protegiendo.** *Bloque compacto atricional que muele 1-0.* ⚠️ Ausencia de Azmoun estrecha el ataque; ruido geopolítico.
- **Australia — Popovic (3-4-2-1/back-5).** No posesión; organización, físico, **ataques wide por CARRILEROS** (Bos izq, Irankunda der); creatividad escasa. Bloque bajo/medio de cinco, transiciones rápidas. **MEJOR DEFENDIENDO:** organización + **dominio aéreo/ABP** (Souttar, Burgess); ataque la limitación. Personal: **Souttar** (monstruo aéreo/ABP), Irvine, Irankunda, Boyle. **Mercado: goles de ABP es el edge claro (Souttar aéreo); córner/header; low-scoring/Under vs fuertes.** *Grinder físico de back-5 movido por ABP con pace de contra.* ⚠️ Baja — DT/identidad estables; duda es output vs élite.
- **Arabia Saudí — 🔴 Donis (DT desde Abr-26, NO Renard).** ⚠️ **CRISIS DE DT:** Renard cesado (0-4 vs Egipto); Donis llegó como **estabilizador, no reinventor**, ~2 meses pre-torneo. **Sin identidad de posesión establecida; defensa fue el fallo bajo Renard.** **Llamada retenida — inestable** (si forzado: defensa floja, sin ataque claro). Personal: en flujo; Al-Dawsari el marquee (verificar). **Mercado: ALTA incertidumbre = cautela; inestabilidad defensiva → BTTS/goles-en-contra hasta ver patrón; Grupo H brutal (ESP/URU/CPV). NO modelar sobre Renard.** *Equipo en crisis de DT a mitad de reconstrucción.* ⚠️🔴 MUY ALTA — sin datos de torneo, churn de plantilla.
- **Catar — Lopetegui (4-2-3-1, DT desde May-25).** Posesión/control proactivo estilo LaLiga; **amplitud híbrida no pura-banda** (Afif arranca izq pero **invierte al CENTRO** como playmaker — la creación va por él). Compacto zonal pero ejecución floja. **MEJOR ATACANDO (claro):** Afif 11 asist, Almoez 12 goles en quali; defensa el problema crónico. Personal: **Afif** (creador invertido), Almoez Ali. **Mercado: ataque real + defensa leaky → goles/BTTS, no cagey vs calidad; domina posesión vs menores.** *Ataque con sabor a posesión alrededor de un creador, minado por defensa blanda.* ⚠️ ALTA en defensa — Lopetegui aún probando; back line sin probar vs élite.
- **Uzbekistán — 🔴 Cannavaro (3-4-3→5-3-2, debut WC).** ⚠️ DT desde Oct-25 (clasificó Kapadze). **Directo, NO posesión**: 3-4-3 de bloque bajo que **depende de centros por BANDAS + ABP** al 9; balones largos a Shomurodov; físico. Low-block 5-3-2, defensa "el cimiento". **MEJOR DEFENDIENDO (claro):** 1 derrota en 15 quali, Khusanov (Man City) ancla. Personal: **Shomurodov** (foco), **Khusanov** (CB), Sergeev. **Mercado: low-scoring/Under, cagey; aéreo/ABP en ataque; cede posesión vs Grupo K (POR/COL).** *Bloque bajo físico drilado por Cannavaro que contra y centra.* ⚠️ MEDIA — Cannavaro pocos partidos; techo ofensivo sin probar.
- **Jordania — 🔴 Sellami (4-5-1/3-4-3, NO Ammouta).** ⚠️ Ammouta llevó la **final de Asian Cup**; Sellami clasificó al WC. Reactivo/directo, no posesión; defiende profundo → **suelta a Al-Tamari de contra**; Al-Naimat target; creación **por transición**. Bloque compacto profundo. **MEJOR DEFENDIENDO con transición élite.** Personal: **Al-Naimat** (9), **Mousa Al-Tamari** ("el Messi jordano", la navaja). **Mercado: ABP es arma real; cagey/low-event con el bloque pero edge de contra+ABP; Grupo J (ARG/ALG/AUT) → bloque bajo, Under.** *Counterpuncher drilado con una salida élite (Al-Tamari) + ABP.* ⚠️ BAJA-MEDIA — menos probado que la versión de Ammouta.
- **Irak — 🔴 Graham Arnold (4-4-2 bloque, repechaje Mar-26).** ⚠️ Arnold llegó tarde, armó plantilla días antes del playoff. **Reactivo/transición, dos bancos de cuatro**; Zidane Iqbal de pivote creativo a dos 9s; no posesión. Bloque disciplinado (aguantó 9' de añadido vs Bolivia). **MEJOR DEFENDIENDO:** bloque + goles de ABP/transición. Personal: **Aymen Hussein, Al-Hamadi** (Luton), Zidane Iqbal, Al-Ammari (ABP). **Mercado: ABP es edge documentado (header de Al-Hamadi); low-block → Under/cagey; goles de balón parado y contra; Grupo I brutal (FRA/SEN/NOR).** *Dos bancos de cuatro que gana por ABP y potencia de contra.* ⚠️ MEDIA-ALTA — Arnold heredó tarde, sistema sin datos.

#### OFC (1)

- **Nueva Zelanda — Bazeley (4-3-3/4-2-3-1).** **Directo/físico**; vertical a Wood, **uso intenso de BANDAS → centros**, caza córners/FK; amplitud genuina de banda (Cacace, wingers a Wood). Bloque medio compacto, presión selectiva. **DEFENSA-primero con ataque aéreo élite:** "juego aéreo de los más formidables del torneo"; gana por estructura+ABP, no posesión. Personal: **Chris Wood** (capitán, Forest, foco aéreo), Cacace, Stamenic. **Mercado: amenaza aérea/ABP fuerte + volumen de centros → córner-friendly; Under/low-scoring salvo que Wood convierta; BTTS por matchup.** *Directo, físico, de ABP-y-Wood, gana en el aire.* ⚠️ MEDIA — splits ABP/xG escasos (calidad OFC).

### 6.6 — Corroboración estadística (API-Football, SOLO partidos del DT actual)

> Promedios sobre los últimos ≤20 partidos **con el entrenador actual** (filtrado por fecha de
> nombramiento). Fuente: API-Football `/fixtures/statistics` (xG no disponible en internacionales).
> Genera `data/cache/tsp/api_team_stats_by_coach.json` vía `scripts/spike/tsp/41_team_stats_by_coach.py`.
> **Pos%** = posesión · **Pase%** = precisión de pase · **Rem F/C** = remates a favor/en contra ·
> **SOT F/C** = remates **a puerta** a favor/en contra (mejor proxy de calidad de finalización que
> remates totales) · **Córn F/C** = córners a favor/en contra · **Faltas** = faltas cometidas/partido
> · **TA/p** = tarjetas amarillas/partido · **GF/GA** = goles/partido a favor/en contra. ✓ = el dato
> confirma §6.5; ⚠ = lo matiza. Muestra chica (n<5) = baja confianza.
>
> ⚠️ **Disciplina — fiabilidad del dato (importante para mercado de tarjetas):** **Faltas** está
> presente en TODOS los partidos (fiable). **TA/p (amarillas)** la API solo la reporta en partidos
> **competitivos** (en amistosos menores devuelve `null`) → n-efectivo < n, pero como el WC es
> competitivo es el sub-conjunto **relevante**. **Tarjetas rojas: NO se surfacean** — la API las
> devuelve `null` casi siempre (rojas/partido salía inflado como artefacto de promediar solo los
> partidos con roja); no es un dato fiable de esta fuente. Para cards, cruzar §6.6 con el árbitro
> probable (tabla de árbitros) — el árbitro es co-driver del total de tarjetas.

| Equipo (DT · n) | Pos% | Pase% | Rem F/C | SOT F/C | Córn F/C | Faltas | TA/p | GF/GA | Lectura |
|---|---|---|---|---|---|---|---|---|---|
| **UEFA** | | | | | | | | | |
| Francia (Deschamps · 20) | 58.9 | 88.8 | 17.5/8.6 | 6.2/3.2 | 6.1/3.5 | 10.8 | 2.0 | 2.1/1.1 | ✓ contra de bloque medio; eficiente, disciplina media (detalle §6.2) |
| España (de la Fuente · 20) | 63.2 | 89.7 | 19.9/8.2 | **7.7**/2.6 | 6.8/3.2 | 11.2 | 1.5 | **2.6**/0.8 | ✓✓ SOT 7.7 el más alto de las 48; limpia (detalle §6.3) |
| Inglaterra (Tuchel · 12) | **70.3** | 91.7 | 17.4/**5.9** | 6.8/**1.7** | **7.6/1.9** | 9.8 | **1.0** | 2.2/**0.4** | ✓✓ posesión-dominio + defensa élite (SOT-contra 1.7) + pocas TA |
| Alemania (Nagelsmann · 20) | 64.5 | 89.4 | 17.5/8.7 | 6.8/2.9 | 6.2/3.8 | 12.8 | 1.7 | **2.6**/0.9 | ✓ ataca mucho, defensa ok |
| Portugal (Martínez · 20) | 65.0 | 90.8 | 18.2/9.2 | 6.0/3.4 | 6.5/3.3 | 10.6 | 1.8 | 2.2/0.8 | ✓ posesión-overload, equilibrado |
| Países Bajos (Koeman · 20) | 59.5 | 88.5 | 14.9/9.2 | 5.2/2.9 | 5.9/3.3 | 10.3 | 1.2 | **2.5**/0.9 | ⚠ marca más de lo que el read "portería-a-cero" sugiere |
| Bélgica (Garcia · 12) | 64.1 | 87.2 | 19.2/7.2 | 7.2/2.9 | **8.8**/2.8 | 11.5 | 1.2 | **3.2**/1.1 | ✓ ataque front-loaded; defensa no tan sangrante en muestra |
| Croacia (Dalić · 20) | 58.2 | 88.7 | 17.4/9.8 | 6.8/3.5 | 6.2/4.2 | 9.7 | 1.7 | 2.1/1.0 | ✓ control, vs grupo flojo golea |
| Suiza (Yakin · 20) | 58.3 | 87.8 | 12.2/9.8 | 4.7/3.5 | 4.9/4.1 | 10.8 | 1.6 | 2.0/1.2 | ✓ low-event, ataque funcional |
| Austria (Rangnick · 20) | 62.6 | 84.7 | 14.9/8.6 | 5.9/2.0 | 4.7/3.1 | 11.7 | 1.6 | 2.4/0.8 | ✓ intenso, output alto |
| Noruega (Solbakken · 20) | 55.4 | 87.7 | 15.8/8.7 | 5.9/2.9 | 5.3/2.5 | 9.2 | 1.1 | **3.0**/0.9 | ✓ finalizadores élite (3 GF); pocas faltas/TA |
| Escocia (Clarke · 20) | **50.0** | 83.8 | 10.8/**14.4** | 4.2/4.0 | 4.5/**5.4** | 11.6 | 1.5 | 1.5/1.2 | ✓ dominado, absorbe y contra; bajo de gol |
| Suecia (Potter · **4**) | 41.8 | 80.5 | 9.0/12.8 | 3.5/5.2 | 3.5/7.2 | 12.2 | 2.2 | 2.0/2.0 | ⚠ n=4; superados pero los 9 marcan (BTTS) |
| Turquía (Montella · 18) | 55.8 | 84.4 | 15.4/11.1 | 4.9/3.7 | 5.7/3.8 | 10.6 | **2.6** | 2.0/1.2 | ✓ atacante Y permeable (BTTS+Over); **TA 2.6 la más alta de las 48** |
| Bosnia (Barbarez · 17) | 43.9 | 76.6 | 10.8/**13.6** | 3.4/4.4 | 3.1/4.8 | **14.8** | 2.3 | 1.2/1.6 | ✓ no-posesión, superados; **muy faltosa (14.8) + TA 2.3** |
| Chequia (Koubek) | — | — | — | — | — | — | — | — | *sin partidos con stats bajo DT nuevo — solo cualitativo* |
| **CONMEBOL** | | | | | | | | | |
| Argentina (Scaloni · 20) | 65.2 | 89.0 | 12.2/6.2 | 5.1/2.1 | 4.4/2.6 | 10.1 | **1.3** | 2.2/**0.5** | ✓ control eficiente; muy disciplinada (detalle §6.1) |
| Brasil (Ancelotti · 10) | 59.0 | 88.0 | 14.1/9.8 | 5.2/3.6 | 4.7/3.5 | 12.7 | 1.4 | 2.1/0.9 | ✓ n=10; equilibrio, faltas altas (detalle §6.4) |
| Uruguay (Bielsa · 20) | 54.6 | 82.5 | **9.8/12.1** | **2.6**/3.6 | 4.7/4.3 | 11.1 | 2.3 | **0.8/0.8** | ✓✓ crisis: ataque roto (SOT 2.6), superados; TA 2.3 |
| Colombia (Lorenzo · 20) | 56.2 | 85.4 | 12.7/9.9 | 5.2/3.3 | 4.2/3.5 | **13.1** | 1.7 | 1.9/1.1 | ✓ equilibrado con pólvora; faltosa (13.1) |
| Ecuador (Beccacece · 19) | 55.2 | 84.6 | 11.1/9.1 | 4.1/2.8 | 4.2/3.6 | 12.7 | 1.6 | **0.9/0.4** | ✓✓ defensa élite (0.4 GA), ataque romo (0.9 GF) |
| Paraguay (Alfaro · 17) | **36.6** | **71.6** | 9.9/9.2 | 3.7/3.2 | 3.9/4.4 | 12.2 | 2.2 | 1.1/0.9 | ✓✓ el más directo (36% pos), low-scoring; TA 2.2 |
| **CONCACAF** | | | | | | | | | |
| México (Aguirre · 20) | 56.9 | 86.2 | 11.8/7.5 | 4.5/2.5 | 4.5/3.1 | 12.4 | 1.9 | 1.2/0.7 | ✓ controla, pero bajo de gol vs su fama |
| EE.UU. (Pochettino · 20) | 56.8 | 86.5 | 10.9/8.8 | 4.5/3.8 | 4.5/4.8 | 10.4 | 1.7 | 1.8/**1.4** | ✓ posesión pero permeable (1.4 GA) |
| Canadá (Marsch · 20) | 50.5 | 79.5 | 11.6/6.5 | 4.5/2.5 | 5.5/2.6 | **14.0** | 2.2 | 1.6/0.7 | ✓ no-posesión, defiende bien; **faltosa (14.0) + TA 2.2** |
| Panamá (Christiansen · 20) | 53.5 | 83.2 | 12.8/10.8 | 5.0/4.0 | 4.1/3.6 | 11.4 | 1.6 | 1.8/1.3 | ✓ equilibrado, sólido |
| Curaçao (Advocaat · 20) | 55.2 | 79.2 | 13.8/10.7 | 5.4/3.8 | 4.4/3.6 | **14.1** | 1.6 | 2.3/0.8 | ✓ tacaño atrás, pica de contra; **faltosa (14.1)** |
| Haití (Migné · 19) | 57.2 | 83.3 | 16.3/9.6 | 5.8/3.6 | 5.4/2.8 | 13.6 | 1.5 | **2.7**/1.2 | ⚠ más vistoso/goleador de lo que "leaky" sugiere (vs OFC/CONCACAF menores) |
| **CAF** | | | | | | | | | |
| Marruecos (Ouahbi · **2**) | 57.5 | 88.5 | 9.0/9.5 | 3.5/4.5 | 1.5/2.0 | 10.0 | 2.0 | 1.5/1.0 | ⚠ n=2 (solo Ouahbi): igualado/superado en remates — NO el dominio territorial de la era Regragui |
| Senegal (Thiaw · 14) | 58.4 | 87.5 | 13.4/8.0 | 6.4/2.8 | 5.9/4.3 | **14.5** | 1.6 | 2.3/0.8 | ✓ defensa fuerte; **muy faltosa (14.5) pero TA solo 1.6 → físico "limpio"** |
| Egipto (H. Hassan · 12) | **40.8** | 80.9 | 10.4/**13.4** | 4.1/3.2 | 3.0/5.7 | 11.6 | 1.7 | 1.4/**0.4** | ✓✓ directo/no-posesión, bloque absorbe (0.4 GA pese a superado) |
| Argelia (Petković · 11) | 50.1 | 85.1 | 9.9/9.5 | 4.0/3.4 | 5.1/4.1 | **14.6** | 2.1 | 1.8/1.0 | ⚠ menos dominante de lo que "atacante" sugiere; **faltosa (14.6) + TA 2.1** |
| Costa de Marfil (Faé · 16) | 54.9 | 87.8 | 15.5/9.0 | 3.9/2.5 | 6.1/3.5 | **14.4** | 1.3 | 2.0/0.8 | ✓ defensa sólida; **faltosa (14.4) pero TA solo 1.3 → físico "limpio"** |
| Ghana (Queiroz · **1**) | 41.0 | 88.0 | 7.0/16.0 | 3.0/8.0 | 3.0/9.0 | 9.0 | 1.0 | **0.0/2.0** | ⚠ n=1; superado total (datos mínimos) |
| Cabo Verde (Bubista · 11) | 50.8 | 79.6 | 10.4/**14.4** | 3.7/3.7 | 3.8/4.8 | 13.7 | 1.5 | 1.6/1.3 | ✓ underdog, superado pero pica |
| Sudáfrica (Broos · 19) | 60.1 | 84.9 | 13.5/7.0 | 4.8/2.5 | 4.9/2.9 | 12.4 | 1.8 | 1.6/0.9 | ✓✓ posesión alta + problema de gol (1.6 GF) |
| RD Congo (Desabre · 16) | **45.7** | 79.3 | 13.6/8.2 | 3.8/2.1 | 4.8/3.5 | 12.5 | 1.1 | 1.1/0.6 | ✓ no-posesión, sólido atrás |
| Túnez (Lamouchi) | — | — | — | — | — | — | — | — | *sin partidos con stats bajo DT nuevo — solo cualitativo* |
| **AFC** | | | | | | | | | |
| Japón (Moriyasu · 20) | 57.9 | 86.3 | 12.6/6.8 | 5.5/**1.7** | 5.2/2.0 | 12.5 | **0.9** | **2.4**/0.5 | ✓ ataca, domina, defensa élite (SOT-contra 1.7); **TA 0.9 la más baja de las 48** |
| Corea Sur (Hong · 19) | 63.3 | 87.2 | 12.0/8.6 | 4.6/2.7 | 5.7/2.7 | 9.9 | 1.2 | 1.8/1.0 | ✓ posesión, pero defensa permeable a su talento |
| Irán (Ghalenoei · 20) | 54.9 | 80.2 | 15.6/9.1 | 5.3/3.0 | 4.5/3.0 | 11.5 | 1.7 | 2.0/0.9 | ⚠ atacan más de lo que "defensa-primero" sugiere |
| Australia (Popovic · 17) | **45.2** | 80.6 | 8.6/10.1 | 3.1/3.5 | 3.5/4.6 | **8.5** | 1.5 | 1.3/0.9 | ✓ no-posesión, defensivo, bajo de gol; **menos faltosa de las 48 (8.5)** |
| Arabia Saudí (Donis · **1**) | 58.0 | 83.0 | 12.0/11.0 | 2.0/6.0 | 2.0/2.0 | 11.0 | 1.0 | 1.0/2.0 | ⚠ n=1; inestable (datos mínimos) |
| Catar (Lopetegui · 7) | 51.4 | 84.3 | **6.7/11.9** | **2.3**/4.1 | 3.1/4.6 | 10.4 | 1.8 | **0.7/1.6** | ⚠⚠ **MATIZA: bajo Lopetegui los SUPERAN y no marcan (SOT 2.3)** — el "mejor atacando" no se sostiene |
| Uzbekistán (Cannavaro · **2**) | 43.0 | 77.0 | 7.0/13.0 | 3.0/4.0 | 3.0/4.0 | 9.5 | 1.0 | 1.5/1.0 | ⚠ n=2; bloque bajo confirmado |
| Jordania (Sellami · 15) | **35.7** | 77.0 | 12.1/10.6 | 4.1/3.9 | 4.6/4.6 | 11.4 | 1.1 | 1.5/0.9 | ✓✓ el menos posesión (36%), reactivo/contra |
| Irak (Arnold · 6) | 44.2 | 75.7 | 7.0/**12.8** | 2.7/3.3 | 3.0/5.0 | 9.3 | 1.3 | 0.8/0.7 | ✓ bloque defensivo, superado, low-scoring |
| **OFC** | | | | | | | | | |
| Nueva Zelanda (Bazeley · 15) | **46.1** | 80.8 | 9.0/**15.3** | 2.9/**5.6** | 4.4/5.4 | 11.4 | 1.5 | **0.6/1.6** | ✓✓ defensa-primero, superado por técnicos (SOT-contra 5.6), muy bajo de gol |

**Lecturas que el dato MATIZA (importante):**
- **🔴 Marruecos (caso ejemplar del filtro por DT):** la web daba Regragui (62% pos, dominio territorial 6.8-1.6 córners, GA 0.3). Pero **Regragui fue depuesto (mar-26); el DT actual es Ouahbi**. Bajo Ouahbi (n=2): 57.5% pos, **los superan 9-9.5 en remates, córners 1.5-2.0** → NO es el juggernaut de la era anterior. Régimen de 3 meses, legado WC22/AFCON no predictivo. Sin el filtro por DT, el sistema habría modelado al equipo equivocado.
- **Catar:** el read web ("mejor atacando") es de antes; **bajo Lopetegui (n=7) los superan 6.7-11.9 en remates y marcan 0.7/p** → NO atacan en su periodo. El filtro por DT actual lo destapa.
- **Irán / Argelia:** "defensa-primero" / "atacante" matizados — Irán remata más (15.6) de lo que su etiqueta sugiere; Argelia menos dominante (9.9 remates).
- **Países Bajos / Haití:** marcan más de lo que su read sugiere (NED 2.5 GF; Haití 2.7 vs menores).
- **Confirmaciones fuertes (✓✓):** Inglaterra, Senegal, Egipto, Ecuador, Paraguay, Jordania, Japón, Sudáfrica, Uruguay (crisis), Nueva Zelanda.

**Disciplina — lectura para mercado de tarjetas (el mercado más blando):**

> Recordatorio §1: la **formación es inerte** para tarjetas; el driver es el historial del equipo +
> el árbitro. **Faltas ≠ tarjetas** — el ratio falta→tarjeta varía mucho por equipo y por confederación.
> La señal de cards es **TA/p (la amonestación real)**, con faltas como contexto.

- **Faltas/p más altas (físicos):** Bosnia 14.8 · Argelia 14.6 · Senegal 14.5 · Costa de Marfil 14.4 ·
  Curaçao 14.1 · Canadá 14.0 · Cabo Verde 13.7 · Haití 13.6 · Colombia 13.1.
- **Faltas/p más bajas:** Australia **8.5** · Noruega 9.2 · Irak 9.3 · Uzbekistán 9.5 · Croacia 9.7 ·
  Inglaterra 9.8 · Corea 9.9 · Argentina 10.1.
- **TA/p más altas (genuinos cards-over):** Turquía **2.6** · Bosnia 2.3 · Uruguay 2.3 · Canadá 2.2 ·
  Paraguay 2.2 · Suecia 2.2 *(n=4)* · Argelia 2.1 · Francia 2.0.
- **TA/p más bajas (cards-under):** Japón **0.9** · Inglaterra 1.0 · Noruega 1.1 · RD Congo 1.1 ·
  Jordania 1.1 · Bélgica/Países Bajos/Corea 1.2 · Argentina 1.3.
- **⚠️ El matiz clave (faltas que NO se convierten en tarjeta):** las CAF físicas **cometen muchas
  faltas pero las amonestan poco** — Senegal 14.5 faltas → solo 1.6 TA; Costa de Marfil 14.4 → 1.3 TA.
  Falta táctica "limpia" / criterio arbitral más permisivo. **NO** son cards-over pese al volumen de faltas.
- **⚠️ Al revés (pocas faltas, muchas tarjetas = alto ratio):** Turquía 10.6 faltas pero **2.6 TA**;
  Uruguay 11.1 → 2.3 TA. Aquí la amonestación SÍ llega → son los **cards-over reales** (la reserva, no el volumen).
- **Operativo:** para team-cards-over priorizar **TA/p alto** (Turquía, Bosnia, Uruguay, Canadá, Paraguay,
  Argelia), no el mero conteo de faltas. Para cards-under: Japón, Inglaterra, Noruega, Argentina. **Siempre
  cruzar con el árbitro probable** (co-driver del total de tarjetas; ver tabla de árbitros). Rojas: dato no
  fiable de esta fuente (ver leyenda), no apostar overs de rojas sobre este promedio.

**Sin datos bajo DT actual (2):** Chequia (Koubek dic-25), Túnez (Lamouchi ene-26) — DTs muy recientes con amistosos sin cobertura de stats. Usar solo el read cualitativo de §6.5 (ya marcados alta-incertidumbre). n=1-2 (Marruecos, Ghana, Arabia, Suecia, Uzbekistán) = baja confianza.

**Verificación de DT (2026-05-31):** los 48 DTs revalidados contra quién anunció el plantel de 26 en mayo-26. **Marruecos era el único error** (Regragui→Ouahbi, corregido). Ajuste de fecha: Irak/Arnold desde may-25 (no ene-26) → recuperó datos. Todos los demás 47 confirmados.

---

## 6.6-bis — Fuerza de calendario (SoS): ajuste de las stats crudas (mejora #5)

> **Qué resuelve.** Los promedios de §6.6 son **CRUDOS** → inflados/deflactados por la calidad del rival.
> Esta capa computa un **Elo** (estilo World-Football-Elo: peso por torneo + margen + ventaja de local) para
> TODAS las selecciones desde `data/cache/martj42_international_results.csv` (CC0), y para cada equipo promedia
> el **Elo actual de sus rivales** en sus últimos ≤20 partidos bajo el DT actual = **SoS**. Script:
> `scripts/spike/tsp/42_strength_of_schedule.py` (offline, JSON gitignored).
>
> **Honestidad:** el CSV corta en **2026-03-31** (amistosos de abril-junio no incluidos) → ventana ligeramente
> distinta a la de §6.6 (partidos con stats de API-Football), pero captura la **misma era**. **Ghana y Arabia
> quedan sin SoS** (DT desde abril, sin partidos jugados en el snapshot) → usar su §6.6 crudo con cautela.
> `cal`: **DURO** = Δ≥+80 sobre la media (1732), **FLOJO** = Δ≤−80. **Elo propio** = power-ranking interno.

| Equipo (DT·n) | Elo propio | SoS (avg opp Elo) | cal | Stat cruda que se RE-INTERPRETA |
|---|---|---|---|---|
| **CALENDARIO DURO** (stats DEFLACTADAS → el equipo es MEJOR que el número crudo) ||||| 
| Colombia (20) | 2050 | 1934 | DURO | 1.7 GF / 1.1 GA es sólido vs rivales fuertes |
| Paraguay (18) | 1910 | 1936 | DURO | 1.1 GF NO es romo: vino vs los más duros |
| Ecuador (18) | 2016 | 1912 | DURO | **0.3 GA = defensa élite REAL** (la más fiable) |
| Brasil (10) | 2059 | 1910 | DURO | 1.8 GF/0.8 GA honestos vs CONMEBOL |
| España (20) | **2222** | 1892 | DURO | **2.6 GF NO inflado** (output élite vs duro) |
| Uruguay (20) | 1970 | 1869 | DURO | 0.8 GF refleja crisis real (no rival débil) |
| Suiza (20) | 1941 | 1867 | DURO | 1.9 GF decente vs duro |
| Francia (20) | 2137 | 1861 | DURO | leak 1.1 GA es real vs buenos rivales |
| EE.UU. (20) | 1822 | 1856 | DURO | 1.4 GA permeable confirmado vs duro |
| México (20) | 1961 | 1839 | DURO | 1.3 GF bajo pese a rival fuerte (ojo ataque) |
| Portugal (20) | 2040 | 1835 | DURO | 0.9 GA decente vs duro |
| Argentina (20) | 2180 | 1822 | DURO | **0.5 GA élite REAL** vs CONMEBOL |
| **MEDIO** (Δ entre ±80) ||||| 
| Alemania 1985·1805 · Túnez* 1741·1796 · Escocia 1821·1793 · Canadá 1893·1773 · P.Bajos 2014·1760 · Croacia 1982·1743 · Turquía 1955·1742 · Corea 1869·1725 · Uzbekistán 1820·1714 · Australia 1889·1713 · Jordania 1763·1706 · N.Zelanda 1742·1702 · Japón 1980·1700 · Bosnia 1641·1692 · Noruega 1964·1689 ||| medio | (Noruega 3.0 GF ya roza inflado, Δ−43) |
| **CALENDARIO FLOJO** (stats INFLADAS → el equipo es PEOR que el número crudo) ||||| 
| Panamá (20) | 1864 | 1660 | FLOJO | 0.6 GA window halagado |
| Catar (11) | 1586 | 1648 | FLOJO | el Elo más bajo del torneo |
| Senegal (19) | 1928 | 1642 | FLOJO | 0.6 GA inflado (rival CAF flojo) |
| Irak (13) | 1746 | 1641 | FLOJO | low-scoring vs flojos |
| Austria (20) | 1875 | 1634 | FLOJO | **2.4 GF / 0.8 GA inflados** (10-0 San Marino) |
| **Inglaterra (12)** | 2079 | 1633 | FLOJO | **0.4 GA MUY inflado → regresa vs élite** |
| Egipto (20) | 1813 | 1621 | FLOJO | **0.7 GA halagado** (no es muro vs WC) |
| Irán (20) | 1880 | 1613 | FLOJO | 0.7 GA inflado |
| **Bélgica (12)** | 1915 | 1592 | FLOJO | **3.2 GF MUY inflado** (ataque sobrevalorado) |
| Argelia (20) | 1849 | 1580 | FLOJO | 0.6 GA inflado (y aéreo frágil, §6.8) |
| **C. de Marfil (20)** | 1793 | 1568 | FLOJO | **0.5 GA inflado** ("0 encajados" halagado) |
| RD Congo (20) | 1764 | 1558 | FLOJO | 0.6 GA inflado |
| Cabo Verde (20) | 1652 | 1550 | FLOJO | 1.2 GF/0.9 GA de debutante vs flojos |
| Sudáfrica (20) | 1658 | 1530 | FLOJO | 0.8 GA inflado (+ ABP frágil, §6.8) |
| Haití (19) | 1698 | 1513 | FLOJO | 2.5 GF MUY inflado vs CONCACAF menor |
| **Curaçao (20)** | 1622 | 1485 | FLOJO | **el SoS más bajo**; todo halagado |

\* Túnez/Marruecos/Suecia/Chequia con n=2-4 (baja confianza).

**Lecturas ajustadas clave (lo que el SoS cambia):**
- **Inglaterra:** Elo propio élite (2079) PERO **0 GA / 0.4 GA logrado vs el calendario MÁS flojo de los grandes** (SoS 1633) → la solidez defensiva **regresa fuerte vs élite**; no comprar "muro" a precio caro. Cuantifica el ⚠️ de §6.7.
- **Bélgica:** **3.2 GF es un espejismo de calendario flojo** + defensa leaky → el ataque está sobrevalorado por el número; el lean BTTS/Over se sostiene por la defensa, no por una pólvora élite real.
- **Côte d'Ivoire / Egipto / Argelia / DR Congo / Sudáfrica:** sus GA bajísimos (0.5-0.8) están **inflados por calendario CAF flojo** → NO sobreponderar "portería a cero" vs rivales WC fuertes; en Argelia/Sudáfrica además choca con la fragilidad aérea de §6.8.
- **CONMEBOL (deflactado):** **Ecuador 0.3 GA y Argentina 0.5 GA vs SoS DURO = las defensas más fiables del torneo** (números logrados vs rivales fuertes). Paraguay/Colombia: su GF modesto NO es debilidad ofensiva — vino vs los más duros; no fadear su ataque a ciegas.
- **España:** 2.6 GF con SoS DURO + Elo 2222 (el más alto) = **output élite genuino, no inflado** → el lean team-over/dominio es el más limpio.
- **Power-ranking (Elo propio):** top = España 2222, Argentina 2180, Francia 2137, **Inglaterra 2079**, Brasil 2059, Colombia 2050, Portugal 2040; fondo = Catar 1586, Curaçao 1622, Bosnia 1641, Cabo Verde 1652, Sudáfrica 1658.

---

## 6.7 — Profundización pre-WC por selección (jun-2026)

> **Qué es.** Capa **fechada y perecedera** (convocatorias de 26, lesiones, ejecutantes de balón
> parado, forma de clasificación, correcciones al overlay) investigada selección por selección de
> fuentes 2024-2026, con WC2026 arrancando el 2026-06-11. Complementa §6.5 (arquetipo durable) y §6.6
> (stats). **Caduca rápido** — re-verificar XI/lesiones el día del partido.
>
> **CORRECCIONES transversales que esta capa destapó (importantes):**
> - **Vía de clasificación:** Suecia, Turquía y Bosnia entraron por **repechaje** (no directo), arrastrando
>   debilidades que el "clasificó" liso ocultaba. Turquía: **0-6 vs España**. Suecia: **Isak se perdió el
>   repechaje** (peroné) → la identidad se montó solo sobre Gyökeres.
> - **Bajas que invalidan reads del overlay:** **Países Bajos sin De Ligt + De Vrij + Xavi Simons**
>   (zaga improvisada → el "mejor defensa del grupo" flaquea); **Suiza sin Schär**; **Alemania: ter Stegen
>   FUERA → Neuer titular**; **Bélgica: Debast duda**.
> - **Ejecutantes de ABP corregidos:** **Portugal = Bruno Fernandes** (FK/córner), no Ronaldo; **Suiza ya
>   NO tiene a Shaqiri**.
> - **Penales NO automáticos:** **Haaland falló DOS penales vs Israel (oct-25)**.
> - **España: Rodri RECUPERADO del LCA** y convocado → corrige el "pivote en flux".
> - **Francia: el lean *under* del Euro 2024 ya NO aplica** (marca mucho pero concede → BTTS/team-over).

#### UEFA

- **Inglaterra (Tuchel).** Clasificó **8-8-0-0, 22 GF / 0 GA** (grupo flojo → 0-GA regresa vs élite). Squad-26 (22-may): **omitidos Foden, Palmer, Trent, Maguire, Gibbs-White** (menos creación de pizarra y menos aéreo defensivo en ABP). Dudas físicas: **Livramento, Reece James, Stones**. Pickford titular, solo 3 GK. **ABP/props:** penal+referencia = **Kane**; 2º FK/penal = **Saka** (sube sin Palmer). Backup-9 Watkins. **TA/p 1.0 → cards-under válido.** ⚠️ Calor de Florida; 10 fijo borroso. [espn/englandfootball]
- **Francia (Deschamps).** Squad-26 (~14-may): **mediocampo de solo 5** (OUT Camavinga, Kolo Muani) → profundidad frágil ante sanción/lesión. **Forma:** prolíficos pero **conceden en casi todos** → la fuga defensiva 2025 persiste. **ABP:** penal **Mbappé**, FK **Olise**, córner **Olise+Dembélé**, CBs aéreos élite. **CORRIGE overlay:** lean **BTTS/team-over Francia**, ya no *under* puro. ⚠️ Último torneo de Deschamps. [espn/rotowire]
- **España (de la Fuente).** Squad-26 (25-may): **Rodri RECUPERADO del LCA** y convocado (riesgo = ritmo), **Gavi vuelve**, **sin jugadores del Madrid**. **Forma:** quali invicto 21 GF/2 GA (Turquía 6-0); perdió final NL vs Portugal. **ABP/props:** penal **Oyarzabal**; córner/FK **Yamal, Pedri, Baena, Grimaldo, Olmo**; **Merino amenaza aérea real** (10 goles, varios de cabeza) → goleador Oyarzabal/Merino por encima de "Yamal scorer". ⚠️ Ritmo de Rodri; 9 fijo sin cerrar. [aljazeera/beIN/rotowire]
- **Alemania (Nagelsmann).** **CORRIGE portería:** ter Stegen FUERA → **Neuer titular** (salió del retiro). **Gnabry FUERA**; **Musiala fitness condicional**. Kimmich capitán. **Forma irregular:** abrió quali con 0-2 vs Eslovaquia, cerró 6-0. **ABP arma cuantificada: 28% de goles desde la Euro vienen de balón parado** (Kimmich ejecuta; aéreos Tah/Rüdiger/Anton/Havertz). **Props:** goleador **Woltemade**/Havertz. ⚠️ Fitness Musiala; penalty-taker no confirmado (no asumir). [bundesliga/TFA set-pieces]
- **Portugal (R. Martínez).** Squad-26 (19-may). **Ronaldo (41, no 40)** apto pero sin ritmo (molestia isquios, ausente marzo). **Rúben Dias duda real** (isquios, clave en zaga). **Forma:** campeón NL; quali 20 GF / **7 GA → NO portería a cero** (confirma overlay). **CORRIGE ABP:** ejecutante FK/córner = **Bruno Fernandes** (no Ronaldo); penal **Ronaldo+Bruno**. ⚠️ Minutos Ronaldo / aptitud R. Dias hasta el debut (17-jun vs RD Congo). [sportsmole/rotowire]
- **Países Bajos (Koeman).** **CORRIGE overlay (zaga):** **De Ligt OUT, De Vrij OUT, Xavi Simons OUT (LCA)** → pareja de centrales improvisada (Van Dijk + Van de Ven/Aké/Hato) → el "mejor defensa del grupo" flaquea, y **baja el peso aéreo ofensivo de ABP**. **Depay volvió de lesión muy justo** (óxido). **Forma:** ganó grupo 27 GF/4 GA pero **2× 1-1 vs Polonia** (no batió al serio). **ABP:** penal **Van Dijk** (fluido con Depay); FK/centros **Depay**, Kluivert. **Props:** goleador Depay (fitness dudoso) → **Gakpo más fiable**. [espn/onefootball/rotowire]
- **Bélgica (Rudi Garcia).** Squad-26 (15-may): **De Bruyne (ojo) y Lukaku (cadera) entran sin ritmo**; **Debast duda (muslo)** agrava la reconstrucción defensiva. **Forma:** quali invicto 29 GF pero **empates nerviosos vs Macedonia/Kazajistán** (vulnerable a bloque compacto, no solo a élite) + 1-1 vs México. **ABP/props:** córner KDB/**Tielemans/Trossard**, FK KDB/**Doku**, penal KDB/**Tielemans/Lukaku**; goleador Lukaku/De Ketelaere; **Onana foul-prone**. ⚠️ Ritmo KDB/Lukaku; centrales sin probar. [rotowire/fotmob]
- **Croacia (Dalić).** Squad-26 (18-may): Modrić (40) **6º Mundial**; dudas de ritmo **Kovačić (Aquiles, casi toda la temporada fuera)** y **Gvardiol (tibia, ene-26)**. **Forma:** líder grupo 26 GF/4 GA (vs flojos); **0-2 temprano en Montenegro** confirma fragilidad de arranque/transición del overlay. **ABP:** penal/FK **Modrić, Perišić, Kramarić**; córner +Baturina/Pašalić/Moro. **Props:** goleador **Kramarić** (6 en quali, penalty-taker). ⚠️ Carga de minutos Modrić(40)/Perišić(37) en calor. Debut 17-jun vs Inglaterra. [croatiaweek/squawka]
- **Suiza (Yakin).** Squad-26 (20-may): **Schär FUERA (lesión larga)** → Elvedi al centro con Akanji; **Amdouni** recién de LCA. Xhaka capitán. **Forma muy fuerte:** quali invicto (2 GA), 0-0 anulando a Haaland, **junio 4-2 a México y 4-0 a EEUU** (pero amistosos inflan O2.5 — la defensa es el activo apostable, no el ataque). **CORRIGE ABP:** sin Shaqiri → penal **Xhaka/Embolo/Amdouni**, FK **Xhaka/Rodríguez**, córner **Vargas/Rieder/Aebischer**; aéreo Embolo. **Props:** goleador **Embolo**/Ndoye. ⚠️ Forma 4-3-3 vs 4-2-3-1 por fuente. [rotowire/SI]
- **Austria (Rangnick).** Squad-26 (18-may): **Alaba va y capitanea pero su fitness es la mayor duda de la zaga**; Arnautović (37) vice; **Wöber OUT**, Kalajdžić vuelve. **CORRIGE/MATIZA overlay:** quali 22 GF / **solo 4 GA → defensa élite** (no el "caos BTTS" sugerido; el 10-0 a San Marino infla GF). **ABP/props:** penal **Arnautović/Sabitzer/Baumgartner**; córner/FK **Sabitzer (ppal), Alaba, Schmid**; goleador **Arnautović** (récord nacional). Mantener tilt **córner por presión**, cauto con BTTS automático. ⚠️ Minutos Alaba; Grupo J durísimo (Argentina/Argelia/Jordania). [ORF/rotowire]
- **Noruega (Solbakken).** **⚠️ Ødegaard duda real** (~5 lesiones en la temporada, ausente marzo) → sin él baja la creación central. Haaland sano. **Forma 8/8 en quali** (doblete a Italia) pero vs rivales flojos (11-1 Moldavia). **CORRIGE ABP:** córner/FK **Ødegaard/Ryerson/Thorstvedt/Bobb** (no Haaland; Haaland remata). **Props:** **Haaland 16 goles en 8** (anytime/team-total núcleo) PERO **falló 2 penales vs Israel** → penalty-taker no automático. Primer Mundial desde 1998; grupo durísimo (Francia/Senegal/Irak). [aljazeera/uefa/goal]
- **Escocia (Clarke).** **Clasificó directo** (1º grupo, 4-2 a Dinamarca, overhead McTominay). Primer Mundial desde 1998. **⚠️ CAMBIO CLAVE: Gilmour OUT (rodilla, 30-may)** → debilita el control del medio; entra Tyler Fletcher (19). **ABP (edge declarado, con nombres):** penal **McTominay**+McGinn; córner/FK **McGinn, Ferguson, Robertson, Christie**. **Props:** **McTominay** goleador desde el medio + penalty-taker; **9 rotativo sin titular fijo** (baja conversión de "goleador de un 9"). Grupo: Haití (13-jun), Marruecos, Brasil. [skysports/rotowire]
- **Chequia (Koubek · alta incertidumbre).** **CORRIGE formación:** NO es 3-4-1-2 fijo → **rota 4-2-3-1 ↔ 3-4-2-1 por rival**; estilo confirmado: mid-block físico, directo, aéreo a Schick, Souček motor. DT 74a. **Pedigrí de tanda** (2 shootouts en playoff: Irlanda y Dinamarca). **ABP es el edge:** **8 goles de balón parado en quali = tope de Europa** (una fuente dice 10); córner **Coufal/Souček/Jurásek/Provod**, FK **Souček**, aéreo **Krejčí (CB, anotó ABP en ambos playoffs)**+Schick. **Props:** goleador **Schick**, penal Souček/Schick. ⚠️ Muestra mínima bajo Koubek; ritmo de Hložek. [rotowire/SI]
- **Suecia (Potter · alta incertidumbre, n≈4).** **Clasificó por repechaje** (3-1 Ucrania, 3-2 Polonia). **CORRIGE overlay:** **Isak se perdió ambos repechajes (peroné)** → identidad montada solo sobre **Gyökeres**; y NO es dominador — vs Polonia **33% posesión, superado 9-15 remates, 2-9 córners** → contraataca, no domina ("mejor atacando" es engañoso). **Isak convocado pero forma dudosa** (4 goles en la temporada); **Kulusevski OUT (rodilla)**. **ABP:** penal **Gyökeres**; **Lagerbielke (CB) gol de cabeza** en ABP. Final vs Polonia **5 amarillas** (over-cards en duelos parejos). Debut 14-jun vs Túnez. [nbc/espn/uefa]
- **Turquía (Montella).** **Clasificó por repechaje** (1-0 Rumanía, 1-0 Kosovo); en grupo **0-6 vs España** (peor derrota en 60 años → fragilidad defensiva CONFIRMADA empíricamente). **⚠️ Çalhanoğlu (capitán) lesión muscular (sóleo), recuperación incierta** — si juega mermado/ausente **el edge ABP cae** (es el ejecutante de FK/penal/córner, sin sustituto claro). Güler debería llegar. **Props/cards:** confirma perfil **card-prone (TA 2.6 la más alta)** pero sin nombres individuales verificados (no inventar); penal **Çalhanoğlu**. ⚠️ Grupo reportado distinto por fuente — verificar sorteo. [dailysabah/olympics]
- **Bosnia (Barbarez).** **Clasificó por repechaje** (Gales + Italia 1-1/4-1 pen). **⚠️ Džeko (40) lesión de hombro** tardía vs Italia — variable viva (sin él baja techo aéreo+liderazgo); convocado igual. **CORRIGE formación:** §6.5 dice 4-2-3-1 → prensa 2026 reporta **switch a 4-4-2** (Demirović+Džeko). **Líder UEFA en duelos (544) y regates (97)** → corrobora perfil físico (faltas 14.8 + TA 2.3 = **cards-over vigente**). ABP: servicio aéreo a Džeko; penal sin fijo (Bajraktarević marcó el decisivo). Pedigrí de tanda → Under/draw/gol-tardío/shootout. [aljazeera/squawka/uefa]

#### CONMEBOL

- **Argentina (Scaloni · campeón vigente).** Squad-26 confirmado (28-29 may). **Messi VA (39, 6º Mundial)** — injury scare no serio, vigilar minutaje/rol (ya alternó banca en 2026). **Dybala OUT**; Mastantuono y Buendía fuera. **⚠️ Penal NO es fijo de Messi:** vs Zambia lo ejecutó **Otamendi** → penalty-taker por comité en KO. Goleador reparten **Lautaro/J. Álvarez/Messi**. **Amplitud post-Di-María:** sin reemplazo tipo-DM → la dan **Nico González, Giuliano Simeone, Barco** (carrilero), no un extremo desequilibrante. CBs fiables (defensa élite en quali); el riesgo es ritmo/transición, no solidez. [SI/espn]
- **Brasil (Ancelotti).** Squad-26 (18-may). **Neymar VA (34)** como **9 central** pero fitness/forma en Santos floja. **CORRIGE overlay (espina Madrid reducida):** **Rodrygo, Estêvão y Militão FUERA** (lesión) → queda Vinícius + Casemiro. **9 sin fijar** (Cunha 1º candidato; Endrick/Igor Thiago/Rayan compiten) — confirma el matiz. **Forma alta-varianza** bajo Ancelotti (5V-3D-2E: 0-0 Ecuador, 1-0 Paraguay, **4-1 derrota vs Argentina**). **Penal = Raphinha** (relevó a Vinícius, 18/19 carrera). ⚠️ Fitness Neymar; 9 abierto; portero/laterales veteranos. [espn/trivela]
- **Uruguay (Bielsa).** **CORRIGE etiqueta:** el "motín" debe reclasificarse a **grieta DT-plantel / apatía persistente** — Bielsa ratificado, sin rebelión activa a jun-26 (grieta deportiva real; Nández fuera por extrafutbolístico). Squad-26 (31-may): OUT **Nández + Suárez**, vuelve Muslera (5º Mundial). **Crisis goleadora CONFIRMADA:** 0-0 Argelia, **1-1 Inglaterra solo por penal de Valverde al 90+4** → Under/No-BTTS/córner-estéril vigentes. **Penal = Valverde**; aéreo Araújo/Giménez; Núñez no marca con la celeste. ⚠️ Clima interno no auditable; fitness Piquerez. [montevideo/espndeportes]
- **Colombia (Lorenzo).** Squad-26 (25-may): **James capitán** con molestia menor (OK); OUT Ditta, Castaño, Borré. **Grupo K: Portugal, Uzbekistán, RD Congo (sin anfitriones → sin fade-host).** **Forma:** cerró quali fuerte (3-0 Bolivia, 3-6 Venezuela) pero **1-2 vs Croacia (mar-26) = alerta defensiva** vs rival de tú-a-tú. **ABP/props:** **James penalty-taker** (anotó vs ARG y URU) + córner/FK, **máximo asistente de la quali (7)**; goleador **Luis Díaz** (7 quali); aéreo Davinson/Mina/Lerma. Doble ruta vigente; perfil Over/BTTS sostiene. ⚠️ Minutaje James (36). [eltiempo/infobae]
- **Ecuador (Beccacece).** Squad-26 (1-jun): **⚠️ Pacho (PSG) e Hincapié (Arsenal) juegan la final de Champions el 30-may → llegan tarde (3-jun)** → integración/carga de cara al debut 14-jun vs Costa de Marfil. **Campana y Mercado OUT (lesión).** Defensa élite CONFIRMADA (5 GA en quali, la más tacaña de CONMEBOL). **Ataque romo CONFIRMADO** (ESPN: invicto "opacado por la falta de gol") → Under/No-BTTS/portería-a-cero. **⚠️ Props:** Enner Valencia (36) máximo goleador con solo **6**, y **falló 3 penales en quali** → penalty-taker no fiable; reparto post-fallos no verificado. [espndeportes/eluniverso]
- **Paraguay (Alfaro).** 26 casi cerrado; **Gustavo Gómez (capitán)** + Junior Alonso eje; **⚠️ Villasanti convocado pese a no jugar desde ago-24 (LCA)** → titularidad dudosa. **Forma:** invicto en 9 bajo Alfaro, ganó en casa a **Brasil 1-0, Argentina 2-1, Uruguay 2-0**. **ABP con nombres:** goles de cabeza de **Galarza, Alderete** (de FK/córner servidos por Diego Gómez); **penal = Enciso** (no Gómez). **Props:** goleador **Sanabria/Almirón**; card-prone (TA 2.2) vía G. Gómez/Alderete por duelo aéreo. **MATIZ overlay:** low-scoring sí, pero el gol llega por **ABP+cabeza+transición** → ángulo = team-under + gol-de-cabeza/córner, NO "No-BTTS ciego" (marca a los top). ⚠️ XI con un solo amistoso pre-debut. [abc/espndeportes]

#### CONCACAF (anfitriones MEX/USA/CAN → recordar señal host-fade -12-18pp, §6 patterns_v2)

- **México (Aguirre · anfitrión, Grupo A vs Sudáfrica 11-jun/Corea/Chequia).** **🔴 CORRIGE overlay: Lozano FUERA** (sin minutos en San Diego + conflicto disciplinario; el overlay lo listaba RW titular) → amplitud recae en César Huerta/Alvarado/Quiñones/Vega. **⚠️ Edson Álvarez duda real** (cirugía tobillo feb-26) → sin su ancla, la salida-desde-atrás explotable EMPEORA. Jiménez referencia (entró tarde). **Forma:** invicto 2026 (empates vs Portugal/Bélgica, 2-0 Ghana) **pero 0-4 vs Colombia (oct-25)** sigue siendo la alerta — nivel inflado por rivales menores. **ABP/props:** penal **Raúl Jiménez**; FK Jiménez+Luis Chávez. ⚠️ Incertidumbre ALTA (único test élite reciente = goleada). [cbssports/foxsports]
- **EE.UU. (Pochettino · anfitrión).** Roster-26 (26-may): Pulisic/Adams/McKennie/Balogun/Weah dentro; **13 debutantes WC (mitad del plantel) → corrobora "XI poco rodado"**. **⚠️ CORRIGE eje: Chris Richards (CB titular) duda (tobillo)** → pareja McKenzie+Ream(37) improvisada → fragilidad aún más aguda; CBs lentos confirmado. **Forma:** 2-5 Bélgica, 0-2 Portugal, **3-2 vs Senegal (Mané doblete pese a perder)** → BTTS/Over vs calidad vigente. **ABP/props:** **Pulisic = penal + FK + córner (ejecutante único)**; goleadores Pulisic/Balogun (en forma). ⚠️ Aptitud Richards/Pulisic; host-fade aplica. [espn/foxsports/rotowire]
- **Canadá (Marsch · anfitrión).** Squad-26 (29-may): **⚠️ Davies convocado pero NO recuperado del todo** — tras el LCA sufrió **isquios en semis CL vs PSG** → Marsch lo da **dudoso para el debut (12-jun vs Bosnia)**, apunta al 2º partido (no titular fijo) → **la izquierda pierde mucho** sin él. J. David (Juventus) sano, líder. **Forma roma CONFIRMA overlay** (0-0 Ecuador, 1-0 Guatemala, 0-0 Túnez — "defiende, no marca"). **ABP/props:** **penal = J. David** (doblete de penal vs Islandia); aéreo Larin/Bombito; **card-over equipo válido (faltas 14.0/TA 2.2)**. ⚠️ ¿Juega Davies el debut? (probable no); host-fade. [canadiansoccerdaily/espn]
- **Panamá (Christiansen · Grupo L vs Inglaterra/Croacia/Ghana, debut 17-jun vs Ghana).** **2ª Mundial** (debutó 2018), clasificó directo. Squad-26: **⚠️ Carrasquilla (Pumas) duda (lesión inguinal)** — es córner/FK + penal, sin él cae el ABP; Godoy (capitán, 159 caps) sano. **🔴 MATIZ DURO:** **Brasil 6-2 Panamá (31-may)** — las "6 porterías a cero" eran vs inferiores CONCACAF; el modo compacto-contra **NO contiene a élite** → sesgo Under solo vs pares, NO vs su grupo. **Props:** goleadores quali Fajardo/J.L. Rodríguez (3 c/u); penal Carrasquilla. ⚠️ Fitness Carrasquilla; ¿el 6-2 es ruido o señal? [flashscore/olympics]
- **Curaçao (Advocaat · Grupo E vs Alemania/Ecuador/Costa de Marfil).** **Debut; la nación MÁS PEQUEÑA por población (~156k) en clasificar a un Mundial masculino** (0-0 en Jamaica lo selló, con suerte/aguante). **🔴 CHURN DE DT CONFIRMADO:** Advocaat dimitió (feb-26, salud familiar) → Rutten (perdió ambos amistosos de marzo) → **Advocaat RE-CONTRATADO ~13-may por presión del vestuario; 78 años = DT más veterano de la historia mundialista.** **🔴 CORRIGE forma: el "28 GF/5 GA, 10 invicto" es de la ERA QUALI — YA NO aplica.** Reales recientes: **China 0-2, Australia 1-5, Escocia 1-4** → equipo reensamblado, techo debutante real vs élite → **Over/team-total RIVAL, no portería-a-cero**. Núcleo: hermanos Bacuna, **Chong**, **Rangelo Janga** (goleador histórico, 21). ⚠️ XI fluido tras el retorno de Advocaat. [espn/aljazeera]
- **Haití (Migné · 1ª Mundial desde 1974).** Ganó Grupo C 3ª ronda (cierre: **3-3 en Costa Rica, hat-trick Nazon**); quali 20 GF / **13 GA → zaga NO tacaña** (confirma "defensa floja"). **CORRIGE formación:** no es 4-4-2 fijo → **rota 4-2-3-1 ↔ 4-4-2/4-3-3/3-5-2 por rival** (Bellegarde+Pierre doble pivote). Squad-26 (15-may): **Isidor (Sunderland), Bellegarde (Wolves), Nazon dentro; ~100% diáspora, 1 jugador local**. **ABP/props:** córner **Bellegarde/Deedson/Casimir**, FK **Bellegarde**, **penal Nazon** (alt. Isidor); goleador **Nazon/Isidor**. **⚠️ Sin sede local desde 2021** (pandillas controlan Port-au-Prince) → base en Curaçao, equipo expatriado sin afición — factor moral/logístico. → No-portería-a-cero, BTTS/Over vs los top. [si/rotowire/espn]

#### CAF (3 DTs nuevos 🔴 confirmados sin cambio: Ouahbi/Lamouchi/Queiroz)

- **Marruecos (Ouahbi · Grupo no listado).** **DT confirmado: Ouahbi SIGUE** (sin nuevo cambio), mandato declarado = recuperar el fútbol ofensivo "que faltó en la AFCON" (corrige a Regragui). **⚠️ Hakimi dentro pero duda física** (desgarro isquios, semis CL); **En-Nesyri FUERA** (irregular). Referencias El Kaabi/Rahimi. **Forma bajo Ouahbi:** Ecuador 1-1, Paraguay 2-1, Burundi 5-0; **amistosos clave pendientes: Madagascar 2-jun, Noruega 7-jun → señal real**. **MANTÉN el re-baselinar de §6.6:** el dominio territorial era de Regragui, NO de Ouahbi (n=2 los igualan/superan) → cautela en totales/team-style. NO inventar penalty-taker. ⚠️🔴 régimen 3 meses sin probar vs élite. [espn/thenational]
- **Senegal (Pape Thiaw · Grupo I "death": Francia 16-jun/Noruega/Irak).** DT confirmado pero **⚠️ disputa contractual viva** (contrato venció feb-26 — ruido de vestuario, no cambio). **🔴 CORRIGE overlay: el título AFCON 2025 fue RETIRADO por CAF y otorgado a Marruecos** (walk-off de la final) → "campeón AFCON" disputado; el pedigrí de tanda (Mendy) sí es real. **Mané (34) capitán, su último Mundial** (motivación máxima). **⚠️ Koulibaly (35) NO confirmado** (rotura muscular de 2º grado, baja desde abril; Thiaw no garantizó disponibilidad a fin de mayo) → la duda de CBs NO está resuelta; eje posible improvisado (Niakhaté + Seck/M. Sarr). **Forma:** 4/5 (3-1 Inglaterra en Wembley, 2-0 Perú). **Props:** goleador Mané/Jackson/Sarr; **Gueye card-prone**; físico "limpio" (14.5 faltas/1.6 TA) vigente. [aljazeera/espn]
- **Egipto (H. Hassan · Grupo G: Bélgica/Irán/NZ).** DT confirmado. **Salah capitán (deja el Liverpool)**, a 2 goles del récord histórico. **🔴 Mostafa Mohamed (9) EXCLUIDO** → ataque aún más Salah/Marmoush-dependiente. **Forma:** quali invicto 10/10, **7 porterías a cero, 2 GA** (confirma 0.4 GA); pre-WC 0-0 España, 4-2 perdido vs Croacia. **ABP/props (con nombres):** córner **Salah/Marmoush/Zizo**, FK **Salah**, **penal Salah (1º), Marmoush (2º)**; Salah anytime claro. 3-4-1-2 reservado a rivales fuertes. ⚠️ Carga/edad de Salah; tercer goleador inexistente. [cafonline/rotowire]
- **Argelia (Petković · clasificó).** DT confirmado (lista 31-may). **🔴 CORRIGE overlay: Bennacer OMITIDO** (el overlay lo listaba como "controla") → medio más vertical (Aouar/Bentaleb/Chaïbi); **portero RESUELTO: Luca Zidane** probable titular (era "sin asentar"). **IN:** Mahrez, Amoura, **Gouiri** (9 real). **Forma:** 7-0 Guatemala, 0-0 Uruguay; **eliminados QF AFCON 0-2 vs Nigeria (Osimhen) → "bullyable/aéreo flojo" refrendado.** **Props:** **Amoura goleador preferente** (pichichi africano de la quali); **card-prone confirmado (14.6 faltas/TA 2.1)**. ⚠️ Ejecutante exacto de ABP sin confirmar; Zidane debutante. [beIN/africasoccer]
- **Túnez (Lamouchi · Grupo F: NED/JPN/SWE).** **DT confirmado: Lamouchi** (overlay acertó), solo n=2 (1-0 Haití, 0-0 Canadá → confirma defensa-primero/ataque romo). **🔴 CORRIGE plantel:** **Laïdouni OUT, Msakni OUT** (el overlay los listaba); **omisión grande: Ben Romdhane (máx. goleador de quali, 4) FUERA** → ataque aún más despoblado de gol. **Skhiri sí, capitán/eje.** Estilo: 4-2-3-1 bloque medio, gol vía **ABP coreografiado + overlaps de Ali Abdi (LI, principal centrador)**. **Under/portería-a-cero/BTTS-No el más fuerte de CAF.** ⚠️ n=2 vs menores; XI sin asentar; no inventar penalty-taker. [fifa/carthagemagazine]
- **Costa de Marfil (Faé · Grupo E: Alemania/Curaçao/Ecuador).** DT confirmado. **🟢 "0 encajados en quali" VERIFICADO: 25 GF / 0 GA en 10** (mejor DG de África) → defensa élite sostenida. **🔴 CORRIGE overlay: Haller FUERA** (solo reserva) → el 9 pasa a **Evann Guessand** (focal aéreo); **Pépé recuperado/IN**. **Forma:** AFCON QF eliminados **2-3 vs Egipto (sí se les abre arriba)**; 4-0 Corea, 1-0 Escocia. **ABP/props:** **Kessié FK/penal/córner**, **Amad córner**; scorer Amad/Guessand/Diomande/Pépé. **Matiz vigente:** marca poco, "se apaga vs bloque bajo" (peligroso tras robar, no en build-up lento). ⚠️ Jerarquía de penalty-taker (Guessand vs Kessié) sin clara. [wikipedia/rotowire]
- **Ghana (Queiroz · Grupo no listado).** **DT confirmado: Queiroz** (overlay acertó), veterano (5º Mundial), orden+transición — pero solo ~3 partidos. **🔴🔴 CORRECCIÓN DURA DE PERSONAL: KUDUS FUERA** (cuádriceps, season-ending) **y Salisu (CB) FUERA (LCA)** → la defensa porosa pierde además un central, y el ataque ya NO pivota en Kudus → recae en **Semenyo (Man City), Iñaki Williams, J. Ayew (cap.)**. **Forma bajo Queiroz floja: 0-2 México, 0-2 Gales (2-jun), 0 goles en warm-ups.** **ABP/props:** **J. Ayew penal + FK + córner** (máx. goleador quali). **🔴 MERCADO: el sesgo Under/low-block del overlay se ENFRÍA** — defensa des-gelada + sin CB titular + sequía de gol → BTTS/Over por **concesión** más que por pegada; NO sobre-modelar low-block vs Inglaterra. ⚠️🔴 LA MÁS IMPREDECIBLE. [espn/ghanafa]
- **Cabo Verde (Bubista · Grupo H: España/Uruguay/Arabia).** DT confirmado (**CAF Coach of the Year 2025**). Debut histórico (selló 3-0 a Eswatini, por encima de Camerún); **país más pequeño por superficie en clasificar**. **🔴 CORRIGE overlay:** **Teixeira y Janga NO entraron** en la lista; **Jamiro Monteiro es mediocampista, no delantero**. Núcleo: **Ryan Mendes (cap., córner/FK)**, Garry Rodrigues, Jovane Cabral, **Livramento (4 goles quali, referencia)**, Logan Costa (CB). **Forma:** 2-4 Chile, 1-1 Finlandia → **defensa NO impenetrable vs top** → "portería-a-cero" no sostenida vs su grupo. **ABP:** Mendes + Kevin Pina; penalty-taker no verificado. ⚠️ Techo de debutante. [aljazeera/cafonline]
- **Sudáfrica (Broos · Grupo A: México/Corea/Chequia).** DT confirmado. Clasificó 1º **pese a deducción de 3 pts** (alineó a Mokoena suspendido → 3-0 a Lesoto). **🔴 CORRIGE overlay (problema de gol AGRAVADO, no atenuado):** pre-WC **0-0 vs Nicaragua (#131) con Foster fallando penal (palo)**, 1-1 y 0-2 vs Panamá; AFCON R16 fuera vs Camerún. → **team-total-Under/low-scoring reforzado**; defensa sigue el activo. **ABP/props:** **Mokoena FK directo** + máx. goleador reciente; **penal Foster (pero acaba de fallar — ojo)**; R. Williams (GK) parador de penales. ⚠️ Salida a WC retrasada por lío de visas mexicanas; ejecutante de penal en duda. [goal/kickoff]
- **RD Congo (Desabre).** DT confirmado. **Clasificó vía repesca intercontinental: 1-0 vs Jamaica (aet, gol Tuanzebe 100')** — 1er Mundial desde 1974 (Zaire). **Mbemba capitán** (récord caps); **Wan-Bissaka y Tuanzebe** debutan (cambiaron de Inglaterra). **🔴 CORRIGE overlay (orden de ataque):** **Bakambu primario (21 goles, club Betis)** > **Wissa degradado** (forma pobre/lesión: 3 goles en 24 apps tras fichar al Newcastle). **🔴 ABP — llena hueco del overlay ("poco documentado"): Gaël Kakuta = penalty-taker + hub creativo de ABP.** Bloque compacto + contra vigente. ⚠️ Forma de Wissa; profundidad fina si Bakambu (35) se apaga. [aljazeera/beIN]

#### AFC (4 DTs nuevos 🔴 confirmados sin cambio: Donis/Cannavaro/Sellami/Arnold)

- **Japón (Moriyasu · Grupo F: Países Bajos 14-jun/Túnez/Suecia).** DT confirmado. **🔴 CORRIGE overlay (el aislamiento de bandas se ROMPE): Mitoma FUERA (isquios) y Minamino FUERA (LCA)** → desaparece el 1v1 izquierdo; **Kubo (der.) carga la creación casi solo** (apoyo Doan/Ito); Tomiyasu vuelve. **Forma excelente:** 1-0 Inglaterra (Wembley), 1-0 Escocia; quali 54 GF / **3 GA** (defensa élite confirmada, SOT-contra 1.7). **ABP/props:** FK **Kubo/Kamada**, córner **Kubo/Doan/Ito**; **sin 9 élite** (Ueda/Maeda) → **techo ofensivo BAJADO sin Mitoma**, team-total/Over menos atractivo. **TA 0.9 = cards-under (la más baja de las 48).** ⚠️ Penalty-taker no confirmado; suplencia de la verticalidad de Mitoma. [aljazeera/squawka]
- **Corea del Sur (Hong M-b · Grupo A: Chequia 11-jun/México/Sudáfrica, altitud Guadalajara).** DT confirmado (lista 16-may). Son (34, **capitán, LAFC/MLS**). **Forma volátil/dependiente de rival:** **colapso mar-26: 0-4 vs Costa de Marfil + 0-1 Austria (5 encajados, 0 marcados)** vs goleadas a menores (Trinidad 5-0) → techo vs élite NO probado. **CORRIGE/MATIZA overlay:** back-3 = blanco de crítica explícita (prensa pide back-4 ya); mecanismo de fragilidad = **carrileros suben → huecos en transición** → BTTS/goles-en-contra vs calidad reforzado. **ABP/props:** **FK Son + Lee Kang-in**; **penal Son**. ⚠️ ¿back-3 o back-4 en el WC? (sin decisión pública); sequía de Son en juego abierto. [espn/koreaherald]
- **Irán (Ghalenoei · Grupo G: Bélgica/Egipto/NZ).** DT confirmado. **🔴 CORRIGE §6.6: Taremi juega en OLYMPIACOS, no Inter** (capitán/foco). **⚠️ Azmoun omitido del preplantel** (¿lesión/castigo?) pero hay debate de reincorporación — veto NO 100% firme. **🔴 Riesgo logístico USA REAL:** plantel entrenaba en Turquía **sin visados** al 29-may (conexiones IRGC complican entrada) — riesgo operativo genuino. **Forma:** 5-0 Costa Rica (Taremi doblete de penal), 1-2 Nigeria. **MATIZ §6.6 confirmado:** atacan más que "defensa-primero" vs menores (puede golear a NZ); "muele 1-0" aplica vs élite (Bélgica). **Penal = Taremi.** ⚠️ Visados; estatus de Azmoun. [thedailystar/presstv]
- **Australia (Popovic · Grupo D: Turquía 14-jun/USA/Paraguay).** DT confirmado (lista 1-jun). **CORRIGE disponibilidad: Souttar IN** (vuelve de lesión, pilar aéreo); **Boyle FUERA (cortado), McGree FUERA (isquios)**. **Forma:** FIFA Series 2/2 (Curaçao 5-1) pero **0-1 vs México** → ofensiva luce vs débiles, se apaga vs medio/alto (confirma "ataque limitado"). **ABP/props:** amenaza aérea real **Souttar + Burgess + Circati** → edge córner/header-anytime; goles desde banda/medio (Irankunda doblete vs Curaçao). **Faltas 8.5 (las menos de las 48) confirmado.** ⚠️ Penalty-taker no verificado; fitness Souttar/Leckie. [socceroos/flashscore]
- **Arabia Saudí (🔴 Donis · Grupo H: España/Uruguay/Cabo Verde).** **DT confirmado: Georgios Donis (desde 24-abr-26, contrato 1 año)** — overlay acertó; Renard cesado (0-4 Egipto). **Clasificó vía 4ª ronda AFC** (no directa; selló 0-0 vs Irak), equipo cerrado. Identidad Donis = estructura defensiva, NO reinventor, ~6 sem pre-WC. **Núcleo WC22 retenido (7)**; **Salem Al-Dawsari (cap.) sano**. **Forma bajo Donis: derrota 2-1 vs Ecuador (n=1) → fragilidad defensiva confirmada.** **ABP/props:** **Al-Dawsari penalty-taker + FK** (71% conversión carrera) + referencia goleadora. → **inestabilidad defensiva, BTTS/goles-en-contra** en Grupo H brutal. ⚠️🔴 n=1 bajo Donis; XI sin fijar. [aljazeera/alarabiya]
- **Catar (Lopetegui · Grupo B: Suiza/Canadá/Bosnia).** DT confirmado. **Clasificó vía 4ª ronda AFC** (2-1 EAU, 0-0 Omán) — 1ª vez por mérito (2022 fue anfitrión); en 3ª ronda **5-0 vs EAU** expuso la defensa. **⚠️ Almoez Ali "fit-again" tras cirugía** (jugó ~2 partidos en el año) → ritmo dudoso, **riesgo en su línea de goleador** (12 en quali). **Afif sin problemas.** **MANTÉN matiz §6.6:** bajo Lopetegui los superan y marcan poco (SOT 2.3) — defensa vulnerable confirmada. **ABP/props:** **Afif penalty-taker** (hat-trick de penales en final Asian Cup 2024) + creador-finalizador. ⚠️ Ritmo de Almoez; back line sin probar. [thenational/peninsula]
- **Uzbekistán (🔴 Cannavaro · debut).** **DT confirmado: Cannavaro** (clasificó Kapadze) — overlay acertó. **Clasificó directo en 3ª ronda AFC** (1ª vez en su historia, 1er centroasiático). **Shomurodov capitán** (cedido en Başakşehir, 13 goles/18). **⚠️ Khusanov (Man City, CB ancla) llega CORTO de ritmo** (apenas jugó en PL) → el ancla aérea defensiva no está afilada. **Forma (Cannavaro):** ganó FIFA Series (3-1 Gabón, Venezuela en penales). **ABP/props:** **penal Shukurov → Shomurodov**; córner/FK **Fayzullaev/Shukurov/Masharipov**; goleador Shomurodov. **5-3-2 de techo ofensivo BAJO confirmado por el propio DT** ("nada que perder") → Under/cagey. ⚠️ n=2 competitivo; debut absoluto. [fifa/rotowire]
- **Jordania (🔴 Sellami · Grupo J: Argentina/Argelia/Austria).** **DT confirmado: Sellami** (marroquí nacionalizado jordano) — overlay acertó. **Clasificó 1ª vez en su historia** (3-0 a Omán). **🔴 CORRECCIONES:** **Al-Tamari ahora en RENNES** (no Montpellier; sigue siendo la navaja + FK/co-penal); **🔴 Al-Naimat (el "9" del overlay) FUERA del Mundial (LCA en Copa Árabe)** → referencia ofensiva pasa a **Ali Olwan** (29 goles con Jordania). **ABP/props:** penal **Olwan/Al-Tamari/Baha' Faisal**, córner/FK **Al-Tamari**; goleador Al-Tamari. **MATIZ:** la tesis counterpuncher+ABP aguanta, pero el eje ya NO es un target — es transición/banda + Olwan; amistosos recientes con mucho BTTS (inflados) → en Grupo J durísimo, Under/bloque bajo más fiable. ⚠️ Fitness Olwan; quién es el 9. [wikipedia/rotowire]
- **Irak (🔴 Graham Arnold · Grupo I: Francia/Senegal/Noruega).** **DT confirmado: Arnold.** **🔴 CORRIGE overlay ("armó días antes"):** Arnold asumió **9-may-25** y dirigió TODA la 4ª/5ª ronda + playoffs (no fue parche). **Clasificó (1ª vez desde 1986) vía playoff intercontinental: 2-1 vs Bolivia** (Al-Hamadi 10'+18', Aymen Hussein 53'). **⚠️ Ali Al-Hamadi (Luton) DUDA REAL** (temporada arruinada por lesiones). **ABP sigue el edge:** **Al-Ammari ejecutante** (15 chances/4 asist en quali); goleador Aymen Hussein. Low-block → Under coherente en Grupo I brutal. ⚠️ Fitness Al-Hamadi; sistema sin muestra de torneo; penalty-taker no verificado. [aljazeera/fifa]

#### OFC

- **Nueva Zelanda (Bazeley · Grupo G: Irán 16-jun/Egipto/Bélgica).** DT confirmado (lista 14-may, sin sorpresas). Wood (capitán, Forest) IN pese a **temporada PL mermada por lesión** → ojo ritmo. **🔴 CORRIGE overlay/datos: "Bell (GK)" es erróneo — Joe Bell es MEDIOCAMPISTA (Viking FK)**; GK real **Crocombe (Millwall, probable #1)**. **Forma MALA:** 1 victoria en ~7 (0-2 Finlandia, 0-2 Ecuador, 1-2 Colombia, 1-1 Noruega). **ABP/props:** **penal = Wood** (confirmado) + referencia aérea + goleador del equipo (anytime/team-total); Singh suministra ABP. **MATIZ overlay clave:** el "aéreo élite / 0.6 GF" sale de **OFC + amistosos inflados** — vs UEFA/CONMEBOL **no marcan y encajan ≥2** repetidamente → **Under NZ team-total / NZ-no-marca / rival -1.5 AH** en sus 3 partidos. Amistosos pre-WC: Haití (2-jun), Inglaterra (7-jun). ⚠️ Fitness Wood; córner-friendly no verificable con splits OFC. [rnz/espn]

---

## 6.8 — Vulnerabilidad DEFENSIVA a balón parado (jun-2026)

> **Qué es.** Mejora #4 del roadmap ([[project_wc2026_analysis_gaps_roadmap]]). §6.7 dio los **ejecutantes**
> de ABP (ofensiva); esta capa da el **otro lado: quién es FRÁGIL defendiendo córners/FK** (esquema de marca,
> eslabón aéreo débil, mando de área del portero), con datos ACTUALES 2025-26 (pareja de centrales de junio).
> El edge = **mismatch** equipo-aéreo (§6.7 takers + rematadores altos) × zaga vulnerable → córner/header en contra.
>
> **Honestidad (importante):** NO existe **xGA de balón parado público para selecciones** → estas notas son
> **cualitativas** (esquema de marca + eslabón débil + evidencia de goles concretos encajados), no una métrica.
> Rating: **🔴 vulnerable · 🟡 medio · 🟢 fuerte en el aire**. Hilo recurrente que destapó la investigación: en
> varias selecciones el agujero es el **portero saliendo a centros**, no el central. Re-verificar el XI del día.

#### UEFA

- **Inglaterra 🟡.** **Guéhi** frágil en el aire (duelos aéreos pobres) y **sin Maguire/Konsa en el 26 → cero plan-B aéreo de banquillo**; mitiga que **Pickford SÍ comanda centros**. 0 GA en quali pero vs grupo flojo (no predictivo). Marca híbrida (no detallada).
- **Francia 🟡.** CBs **élite aéreos** (Saliba/Upamecano/Konaté) NO son el agujero → el riesgo es **Maignan dudoso saliendo a centros en partidos grandes** + el leak 2025 (Islandia 2-2, gol de **FK mal defendido**).
- **España 🟢.** Corrige la premisa "zonal puro": marca **individual + 2 zonales** (efectiva, 2 GA en quali). Riesgo real = **línea alta a la espalda**, NO el córner; **Huijsen (1.95) aporta peso aéreo** si entra; Simón sale poco.
- **Alemania 🟢** (matiz 🟡). **Tah/Rüdiger** fuertes por arriba, **Neuer** mantiene autoridad de área (CL 25-26); los goles encajados fueron de **juego abierto**, no ABP. Esquema defensivo no público.
- **Portugal 🟡** (→ alto sin Rúben Dias). **Diogo Costa SALE pero con juicio errático**: falló el puño en córner vs Hungría (14-oct) → gol de Szalai (≥1/7 GA de córner). **Sin Dias**, Inácio/Veiga no dominan el aire → vector real. Ver CB titular el 17-jun.
- **Países Bajos 🟡** (🔴 si arranca Aké+Hato). **Sin De Ligt ni De Vrij** se erosiona el aéreo; Van Dijk queda **solo bien acompañado**; **Verbruggen pasivo en su área**. Pero los goles vs Polonia fueron de **jugada**, no ABP → riesgo estructural/teórico, no demostrado aún.
- **Bélgica 🟡.** Zaga joven **De Winter/Theate sin probar** + lapsus de concentración; **Courtois mitiga el córner directo** (domina área). 5 goles vs Gales (frágil también vs bloque). Lean Over/BTTS sigue.
- **Croacia 🟢.** **4 GA en quali (mejor del grupo)**; las concesiones recientes fueron **transición / FK directo de Olise**, NO aéreo. Riesgo = **ritmo/arranque oxidado** (Gvardiol/Kovačić de lesión), no córner.
- **Suiza 🟢.** **Elvedi domina el aire**, **Kobel #1** (Sommer retirado), back-3, **2 GA en quali**. Sin Schär resta experiencia, no solidez aérea. Sin evidencia de fuga por ABP.
- **Austria 🟢.** **Danso/Lienhart** buen porte aéreo, **4 GA élite** en quali. Sube a 🟡 **solo si Alaba arranca** (falta de ritmo). GK Schlager sin dato de salidas. Sin edge demostrable en córner en contra.
- **Noruega 🟡** (datos insuficientes). CBs jun-2026 = **Ajer + Heggem** (no Østigård/Ryerson del overlay; Ryerson es lateral). Fragilidad documentada = **línea alta/transición**, no aérea; equipo físicamente alto; 5 GA pero vs grupo flojo (solo Italia fue test).
- **Escocia 🟡.** Frágil ante **centros y segundas jugadas** (Souttar —es de Escocia, Rangers— errático; **Gunn no domina el área**), 9 GA en quali. Goles puros de córner/FK **no confirmados** → la fuga es por banda/abierto; bloque compacto mitiga.
- **Chequia 🟡.** **5-3-2 con marca AL HOMBRE** → expone en 1v1 (los arrastra fuera de posición). Paradoja: **élite atacando ABP, no defendiéndolo**; Croacia le hizo 5 (cabezazo + gol de córner de Modrić), **17 GA en quali**. **Jaroš lesionado → Staněk**. Krejčí (CB) decente aéreo.
- **Suecia 🔴.** **12-13 GA en quali, 0 porterías a cero**; prensa cita explícitamente **"defensa de balón parado ineficaz"** + fallo de marca al **segundo palo** (2-0 de Świderski); **Nordfeldt cuestionado**. Muestra chica bajo Potter, pero el historial es de hemorragia. El más vulnerable de UEFA.
- **Turquía 🟡.** Fragilidad defensiva **general** confirmada (0-6 España) pero ese fue **transición**, no ABP estática; mecanismo histórico de **mal marcaje/posición en el área** (Euro 2024) → sufre ante targetman aéreo. CBs Demiral/Bardakcı; Çakır GK sólido.
- **Bosnia 🟡.** **🔴 CORRIGE §6.7: el 26 final NO lleva a Ahmedhodžić ni Bišćan** → CBs reales **Katić (Schalke) + Muharemović (Sassuolo)**, Kolašinac de LI. Físicos compiten el aire, pero **Vasilj flojo saliendo** (su error regaló el 1-0 a Italia) y caen por **fatiga/edad** en bandas.

#### CONMEBOL (la más sólida en el aire; el vector suele ser el PORTERO, no el CB)

- **Argentina 🟢.** Marca **individual disciplinada**; **Romero/Otamendi dominan el aire** (Otamendi cede ritmo, no el duelo). **Dibu se queda en línea** → la 6 yardas la cubren los CBs. ~1 GA en sus últimos 5; vector de córner-en-contra **bajo**. Riesgo = transición, no ABP.
- **Brasil 🟢.** **Marquinhos (1.83 pero 65% de duelos aéreos) + Gabriel Magalhães** sólidos; **Alisson sale bien** a centros. El 4-1 vs Argentina fue **juego abierto/error**, no ABP. Sin Militão NO agrava el aire. Riesgo de Brasil-contra = laterales/transición.
- **Uruguay 🟢.** **Araújo + Giménez = eje aéreo élite**; 0 goles de ABP en los amistosos pre-WC. Único matiz: **Muslera cumple 40 durante el torneo y su titularidad no está garantizada** (Rochet, titular de la quali, también va); salida a centros por confirmar.
- **Colombia 🟡** (→ 🔴 vs especialista de córner). CBs **Davinson + Lucumí** grandes ganan el duelo directo, **pero el agujero es el portero**: **Camilo Vargas no domina su área** → Matanović cabeceó un **córner de Pašalić** para el 2-1 de Croacia (mar-26). Vector = GK en centros; re-verificar si juega Ospina.
- **Ecuador 🟢** (matiz 🟡 micro-ABP). **Pacho + Hincapié** élite, sin grieta aérea estructural. PERO **su único gol reciente encajado fue de ABP** (vs Marruecos; el capitán-CB Pacho lo admitió: "hay que corregir") y **Galíndez (38) no domina alto** → micro-edge en córner-rival/scorer-de-ABP, no en juego abierto.
- **Paraguay 🟢.** **Fortaleza aérea pura: Gustavo Gómez + Alderete** (colosos) dominan ambas áreas; 10 GA en 18, sin goles de córner/FK recientes (los 2 vs Marruecos fueron de jugada). **Atacarlos por ABP = ir a su mejor terreno** → ángulo es contra-córner / under, NO header rival.

#### CONCACAF (anfitriones frágiles; vector frecuente = portero pasivo + segundas jugadas)

- **México 🔴.** **🔴 CORRIGE §6.7: Malagón LESIONADO y FUERA → titular Raúl "Tala" Rangel (Chivas)** (Ochoa relevo); Araujo no convocado. Evidencia dura: en el **0-4 vs Colombia, 2 de 4 goles fueron de ABP** (Lucumí de cabeza con el GK clavado bajo el arco + Lerma de set-piece) → marca individual perdida + portero pasivo a centros. **Rangel sin rodaje en este escenario** = incógnita. Salida-desde-atrás explotable agrava.
- **EE.UU. 🟡.** Sin **Richards** (su mejor defensor aéreo de ABP, duda tobillo) baja el techo. Pareja **McKenzie + Ream (37)** lenta, pero la fragilidad PROBADA es **en transición** (los 7 goles recientes y el doblete de Mané fueron de pérdidas/jugada, no córner). Riesgo aéreo latente, no edge demostrado en ABP.
- **Canadá 🟡.** Bloque sólido (**solo 2 goles de ABP en 15**) PERO cede **42.5% de córners-en-contra convertidos en remate** (señal reactiva) y **St. Clair fue batido de cabeza** (Rubín, Gold Cup); portero no dominante en el aire → ventana de segunda jugada. CBs (Vitória/Cornelius/Bombito) no señalados como débiles.
- **Panamá 🟡** (→ 🔴 vs élite aérea). **Córdoba (CB ancla): los duelos aéreos son su DEBILIDAD per scouting**; **Mosquera (GK) errático** (regaló penal vs Brasil). En el 6-2 vs Brasil: cabezazo libre de Casemiro + desvío de FK + penal del GK. Sólido vs pares CONCACAF, explotable por córner/FK ante calidad aérea (Inglaterra/Croacia, su grupo).
- **Curaçao 🔴.** Zaga neerlando-caribeña **modesta, sin gigante aéreo**; **Eloy Room (37) no domina el área**. Cedió **cabezazos vs Australia (1-5)** y **set-piece ensayado vs Escocia (1-4)** en sus 2 últimos (ojo: vs Escocia jugó 52' con 10). El "5 GA" de la quali está **caducado** → córner/header-anytime del rival + team-total rival.
- **Haití 🟡.** Defensa globalmente porosa (**13 GA en quali**) pero CBs (Lacroix/Delcroix) **físicos y capaces en el aire**; concesión ABP concreta = **córner de Ugalde al 92' vs Costa Rica** (3-3). Portero **Placide (38)** sin dato de salidas (la edad invita cautela). No 🔴 sin más muestra de patrón aéreo.

#### CAF (ojo: la solidez en juego abierto NO garantiza solidez a ABP — ver Marfil/Argelia/RSA)

- **Sudáfrica 🔴.** **Debilidad ABP CONFIRMADA por el propio Broos** ("si seguimos defendiendo así, encajaremos cada partido"). **AFCON R16 vs Camerún: AMBOS goles de córner** (rechace mal despejado + cabezazo de Kofane); 16 GA en 9, "buena parte de balón parado". **R. Williams élite parando pero NO domina el área en centros** (cede el primer despeje). → córner/Over-córners rival, **cabezazo-anytime de CB rival, BTTS-Sí**. El más explotable de CAF a ABP.
- **Argelia 🟡→🔴.** Aérea **"bullyable" CONFIRMADA**: en QF AFCON **Osimhen cabeceó de córner** el 1-0 (0-2, eliminados); **Luca Zidane (debut) no salió a cortar el centro**. Faltosa (14.6/p) → regala FK en zona. Edge para **córner/FK rival + cabeza del rival como scorer** (delanteros de salto).
- **Costa de Marfil 🟡.** Élite en JUEGO ABIERTO (0 GA en quali) **pero grieta ABP real**: en AFCON QF **2 de 3 goles vs Egipto fueron de ABP** (Rabia cabeceó córner de Salah; FK previo al caos). **Kossounou se cayó en vez de cortar** y **Fofana (GK) no sale a centros**. CBs Kossounou+N'Dicka (Boly fuera). No es la fortaleza-a-balón-parado que el "0 encajados" sugiere.
- **Marruecos 🟡** (edge hipotético, no medido). **🔴 CORRIGE §6.7: Saïss se retiró (feb-26)** → desaparece el ancla aérea; **Aguerd con duda física** (pubalgia, sin jugar desde marzo) → pareja CB **inédita** (El Yamiq 33 lento/Masina/Diop); el CB ya fue señalado débil en la final de AFCON. Bono sin dato de salidas. Sin evidencia directa de goles ABP bajo Ouahbi → riesgo por reconstrucción, no confirmado.
- **Senegal 🟡.** **🔴 CORRIGE §6.7: Koulibaly (35) NO está confirmado** (rotura muscular de 2º grado, baja desde abril; Thiaw no garantizó disponibilidad) → eje posible improvisado (**Niakhaté + Seck/M. Sarr**, menos jerarquía aérea). Mitiga que **É. Mendy SÍ domina el área** y sale a centros. Sin patrón de fuga ABP documentado.
- **Ghana 🟡.** **Salisu (mejor CB, ancla aérea) FUERA por LCA** + zaga a reconstruir (Djiku/Mumin; **Amartey NO convocado**) → fragilidad aérea estructural plausible, PERO la evidencia 2025-26 (0-2 México, 0-2 Gales) muestra que concede en **transición/presión, no de ABP**. Tilt MODESTO a rival-anota-de-ABP, no convicción. GK sin nivel élite.
- **Egipto 🟢.** **🔴 CORRIGE §6.7: Hegazi FUERA del 26** → CBs Abdelmonem (post-ACL, ritmo a confirmar) + Yasser Ibrahim/Rabia. **2 GA en 10 / 7 vallas** en quali, sin patrón de fragilidad aérea; GK en disputa (Shobeir/El Shenawy), ninguno reputado por dominar centros. No es objetivo ABP-en-contra.
- **Túnez 🟢.** **Talbi (cabeceador) + Bronn** sólidos por arriba, **Dahmen manda el área**; clasificó **sin encajar (récord)**, 0-0 Canadá / 1-0 Haití bajo Lamouchi. Matiz: n bajo era-Lamouchi + cayó vs **Mali en R16 AFCON** (bajo presión real). Sin fuga ABP documentada.
- **Cabo Verde 🟢.** La **defensa fue su ARMA** (5/5 en casa sin encajar en quali); el 2-4 vs Chile fue **juego abierto + 45' con uno menos** (no ABP); CBs "fuerza aérea + posición", **Logan Costa** referencia, Vozinha firme. Sin debilidad ABP conocida. Caveat: el salto de nivel del Grupo H (España/Uruguay) es presión general, no grieta ABP.
- **RD Congo 🟢.** Bloque compacto top, **Mpasi (GK) sale bien al área**, **Mbemba ancla**; AFCON 1 gol en fase de grupos, repechaje 0 GA, **0.4 GA** últimos 5. Sin fragilidad ABP demostrable → atacarlo por balón parado no tiene valor; mercado defensivo (Under/portería-a-cero/BTTS-No) lo respalda.

#### AFC + OFC

- **Corea del Sur 🔴.** **Back-3 EXPONE** (prensa pide back-4); en el colapso **0-4 vs Costa de Marfil encajó tras córner** (rebote, GK no despeja). Solo **Kim Min-jae** es ancla aérea confirmada; los otros 2 CB y el GK (disputa Kim Seung-gyu/Jo) **sin confirmar**. Edge claro para **córner/header en contra** con buen servicio + rematador alto.
- **Catar 🔴.** **Poca estatura, sin CB mandón en el área**; **Barsham (GK) no domina centros**. Evidencia fresca: **Irlanda 1-0 (28-may) = córner + cabezazo de Collins al min 5**. Laterales "workmanlike" expuestos. → córner/cabezazo-en-contra y **team-total rival al alza**.
- **Japón 🟡.** **Relativamente bajo** (concern aéreo que NED/SWE apuntarán con tamaño), PERO **Zion Suzuki (1.90) domina su área** y la organización zonal es élite (**3 GA en 16**). Atacable solo con **servicio de calidad + 9 alto**, no sistémico.
- **Arabia Saudí 🟡.** El fallo dominante es **transición** (línea alta batida: 0-4 Egipto, 1-2 Serbia), no ABP; única señal ABP = header de córner de **Porozo vs Ecuador**. CBs (Al-Tambakti/Lajami) físicos. Inestable por DT nuevo (Donis), sin portería a cero en 6.
- **Jordania 🟡.** Bloque bajo sólido (**2 GA en 5 del Arab Cup**) pero **concedió el gol decisivo de ABP en la final vs Marruecos** (chilena de Saadane tras set-piece). **Abu Laila (GK) no domina el área**. Set-piece es su grieta real bajo presión sostenida (Grupo J: ARG/ALG/AUT).
- **Irak 🟡.** **Marca al hombre + CBs altos (1.96-1.97)** mitigan, pero **Jalal Hassan (GK) no domina el área** y **Haquin casi empata de córner vs Bolivia** (aviso). Vulnerabilidad real no probada vs el servicio del Grupo I (FRA/SEN/NOR).
- **Nueva Zelanda 🟡.** Dominan el aire en **ATAQUE** (Wood) pero **no lo trasladan a defensa** (encaje ABP por desorganización vs Finlandia); **Crocombe no transmite dominio de área**. **🔴 CORRIGE §6.7: Tuiloma FUERA** → CBs reales Bindon/Boxall/Pijnaker/Surman/Smith (eje joven). Encajes recientes más de juego abierto → 🟡 no 🔴.
- **Irán 🟢.** **Alto/físico**, **Beiranvand domina el área** y sale a centros; sin ABP encajado en 2025-26 (los 2 de Nigeria fueron jugada). **🔴 CORRIGE §6.7: CBs = Khalilzadeh + Kanaanizadegan** (no Pouraliganji/Mohammadhosseini). ABP-en-contra es de sus rutas MENOS productivas.
- **Australia 🟢.** **La ABP defensiva es FORTALEZA, no debilidad:** **Souttar/Burgess/Circati = torres** que dominan ambas áreas; 2ª ronda quali **6/6 sin encajar**. El edge es **ofensivo** (Souttar a balón parado a favor), NO atacar su área.
- **Uzbekistán 🟢.** **🔴 CORRIGE §6.7 ("Khusanov corto de ritmo"): el pace de Khusanov es FORTALEZA** (la duda es fitness, no ritmo); zaga física **defiende bien el aire** y su dominio aéreo es arma ofensiva. El hueco real es **espacio a la espalda de laterales**, no ABP. 7 GA en quali.

### Síntesis #4 — roster de ratings + mismatches (aéreo × vulnerable)

**Vulnerables 🔴 (atacar por córner/FK; cabezazo-en-contra, Over-córners rival, BTTS-Sí):**
Suecia · México · Curaçao · Corea del Sur · Catar · Sudáfrica. **Condicionales (🟡→🔴 vs especialista):**
Panamá (Córdoba+Mosquera) · Argelia (bullyable+L.Zidane) · Colombia (Vargas en córners).

**Medio 🟡:** Inglaterra, Francia, Portugal, Países Bajos, Bélgica, Noruega, Escocia, Chequia, Turquía, Bosnia,
EE.UU., Canadá, Haití, Marruecos, Senegal, Ghana, Jordania, Irak, Japón, Arabia Saudí, Nueva Zelanda.

**Fuertes 🟢 (NO atacar por aire; respaldan Under/portería-a-cero rival):** España, Alemania, Croacia, Suiza,
Austria, Argentina, Brasil, Uruguay, Ecuador, **Paraguay** (su mejor terreno), Egipto, Túnez, Cabo Verde,
RD Congo, Irán, **Australia**, Uzbekistán.

**Equipos-deliverer (ataque aéreo/ABP fuerte = el lado que explota un 🔴):** Chequia (más goles ABP de Europa;
Schick/Souček/Krejčí) · Alemania (28% de goles de ABP) · Inglaterra (pizarra, aunque sin Maguire) · Noruega
(Haaland aéreo) · Australia (Souttar/Burgess) · Costa de Marfil (Kessié) · Paraguay (Gómez/Alderete) · Colombia
(Davinson/Mina) · Senegal (artillería al 2º palo, si Koulibaji llega) · Escocia (McTominay).

**🎯 MISMATCH PRIME (pareo confirmado por grupo): GRUPO A.** Las **tres** rivales de Chequia son 🔴 a balón
parado — **México 🔴, Sudáfrica 🔴, Corea del Sur 🔴** — y **Chequia es el ataque #1 de ABP de Europa**. Es el
cruce aéreo-vs-vulnerable más limpio del torneo: priorizar **córner→gol / cabezazo de Schick-Souček-Krejčí /
Over-córners de Chequia** en sus tres partidos (y, en los Chequia-fuera, los tres 🔴 también se castigan entre sí).

> Recordatorio: rating cualitativo (no hay xGA-ABP público de selecciones). Cruzar SIEMPRE con (a) el XI/GK del
> día — varios vectores son el **portero** (Vargas, Galíndez, Mosquera, Barsham, Hassan, Crocombe, Williams) — y
> (b) el árbitro (mejora #3, pendiente) para el componente de córners concedidos.

---

## 6.9 — Capa de jugador para props (jun-2026)

> **Qué es.** Mejora B (Tier-1). Nombres concretos para los **mercados de props (los más blandos)**, en 3
> categorías que complementan los penalty/FK/córner-takers de §6.7 y los mismatches de §6.8: **Aéreo**
> (rematador de cabeza — el que ejecuta el mismatch aéreo), **Card-prone** (acumula amarillas — cruzar con
> TA/p de §6.6 y árbitro #3), **Foul-drawer** (regateador al que le hacen faltas → genera FK/tarjeta rival).
>
> **Honestidad:** muchos campos son **cualitativos por rol** (las cifras exactas de faltas-recibidas/amarillas
> por jugador 2025-26 no siempre se verifican → marcado "n/d", NO inventado). El cuello de botella de props
> es la **CUOTA, no el dato** ([[project_player_props_and_data_research]]) → pedir cuotas reales, no recitar EV.

#### UEFA
- **Inglaterra** — Aéreo: **Kane** (+Bellingham llega de 2ª línea); sin Maguire, banquillo aéreo nulo. Card-prone: **Rice** (3 amarillas PL, pivote). Foul-drawer: **Saka, Madueke**.
- **Francia** — Aéreo: **CBs Saliba/Upamecano/Konaté** (sin 9 aéreo; Mbappé NO). Card-prone: **Tchouaméni, Koné** (pivotes de corte). Foul-drawer: **Mbappé, Dembélé, Doué**.
- **España** — Aéreo: **Merino** (remató 3, de cabeza, en el 6-0 a Turquía) + CBs. Card-prone: n/d. Foul-drawer: **Yamal** (líder de regates LaLiga ~5/p), **Nico Williams**, Pedri.
- **Alemania** — Aéreo (clave por 28% ABP): **Tah, Rüdiger, Anton, Schlotterbeck** + Havertz al 1er palo. Card-prone: **Kimmich** (4 BL, time-wasting; tasa de falta baja). Foul-drawer: **Musiala** (si va), **Wirtz**.
- **Portugal** — Aéreo: **Ronaldo** (41, sigue rematando), **Gonçalo Ramos**. Card-prone: **Palhinha** (5 PL), **Leão** (5 Serie A). Foul-drawer: **Leão** (34 faltas recibidas, 38 regates).
- **Países Bajos** — Aéreo: **Van Dijk**, **Weghorst** (target si entra; sin De Ligt baja). Card-prone: n/d (perfil De Roon). Foul-drawer: **Gakpo, Malen**.
- **Bélgica** — Aéreo: **Lukaku** (¿forma/minutos?), **De Ketelaere**. Card-prone: **Onana** (3 PL, pivote físico). Foul-drawer: **Doku** (líder de regates PL — el más fiable), Trossard.
- **Croacia** — Aéreo: **Budimir** (17 goles LaLiga), Musa. Card-prone: **Brozović** (7), **Modrić** (4 Serie A). Foul-drawer: **Baturina**.
- **Suiza** — Aéreo: **Embolo**, Akanji/Elvedi en ABP. Card-prone: **Xhaka** (líder de faltas/amarillas BL, juega al límite), Freuler. Foul-drawer: **Ndoye, Vargas**.
- **Austria** — Aéreo: **Arnautović, Kalajdžić** (~2.00m), Gregoritsch. Card-prone: **Sabitzer, Laimer** (presión→falta táctica; cifra n/d). Foul-drawer: n/d.
- **Noruega** — Aéreo (clave): **Sørloth** (195cm, 4 goles de cabeza 25-26) + **Haaland** (194cm). Card-prone: **Ryerson** (4 amarillas/8), Berge. Foul-drawer: **Nusa** (56 faltas recibidas BL).
- **Escocia** — Aéreo (su edge ABP): **McTominay** (llega de 2ª línea), **Souttar/Hendry** (CBs), Adams, Shankland. Card-prone: **McGinn** (5 PL). Foul-drawer: **Doak**.
- **Chequia** — Aéreo (MUY clave, ataque ABP nº1 Europa): **Schick, Souček, Krejčí** (CB, anotó ABP en playoffs), Hložek. Card-prone: **Souček, Krejčí** (físicos). Foul-drawer: n/d (plantel vertical).
- **Suecia** — Aéreo: **Gyökeres**, **Lagerbielke** (CB, cabeceó vs Polonia), Isak si entra. Card-prone: n/d. Foul-drawer: **Gyökeres, Elanga**.
- **Turquía** — Aéreo: **Demiral** (CB, 2 goles ABP en 2025), Akaydın. Card-prone (clave, TA 2.6): **Yüksek, Çalhanoğlu, Çelik** (amonestados en el playoff físico vs Kosovo). Foul-drawer: **Güler, Yıldız**.
- **Bosnia** — Aéreo: **Demirović** (30 duelos ganados, 12 goles), Džeko si parte. Card-prone (clave, faltas 14.8/TA 2.3): **Kolašinac** (3 TA Serie A), Tahirović, Demirović (5 BL). Foul-drawer: **Demirović** (34 faltas recibidas).

#### CONMEBOL
- **Argentina** — Aéreo: **Otamendi** (73.7% duelos aéreos en Mundial de Clubes); **⚠️ Romero duda (rodilla, fuera resto 25-26)** — era el otro CB aéreo. Card-prone: **Romero** (10 TA + 2 rojas PL → top card-prop **si llega**); De Paul moderado. Foul-drawer: **Nico Paz**; Messi n/d.
- **Brasil** — Aéreo: **Marquinhos, Gabriel Magalhães** + Igor Thiago (área). Card-prone: **Casemiro** (9 TA + 1 roja PL 25-26 + entradas temerarias con Brasil). Foul-drawer: **Vinícius, Raphinha** (Rodrygo FUERA; Neymar dudas de fitness).
- **Uruguay** — Aéreo: **Araújo, Giménez** (élite) + Núñez/Valverde (llega). Card-prone (TA 2.3): **Ugarte, Bentancur** (pivotes), Araújo (última línea agresiva). Foul-drawer: **Pellistri, Núñez**.
- **Colombia** — Aéreo (clave, deliverer): **Davinson Sánchez, Yerry Mina** (~4.2 aéreos/90), Córdoba (9). Card-prone (faltas 13.1): **Lerma** (7 TA, 29 faltas/34 en Palace). Foul-drawer: **Luis Díaz, Jhon Arias**.
- **Ecuador** — Aéreo: **Hincapié, Pacho, Félix Torres** + E. Valencia. Card-prone (faltas 12.7): **Caicedo** (líder del equipo: 3A+1R en quali, 2.1 faltas/90). Foul-drawer: **Kendry Páez, Plata**.
- **Paraguay** — Aéreo (clave, deliverer): **Gustavo Gómez, Alderete, Balbuena**; cabeza recientes **Alderete** (vs ARG), **Galarza** (vs URU). Card-prone (TA 2.2): **Cubas** (7 TA en 2025 + 5 en 864' de 2026 = ritmo muy alto), J. Alonso (4). Foul-drawer: **Almirón** (Enciso ya es FK/penal).
#### CONCACAF
- **México** — Aéreo: **Johan Vásquez** (53% duelos aéreos Serie A), Montes. Card-prone: **Edson Álvarez** (4 TA/12 Süper Lig, 2.58 faltas/90) si va. Foul-drawer: **Vega, César Huerta** (cifra n/d).
- **EE.UU.** — Aéreo: **Ream, McKenzie** + Balogun/Pepi. Card-prone: **Tyler Adams** (8 TA PL Bournemouth), **McKennie** (suspensión por amarillas en Juve). Foul-drawer: **Pulisic, Weah, Tillman**.
- **Canadá** — Aéreo: **Larin, Bombito** (CB). Card-prone (equipo físico, 14.0/TA 2.2): **Koné** (3 TA + 1 roja, expulsado en debut Sassuolo), Eustáquio. Foul-drawer: **Ahmed, Buchanan, Shaffelburg**; Davies si juega.
- **Panamá** — Aéreo: **Andrade, Cedeño** (llegada); CB-header n/d firme (Córdoba marcó pese a aéreo flojo). Card-prone: **Godoy** (físico, amarilla vs RSA). Foul-drawer: **J.L. Rodríguez, Cristian Martínez** (15 faltas recibidas) — Carrasquilla excluido (FK).
- **Curaçao** — Aéreo: **Janga** (9); CBs n/d. Card-prone: **Leandro Bacuna** (4 TA en 1.Lig). Foul-drawer: **Chong**.
- **Haití** — Aéreo: **Isidor** (Wilson, Sunderland), Pierrot; CBs **Duverne/Delcroix** (⚠️ "Lacroix" es carrilero, no CB). Card-prone: **Duverne** (4 TA Pro League). Foul-drawer: **Étienne Jr.** (Bellegarde excluido, FK).
#### CAF
- **Marruecos** — Aéreo: **El Kaabi** (9), Aguerd (CB). Card-prone: **Amrabat** (pivote físico), Ounahi. Foul-drawer: **Hakimi, Brahim Díaz**.
- **Senegal** — Aéreo (clave, deliverer): **Niakhaté**, Koulibaly (si va), **N. Jackson**, P.M. Sarr (llega). Card-prone (físico "limpio": faltas 14.5 / TA 1.6): **Gana Gueye, Pape Gueye** (pivotes). Foul-drawer: **Ismaïla Sarr, Mané, I. Ndiaye**.
- **Egipto** — Aéreo: **Abdelmonem** (post-ACL), Yasser Ibrahim, Marmoush. Card-prone: **Trezeguet** (4 TA/21, 1.44 faltas/90), Abdelmagid. Foul-drawer: **Trezeguet**.
- **Argelia** — Aéreo: **Mandi**, Gouiri, Bensebaïni (córner). Card-prone (TA 2.1): **Zerrouki, Bentaleb** (pivotes), Bensebaïni (Bennacer FUERA). Foul-drawer: **Amoura, Chaïbi** (Mahrez excl., FK).
- **Túnez** — Aéreo: **Talbi** (CB, 71% duelos aéreos), Bronn. Card-prone: **Skhiri** (1 TA + 1 roja BL). Foul-drawer: **Hannibal Mejbri** (2º mejor regateador AFCON 2025).
- **Costa de Marfil** — Aéreo: **N'Dicka, Diomandé** (CBs), Guessand (9). Card-prone (faltas 14.4): **Kessié** (perfil físico; cifra exacta n/d), Seri. Foul-drawer: **Amad Diallo, Pépé**.
- **Ghana** — Aéreo: **Djiku, Mumin** (CBs); **⚠️ Iñaki Williams débil aéreo (46.9%)** → mejor como foul-drawer. Card-prone: **Djiku** (5 TA + 1 roja 25-26; **⚠️ Partey LIMPIO, 1 TA/21 — NO es él**). Foul-drawer: **Semenyo** (52 regates), **Iñaki Williams** (23 faltas recibidas).
- **Cabo Verde** — Aéreo: **Logan Costa** (CB, **⚠️ post-LCA, ritmo en duda**), R. Lopes, Livramento (9). Card-prone: **Kevin Pina** ("destroyer"; cifra n/d). Foul-drawer: **Garry Rodrigues, Jovane Cabral**.
- **Sudáfrica** — Aéreo: **Ngezana, Mbokazi, Sibisi** (CBs; **⚠️ NO Mvala/Mbatha — Mbatha es MC**), Foster (9). Card-prone: **Mokoena** (pivote, amonestado vs Egipto + historial). Foul-drawer: **Mofokeng, Appollis** (jóvenes de banda).
- **RD Congo** — Aéreo: **Mbemba** (CB), Bakambu (9). Card-prone: **Wan-Bissaka** (2 TA PL, lateral físico), Mbemba. Foul-drawer: **Wissa, Mbuku**.

---

## 7. Fuentes

**Tier 1 — educadores de entrenadores / cuerpos técnicos:**
- The Coaches' Voice — 4-2-3-1: https://learning.coachesvoice.com/cv/the-4-2-3-1-football-tactics-pochettino-guardiola-flick-southgate/
- The Coaches' Voice — 4-3-3: https://learning.coachesvoice.com/cv/4-3-3-football-tactics-explained-formation-liverpool-klopp-barcelona-guardiola/
- The Coaches' Voice — 4-1-4-1: https://learning.coachesvoice.com/cv/4-1-4-1-formation-football-tactics-explained/
- The Coaches' Voice — 4-4-2: https://learning.coachesvoice.com/cv/4-4-2-football-tactics-ferguson-simeone-hasenhuttl-dyche/
- The Coaches' Voice — back three: https://learning.coachesvoice.com/cv/back-three-explained-why-conte-moyes-guardiola/
- The Coaches' Voice — 3-5-2: https://learning.coachesvoice.com/cv/3-5-2-formation-conte-mourinho-guardiola/
- The Coaches' Voice — 3-4-3: https://learning.coachesvoice.com/cv/3-4-3-formation-football-tactics-explained-tuchel-conte-pochettino-southgate/
- The Coaches' Voice — wing-backs: https://learning.coachesvoice.com/cv/wing-backs-football-tactics-explained-conte-tuchel/
- The Coaches' Voice — 4-4-2 diamond: https://learning.coachesvoice.com/cv/4-4-2-diamond-football-tactics-explained-klopp-potter-allegri/
- Premier League — 4-4-2 diamond: https://www.premierleague.com/en/news/4243786/the-4-4-2-diamond-football-tactics-explained
- Premier League — 3-4-3: https://www.premierleague.com/en/news/4244194
- The FA / England Football Learning — wing-back en línea de 5: https://community.thefa.com/coaching/b/insights-analysis-blogs/posts/the-pressing-role-of-the-wing_2d00_back-in-a-back-five

**Tier 2 — analistas tácticos:**
- Spielverlagerung — pressing traps en 3-4-3: https://spielverlagerung.com/2020/04/08/pressing-traps-available-in-a-3-4-3/
- Spielverlagerung — Liverpool pressing: https://spielverlagerung.com/2019/05/09/liverpools-pressing-system/
- The Football Analyst — 3-2-5: https://the-footballanalyst.com/what-makes-the-3-2-5-so-effective-in-modern-football/
- The Football Analyst — 5-4-1: https://the-footballanalyst.com/defending-in-the-5-4-1-a-complete-tactical-guide/
- The Football Analyst — attacking fullbacks: https://the-footballanalyst.com/attacking-fullbacks-football-tactics-explained/
- Total Football Analysis — presión en 3-4-3 (Amorim): https://totalfootballanalysis.com/analysis/tactical-theory-the-practicality-of-pressing-in-a-3-4-3-and-how-to-coach-it-tactical-analysis
- Total Football Analysis — pressing variations en 4-2-3-1: https://totalfootballanalysis.com/article/tactical-theory-pressing-variations-within-4231-tactical-analysis-tactics
- Michael Cox (Zonal Marking) — Q&A 4-1-4-1: https://www.chicagofirefc.com/news/what-4-1-4-1-qa-zonal-markings-michael-cox-between-lines

**Empírico (la parte cuantificada):**
- Ruiz-Menárguez & Badiella — Double Machine Learning, 22k+ partidos (posesión/córners/goles/tarjetas): https://arxiv.org/abs/2602.16830  ⚠️ magnitudes solo del abstract
- Competing-risk survival, formación → goles (hazard ratios), 8 torneos: https://pmc.ncbi.nlm.nih.gov/articles/PMC11208451/
- Ashimolowo — match-status → córners (el que pierde recibe más córners): https://ninercommons.charlotte.edu/record/504/files/Ashimolowo_uncc_0694N_11959.pdf
- Match status & posesión (UCL): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4120454/

**Overlay por selección (2024-2026):** ver URLs en el research; principales: Coaches' Voice (España final Euro 2024), ESPN/Marcotti, Total Football Analysis (Argentina Copa, Francia Euro, Brasil Ancelotti data), SofaScore (Ancelotti), World Soccer Talk, FIFA, UEFA, Football-España.

**Banderas de honestidad (importante para no sobre-ajustar):**
- **Ningún source fiable atribuye un patrón de balón parado específico a una formación.** La única
  correlación legítima es indirecta (línea de 3/5 = más cuerpos aéreos en el área; 4-4-2 bajo = reclutar
  delanteros aéreos). **No inventar** una ventaja de balón parado por dibujo.
- **Tarjetas: la formación es empíricamente inerte.** No usar como feature de cards.
- El 4-4-1-1 es la formación peor documentada (sin página tier-1; tratada como 4-2-3-1 sin balón).
- Las traducciones a mercado son en su mayoría **inferencia** sobre mecanismos tácticos sourced —
  tratar como *priors* de peso bajo a validar contra datos propios, no como hechos.
