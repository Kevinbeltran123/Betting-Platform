# Aprendizajes de Apuestas de Fútbol — Football Betting Learnings

> **PLACEHOLDER — Verbatim port pending**
>
> Este archivo es un placeholder estructurado. El contenido verbatim de producción debe ser
> copiado desde:
>   `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Claude_Sport_Betting/learnings/football-learnings.md`
>
> Para el port verbatim ejecutar:
>   ```bash
>   cp /Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Claude_Sport_Betting/learnings/football-learnings.md \
>      src/bip/core/claude/prompts/football-learnings.md
>   ```
>
> D-05: El contenido en español se conserva verbatim — las correcciones escritas por Kevin
> mantienen su voz y el contexto de reconocimiento de patrones.

---

## Contexto y Propósito

Este documento recoge los aprendizajes acumulados del análisis de partidos de fútbol para
apuestas deportivas. El objetivo es identificar situaciones donde el análisis estadístico
puede verse distorsionado por factores contextuales que los modelos ML no capturan
directamente.

El validador de Role C (Claude) utiliza este documento como sistema de referencia para
CONFIRMAR, MARCAR (FLAG) o RECHAZAR picks antes de enviarlos por Telegram.

---

## Sección 1: Trampas Estadísticas en el Análisis de Partidos

### 1.1 La Seducción de las Estadísticas Agregadas

Uno de los errores más comunes en el análisis de partido es dejarse llevar por las
estadísticas agregadas de la temporada cuando el contexto del partido específico las hace
irrelevantes. Las cuotas de un equipo pueden parecer favorables basándose en su rendimiento
general, pero varios factores pueden invalidar esa ventaja estadística.

**Patrones de alerta (red flags):**

- Equipo con alta puntuación en xG de temporada pero con 3+ partidos consecutivos sin
  marcar antes del partido analizado
- Diferencia significativa entre xG esperado y goles reales en las últimas 5 jornadas
- Equipo favorito jugando fuera de casa en liga de alto pressing contra su estilo de juego
- Historial de rendimiento en partidos de alto riesgo vs. partidos de menor importancia

**Cuotas afectadas:** Principalmente mercados 1X2, pero también Over/Under de goles.

### 1.2 El Efecto del H2H Desactualizado

El historial head-to-head (H2H) entre dos equipos puede ser engañoso cuando los datos son
demasiado antiguos o cuando las circunstancias han cambiado significativamente. Un H2H
favorable de hace 3+ temporadas no captura los cambios en plantilla, entrenador o sistema
táctico.

**Cuándo ignorar el H2H:**

1. El entrenador de alguno de los equipos ha cambiado en los últimos 18 meses
2. La plantilla ha tenido renovación superior al 50% de titulares habituales
3. El H2H se basa en menos de 3 partidos en los últimos 3 años
4. Los partidos de H2H se jugaron en condiciones muy distintas (ligas diferentes, competiciones
   europeas vs. liga nacional)

### 1.3 Motivación y Gestión de Partido

La motivación relativa de cada equipo en el partido es uno de los factores más difíciles de
cuantificar estadísticamente pero más importantes en el resultado final. Un equipo ya
clasificado puede realizar rotaciones masivas mientras que el rival juega con máxima
concentración por necesidad.

**Situaciones de alto riesgo por motivación:**

- Equipo local ya campeón o descendido matemáticamente antes de la última jornada
- Equipo visitante necesitando un resultado específico para clasificarse a Europa
- Partido de Copa inmediatamente antes o después (gestión de esfuerzo)
- Derbi regional con implicaciones de orgullo más allá de los puntos en juego
- Equipo con partido de Champions/Europa League el jueves siguiente a un partido de liga el lunes

### 1.4 Lesiones y Alineaciones Confirmadas

El análisis pre-partido debe siempre verificar las alineaciones confirmadas cuando estén
disponibles (típicamente 1h antes del partido). La ausencia de jugadores clave puede
invalidar completamente el análisis estadístico previo.

**Umbrales de preocupación:**

- Baja del portero titular: revalorar pick independientemente del análisis estadístico
- Ausencia de 2+ centrales titulares: mercados de Over/Under y ambos marcan se ven afectados
- Delantero referencia baja 48h antes: pick en mercados de goles del equipo afectado
- Centrocampista organizador ausente: afecta al estilo de juego y la posesión esperada

---

## Sección 2: Patrones de Valor en Cuotas de Mercado

### 2.1 Identificación de Cuotas con Valor (Value Bets)

El valor en una apuesta existe cuando la probabilidad implícita en las cuotas es menor que
la probabilidad real estimada por el modelo. Sin embargo, identificar valor verdadero
requiere distinguir entre sesgo del mercado y señales reales del modelo.

**Indicadores de valor genuino:**

- CLV positivo consistente en las últimas 20+ apuestas del mismo tipo de mercado
- Divergencia entre Pinnacle (mercado más eficiente) y bookmakers de menor margen
- Cuota no ha convergido hacia el valor esperado del modelo en las últimas 2h pre-partido
- Volumen de apuestas en Betfair Exchange confirma la dirección del modelo (smart money)

