# Errores aprendidos — Fútbol

Cada vez que el usuario corrija un pick o identifique un error de análisis, documentar aquí con fecha, contexto y lección. Esta sección crece con la experiencia.

---

## 2026-04-05 — Error #1: Aggregate Stat Seduction

**Contexto:** Analizando Cúcuta Deportivo vs América de Cali (Liga BetPlay), recomendé Over 2.5 goles @ 2.25 basándome principalmente en que Cúcuta tenía 1.80 GA/P en la temporada.

**Qué hice mal:**
- Tomé una stat agregada impactante (Cúcuta defensa entre las peores) y construí la narrativa sobre ella.
- Ignoré que los últimos 5 partidos de Cúcuta fueron: 0-0, 1-0, 2-2, 2-2, 0-2 → promedio solo 2.2 goles/P.
- Los últimos 5 de América: 2-0, 2-1, 0-0, 1-0, 1-1 → promedio solo 1.6 goles/P.
- **Promedio combinado reciente: 1.90 goles/P, BAJO la línea 2.5**.
- También ignoré que el line movement iba hacia Under (Over se alargó de +110 a +125 = money en Under).

**Consecuencia:** Pick con EV real negativo (~-5.5%) presentado como EV positivo (~+8-17%). El usuario me corrigió señalando que la mayoría de partidos recientes terminaron Under.

**Lección:**
> Una stat agregada impresionante (como GA/P de temporada) puede ser engañosa sin contraste temporal. Equipos ajustan defensiva/ofensivamente durante temporada. **Siempre cruzar agregado con forma reciente real de los partidos.**

**Regla añadida al Paso 7:** calcular `recent_avg_goals` combinado de últimos 5 partidos de cada equipo ANTES de apostar Over/Under. Si contradice la línea, necesitas evidencia extraordinaria para apostar en contra del promedio reciente.

**Señal de alerta temprana:** Si al construir el caso del pick solo tengo UNA stat fuerte a favor y todo lo demás es neutral o en contra, probablemente estoy pescando edge donde no hay.

---

## Patrón general de errores en picks Over/Under

Cuando un pick Over falle por este patrón, revisar si:
1. El promedio reciente combinado soportaba la hipótesis
2. El line movement iba a favor o en contra
3. Usé stat agregada de temporada sin verificar forma reciente
4. El H2H reciente (si existe y es actual) soportaba la hipótesis

Si 2+ de estas señales iban en contra, el pick no debió ocurrir.

---

## 2026-04-05 — Aprendizaje #2: Bajas defensivas múltiples = ajuste agresivo de goles rival

**Contexto:** Mismo partido Cúcuta vs América de Cali. Tras corregir el error #1, aposté BTTS No @ 1.80 (EV +8%) y gané. Descarté Under 2.5 @ 1.63 (EV +1.06%, bajo umbral) y Doble Oportunidad X2 @ 1.21 (EV negativo). El proceso funcionó: +1.00u neto y evitamos pérdida en X2.

**Qué observé:**
- América viajaba sin 2 centrales titulares (Nicolás Hernández rodilla + Jan Lucumí ligamentos).
- Identifiqué esto como riesgo en el contra-argumento y bajé el stake de BTTS No a 1.25u en vez de 2u.
- Pero NO ajusté numéricamente mi estimación de goles de Cúcuta por esas bajas. Mantuve la prob. de BTTS No en 60%.
- Resultado: Cúcuta metió 2 goles (por encima de su avg reciente de 1.4/P), América 0. BTTS No ganó, pero la estimación de goles de Cúcuta fue conservadora.

**Lección:**
> Cuando un equipo tiene **2+ bajas en la misma línea** (especialmente defensa central), el ajuste no debe ser solo cualitativo ("lo anoto como riesgo"). Debe ser cuantitativo: subir la estimación de goles del rival en +0.3 a +0.5 goles/P respecto a su promedio reciente. Dos centrales fuera desorganizan toda la estructura defensiva, no es lo mismo que perder un lateral + un mediocampista.

**Regla operativa:**
- 1 baja defensiva titular → ajuste +0.1-0.2 goles/P al rival
- 2 bajas en misma línea (ej: pareja de centrales) → ajuste +0.3-0.5 goles/P al rival
- Aplicar este ajuste ANTES de calcular probabilidades de Over/Under y BTTS

**Validación del proceso:**
- EV calculator descartó correctamente Under 2.5 (edge real insuficiente con cuota del usuario)
- EV calculator descartó correctamente X2 (EV negativo → habría sido pérdida de 1u)
- BTTS No capturó el edge real: América sin gol visitante + Cúcuta anotando contra defensa rota

---

## 2026-04-06 — Error #3: Parlay completo fallido (3/3 patas perdidas)

