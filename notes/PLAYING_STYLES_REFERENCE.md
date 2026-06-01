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