### 2.2 Sesgos del Mercado de Apuestas

Los mercados de apuestas tienen sesgos sistemáticos que generan oportunidades recurrentes:

**Sesgo de equipo local:** Los mercados sobrevaloran sistemáticamente al equipo local en
ligas con alta asistencia y ambiente intenso (como la Premier League y la Bundesliga).
El efecto es más pronunciado cuando el equipo local lleva varias jornadas sin ganar en casa.

**Sesgo de cuota baja:** Las cuotas inferiores a 1.5 para un equipo favorito tienden a
sobreestimar la ventaja cuando el partido es un enfrentamiento directo entre dos equipos
en la zona media de la tabla.

**Sesgo de racha:** Los mercados sobreajustan las cuotas de un equipo que lleva 3+ partidos
ganando consecutivamente, especialmente si fueron victorias holgadas. La regresión a la
media estadística sugiere cautela.

### 2.3 Movimiento de Cuotas como Señal

El movimiento de cuotas desde la apertura hasta el cierre puede indicar información nueva
que el modelo no ha procesado:

- Movimiento > 10% hacia una dirección: probable información privilegiada sobre alineaciones
- Cuota que se aleja del modelo al cierre: el mercado puede tener información sobre
  lesiones o motivación no pública aún
- Pinching (cuota que converge desde ambos lados): mercado eficiente, señal débil del modelo

---

## Sección 3: Errores de Análisis Frecuentes

### 3.1 Error de Contexto Europeo

Equipos que participan en competiciones europeas (Champions League, Europa League,
Conference League) frecuentemente muestran rendimiento degradado en liga los días
inmediatamente posteriores a partidos europeos exigentes.

**Patrón específico:** Partido de ida o vuelta en Europa el jueves → partido de liga el
domingo → rendimiento del equipo europeo puede estar 15-20% por debajo del esperado.

**Corrección:** Aumentar la incertidumbre del modelo en ±2-3% para picks de este equipo
en el partido de liga posterior al europeo.

### 3.2 Error de Forma Corta vs. Forma Larga

El análisis debe equilibrar la forma reciente (últimas 5-6 jornadas) con el rendimiento
de temporada completa. Los modelos que sobrepesan la forma reciente pueden ser engañados por
rachas atípicas.

**Forma corta engañosa (alerta):**
- 3 victorias consecutivas contra rivales de zona de descenso → no proyectar al rival actual
- Racha de derrotas incluye partidos ante los 3 primeros de la tabla → normalizar
- Empates consecutivos pueden reflejar cambio táctico defensivo, no pérdida de nivel

### 3.3 El Problema de Inferencia de Mercados de Córners

Los mercados de córners son especialmente susceptibles a sesgos de análisis porque los
modelos estadísticos de córners tienen menor precisión que los modelos de goles. Factores
adicionales de cautela:

- Estilos tácticos muy defensivos generan pocos córners independientemente del dominio
- Partidos de alta importancia táctica tienden a tener menos córners totales
- El marcador en curso afecta significativamente a la frecuencia de córners (equipos
  perdiendo buscan córners; equipos ganando protegen la posesión)

---

## Sección 4: Guía de Decisión para el Validador Role C

### 4.1 Criterios para CONFIRM

El validador debe emitir CONFIRM cuando:

1. El análisis estadístico del modelo es consistente con el contexto del partido
2. No hay factores de motivación que distorsionen significativamente el resultado esperado
3. Las alineaciones confirmadas no incluyen bajas críticas para el mercado analizado
4. El movimiento de cuotas es favorable o neutro (no contradice al modelo)
5. El H2H relevante (últimos 3 años, mismo contexto) apoya la dirección del pick
6. No hay señales de equipo con partido europeo próximo que genere gestión de esfuerzo

### 4.2 Criterios para FLAG (Marcar con Advertencia)

El validador debe emitir FLAG cuando:

1. Hay un factor contextual que añade incertidumbre pero no invalida el pick
2. Las cuotas tienen movimiento mixto (convergencia desde ambos lados)
3. El pick es técnicamente válido pero en un mercado con mayor varianza de la habitual
4. Hay información de motivación que puede afectar al equipo favorecido sin ser determinante
5. El H2H tiene datos limitados (1-2 partidos) en el período relevante

**Formato de FLAG:** El reason_code debe identificar el factor específico de alerta.
Ejemplos válidos: `motivacion_rotaciones`, `h2h_datos_escasos`, `europeo_jueves_previo`,
`movimiento_cuota_adverso`, `lesion_jugador_clave`.

### 4.3 Criterios para REJECT

El validador debe emitir REJECT cuando:

1. La alineación confirmada incluye baja del jugador principal para el mercado analizado
   (portero para picks de goles concedidos, delantero para picks de goles marcados)
2. El equipo tiene motivación claramente invertida (necesita perder para beneficiarse en
   la clasificación, ya campeón con rotaciones masivas confirmadas)
3. El movimiento de cuota es > 15% en dirección contraria al pick con alta convicción de
   mercado (smart money contradice al modelo)