**Contexto:** Parlay de 3 patas para el lunes 6 de abril:
1. Gol en 1H Napoli vs Milan @ 1.40 — PERDIDA
2. Villarreal ML @ 2.25 (Girona vs Villarreal) — PERDIDA
3. Benfica gana 1H @ ~1.75 (Casa Pia vs Benfica) — PERDIDA

### Error A: Motivación mal leída (Napoli vs Milan)

**Qué hice:** Asumí que "2do vs 3ro, 1 punto de diferencia" = partido abierto y agresivo. Construí todo sobre el stat de 13/13 partidos de Napoli con gol antes del HT en casa.

**Qué pasó en realidad:** Inter lideraba por 9 puntos (72 vs 63/62). El Scudetto estaba decidido. Napoli y Milan peleaban entre sí por el 2do puesto, donde **un empate no perjudicaba a ninguno** — ambos mantenían posiciones relativas. Perder era el único resultado catastrófico → incentivo a NO arriesgar, especialmente en primera parte.

**Lección:** Confundí "partido grande" con "partido abierto". Los partidos grandes entre equipos donde el empate sirve a ambos son precisamente los más cautelosos. El 13/13 era contra rivales donde Napoli NECESITABA ganar.

### Error B: Confirmation bias + stats descontextualizadas (Girona vs Villarreal)

**Qué hice:** Me enamoré de la cuota (2.25 "parece value") y busqué datos que confirmaran: H2H desde 2012, el 5-0 de agosto, away win rate de 43%. Descarté que Girona peleaba descenso de local.

**Qué pasó en realidad:** Un equipo a 5-6 puntos del descenso jugando en casa en abril no es el mismo de septiembre. La desesperación + afición local = multiplicador que las stats de temporada no capturan. H2H de más de 2-3 temporadas es ruido puro.

**Lección:** 
- Stats históricas H2H lejanas (>2-3 temporadas) no tienen poder predictivo.
- Equipos peleando descenso de local en las últimas 10 jornadas son significativamente más peligrosos que lo que indican sus stats agregadas de temporada.
- Cuando la cuota te parece "value" y buscas datos que lo confirmen, ya estás en confirmation bias.

### Error C: Pata débil incluida en parlay (Benfica 1H)

**Qué hice:** Marqué Benfica 1H con 3.5/5 de confianza, señalé 8 empates en 27 partidos (30% draw rate), y AÚN ASÍ la incluí en el parlay para subir la cuota combinada.

**Lección:** En parlays, la cadena se rompe por el eslabón más débil. Solo incluir patas con confianza ≥ 4/5.

### Error D: EV como validación circular

**Qué hice:** Calculé probabilidades basadas en análisis de contexto superficial → obtuve EV positivo → usé el EV positivo como justificación del pick.

**Lección:** EV positivo no valida nada si la probabilidad de entrada es incorrecta. El EV calculator es output, no validación. Garbage in, garbage out.

### Checklist de motivación (OBLIGATORIO antes de estimar probabilidades)

1. ¿Qué necesita el equipo A de ESTE partido específico? (3 pts obligatorios / 1 punto basta / nada)
2. ¿Qué necesita el equipo B?
3. **¿El empate le sirve a alguno de los dos? ¿A ambos?**
4. ¿Perder tiene consecuencias distintas a empatar para cada uno?
5. Si el empate sirve a ambos → **esperar primera parte cautelosa, descartar mercados de gol temprano**
6. ¿Hay factor desesperación (descenso, eliminación)? ¿Es de local? → **no apostar en contra**

### Reglas nuevas derivadas

- **Stats impresionantes (streaks, rachas) requieren stress-test contextual.** ¿Se mantiene la racha en partidos con contexto comparable al actual?
- **H2H > 3 temporadas = ruido.** Ignorar.
- **Parlay: solo patas ≥ 4/5 confianza.**
- **"Cuota parece alta" no es análisis.** Si empiezas por la cuota y buscas justificación, estás al revés.
- **Equipo en zona de peligro + local + últimas 10 jornadas = red flag para apostar en contra.**

---

## 2026-04-09 — Aprendizaje #4: El parlay de DC primera mitad era correcto — confiar en la tesis contextual

**Contexto:** Sesión de análisis de cuartos de final ida Europa League y Conference League. El usuario armó un parlay de 5 patas de Doble Oportunidad primera mitad (local no pierde el HT) para: Bologna, Freiburg, Porto, Mainz, AEK.

**Resultados de los AH+1 primera mitad (según el usuario, todos acertaron):**
- Freiburg: ganaba al HT (Grifo min 10) → ✅
- Porto: 1-1 al HT → ✅
- Mainz: ganaba al HT → ✅
- Bologna/AEK: pendiente de confirmar exacto