4. Se ha identificado información no pública relevante posterior al cierre del análisis
5. El contexto del partido (derby, partido de revancha cargado emocionalmente) hace que
   los modelos estadísticos sean poco fiables históricament

---

## Sección 5: Aprendizajes Específicos por Liga

### 5.1 Premier League (Inglaterra)

- Alta intensidad física favorece a equipos de pressing en casa durante temporada completa
- Rendimiento post-internacional FIFA degradado es más pronunciado que en otras ligas
  (vuelos largos, diferencia horaria para jugadores sudamericanos y africanos)
- El mercado de cuotas de Premier League es altamente eficiente; el valor genuino es raro
  y suele aparecer en mercados secundarios (handicap asiático, total de córners)

### 5.2 La Liga (España)

- Dominio táctico no siempre se traduce en rendimiento en puntos (análisis xG puede
  sobreestimar equipos técnicamente dominantes pero con problemas de finalización)
- Los clásicos regionales (Sevilla derby, Madrid derby, etc.) presentan alta variabilidad
  independiente de la forma de temporada
- El descanso de mitad de temporada (enero) genera pick de valor en mercados de Over/Under
  cuando equipos retoman la actividad tras vacaciones desiguales

### 5.3 Bundesliga (Alemania)

- Liga con mayor precisión de modelos estadísticos (datos de tracking disponibles y
  consistentes)
- Bayerisches Dominanz: el Bayern München tiene una ventaja estadística estructural en
  liga que los modelos pueden subestimar en los partidos fuera de casa ante rivales directos
- El descenso de asistencia en diciembre-enero (clima) afecta ligeramente al rendimiento local

### 5.4 Serie A (Italia)

- Táctica defensiva estructural en gran parte de los equipos reduce los Over/Under de goles
  a mercados de menor valor esperado que en otras ligas
- La tabla final suele ser más ajustada por puntos entre puestos 6-15; picks en partidos
  de mitad de tabla tienen mayor varianza
- Lesiones de centrales son especialmente críticas dado el estilo táctico predominante

### 5.5 Ligue 1 (Francia)

- PSG domina estructuralmente; el valor genuino aparece en los partidos sin PSG donde
  equipos de mediana tabla se enfrentan con motivaciones similares
- Alta variabilidad en rendimiento de porteros; el mercado puede no ajustar suficientemente
  rápido a cambios de portero confirmados
- Los derbis del sur (Marsella, Mónaco, Niza) presentan alta intensidad emocional con
  impacto en la consistencia estadística del modelo

---

## Sección 6: Protocolo de Análisis Pre-Partido

### 6.1 Checklist Obligatorio Antes de Emitir Veredicto

Antes de emitir cualquier veredicto (CONFIRM/FLAG/REJECT), el validador debe verificar:

**Datos del partido:**
- [ ] Fixture ID y liga verificados
- [ ] Hora UTC del partido confirmada
- [ ] Competición identificada (liga, copa, europeo)

**Contexto del equipo local:**
- [ ] Posición en tabla y objetivo de temporada
- [ ] Forma últimas 5 jornadas (victorias/empates/derrotas, goles marcados y recibidos)
- [ ] Lesiones confirmadas y suspensiones
- [ ] Partido europeo en el entorno de 72h (antes o después)

**Contexto del equipo visitante:**
- [ ] Posición en tabla y objetivo de temporada
- [ ] Forma últimas 5 jornadas
- [ ] Lesiones confirmadas y suspensiones
- [ ] Partido europeo en el entorno de 72h (antes o después)

**Análisis de mercado:**
- [ ] Cuota de apertura vs. cuota actual (movimiento)
- [ ] Probabilidad implícita actual vs. probabilidad del modelo
- [ ] Comparativa con cuota de Pinnacle como referencia de mercado eficiente

**Decisión:**
- [ ] Edge confirmado (>5% respecto a probabilidad implícita de Pinnacle)
- [ ] Ningún red flag de las secciones anteriores invalida el análisis
- [ ] Veredicto emitido con reason_code específico

---

## Notas Finales

Este documento es un instrumento vivo. Los aprendizajes se refinan con cada temporada
y cada pick analizado. La versión en producción de este archivo está versionada con git
SHA para trazabilidad de auditoría: cada veredicto del validador registra qué versión de
este documento estaba activa en el momento del análisis.

**Mantenimiento:** Actualizar al inicio de cada nueva temporada con los patrones
identificados en el análisis post-temporada. Revisar los reason_codes de REJECT y FLAG
más frecuentes para identificar áreas de mejora del modelo ML.

**Idioma:** Este documento se mantiene en español deliberadamente. Las correcciones y
matices del análisis de Kevin están en español; traducirlos al inglés perdería precisión
en el significado y la voz del análisis. El validador Role C razona en español pero emite
su veredicto estructurado en inglés (D-06).

---

*Versión: placeholder-v0 — awaiting verbatim port from Claude_Sport_Betting/learnings/*
*SHA: calculado en tiempo de carga por learnings_loader.py (git SHA o sha256 fallback)*
*Última actualización: 2026-05-03*