**Qué hice bien:**
- Identifiqué correctamente que Porto sin delanteros era la pata más débil para ML (Porto empató 1-1 final)
- Identifiqué correctamente que Freiburg y Mainz ganarían (ambos ganaron)
- El usuario me corrigió sobre Villa no marcando en 1H y Bologna en racha — tenía razón contextual

**Qué hice mal:**
1. **Sobreanalicé y generé parálisis.** El usuario tuvo que corregirme múltiples veces para que confiara en el contexto: "idas de cuartos = primeros tiempos sin goleadas". Esta tesis simple era correcta y yo la complicaba con búsqueda de stats granulares.
2. **Confundí mercados.** Leí mal el Hándicap Europeo +1 como Asiático +1 y luego el VA+2 como AH+2. Esto generó recálculos innecesarios y confusión.
3. **Subestimé a Rayo Vallecano y sobreestimé a AEK.** Rayo ganó 3-0 a AEK. Mis argumentos de que Rayo era débil (13° La Liga, 0-0 vs Samsunspor en casa) no capturaron que en eliminatorias europeas de local la motivación es diferente a la liga.
4. **Sobreestimé la fortaleza defensiva de Bologna.** Dije "Bologna no gana el HT en 19 de 20 partidos de local" y "Villa no marca en 1H". Villa metió 2 goles (Watkins doblete). La stat de primeros tiempos de Bologna era de Serie A, no de Europa — contextos diferentes.
5. **El pick de Villa <1.5 goles era incorrecto.** Villa metió 2. Bologna 5 clean sheets en casa en EL no era suficiente — Villa es un equipo de otro nivel vs los rivales previos de Bologna.

**Lecciones:**

### Lección 4A: DC primera mitad en eliminatorias es un mercado sólido
Los picks de "local no pierde el primer tiempo" en idas de eliminatorias europeas son estructuralmente fuertes. De los 5 analizados, la mayoría acertó. La tesis contextual era correcta — no necesitaba tanta validación estadística.

### Lección 4B: No confundir mercados — verificar SIEMPRE el tipo exacto
HC europeo ≠ HC asiático ≠ VA+2 ≠ DC. Cada uno tiene reglas de liquidación diferentes. PREGUNTAR al usuario antes de analizar si no es 100% claro.

### Lección 4C: Equipos de elite de visitante en eliminatorias pueden romper patrones
Villa (3° PL) metiendo 2 goles en Bologna rompe el patrón de "visitantes no marcan en idas". Los equipos verdaderamente de elite (top 3-4 de las grandes ligas) pueden imponer su nivel incluso de visita. No agrupar a Villa con Forest o Celta.

### Lección 4D: Motivación local en Europa ≠ motivación local en liga
Rayo "mediocre" en liga (13°) pero aplastó 3-0 a AEK en Conference League. La motivación europea de local para equipos que rara vez juegan Europa es un multiplicador enorme que las stats de liga no capturan.

### Lección 4E: Simplicidad > complejidad cuando el contexto es claro
El usuario identificó la tesis correcta desde el inicio: "en idas de cuartos no hay goleadas en primera mitad". Yo compliqué innecesariamente buscando stats de primer tiempo partido por partido. Cuando el contexto estructural del torneo da una señal clara, no sobrecargarlo con data granular.

---

## 2026-04-09 — Aprendizaje #5: Porto sin delanteros = empate, no derrota

**Contexto:** Porto vs Forest terminó 1-1. Porto perdió a Samu Aghehowa y Luuk de Jong (delanteros titulares). Identifiqué correctamente que Porto ML era riesgoso por las bajas ofensivas y recomendé Porto o X (DC) en vez de ML.

**Validación:** El DC habría acertado (1-1), el ML habría fallado. El análisis de bajas ofensivas funcionó perfectamente.

**Regla confirmada:** Cuando un equipo pierde a sus delanteros titulares, degradar de ML a DC. El equipo puede mantener su solidez defensiva en casa pero carece de poder de gol para ganar.

---

## 2026-04-09 — Aprendizaje #6: Victoria Anticipada (+2) es ML disfrazado, no hándicap

**Contexto:** El usuario me mostró el mercado VA+2 y yo lo interpreté inicialmente como Asian Handicap +2 (probabilidad ~95%). En realidad es "cobro anticipado si el equipo toma ventaja de 2 goles" = esencialmente ML con un bonus. El usuario me corrigió.

**Regla:** Siempre verificar la definición exacta del mercado en la casa de apuestas. VA+2 (Victoria Anticipada) ≠ AH +2 (Asian Handicap). La cuota lo delata: si un AH +2 paga >2.00, probablemente NO es hándicap.
