# Edge Strategy: Hidden Primary Leagues + Rare Markets

**Author**: Kevin Beltrán
**Created**: 2026-05-02
**Last revised**: 2026-05-02 (revisión 2 — post-integrity & primary-leagues research)
**Status**: Strategic research — pre-Phase 3.5
**Scope**: Long-term edge program after Phase 3 (Pick Engine) ships and validates against Betano.
**Predecessor docs**: `.planning/REQUIREMENTS.md`, `.planning/research/SUMMARY.md`, `CLAUDE.md` Technology Stack

> **Changelog 2026-05-02 (revisión 2)**: Reordenado Tier-1 después de investigar match-fixing integrity + primary-league analysis. Brasileirão Série B **descartada** por Operação Penalidade Máxima (card-spot-fixing en Série B last-round matches específicamente, Sept 2022–Feb 2023). Brasileirão Série A **degradada a Tier-2 con filtros** (caso Bruno Henrique Nov 2024 confirma contaminación en card markets). Liga Portugal Primeira + Romanian SuperLiga + Greek Super League ascendidos como anchors por (a) Betano regional trading desks (b) integrity manageable (c) sample size adecuado. Bulgarian Parva Liga + Cypriot 1st + Albanian Superliga + Serbian SuperLiga **hard-avoid** por integrity crítico. Phase 6 (Timed Corners) → v2-deferred, mantener carve-out para EU Betano coverage donde el mercado existe. Sección 11 (Match-fixing risk register + filtering protocols) añadida. Decisiones del operador en Sección 8 resueltas.

---

## 0. Operator Philosophy (the load-bearing premise)

> **"Las ligas grandes tienen liquidez; las ligas ocultas tienen edge. El edge real vive en mercados raros de ligas primarias de países que el sharp money ignora."**

Esto **no** es una hipótesis de trabajo — es la tesis del programa. Toda la priorización en este documento se deriva de ella.

Implicaciones inmediatas:

1. **Top-5 europeo (PL/La Liga/Bundesliga/Serie A/Ligue 1) NO es el target principal.** Está en el roadmap por razones operacionales (data ya seedeada, Betano deep), pero su CLV esperado en 1X2 es <0.5% — no compite con el costo de oportunidad de modelar lo demás.
2. **El target son LIGAS PRIMARIAS de países menos visibles, NO segundas divisiones de países grandes.** Liga primaria = mejor data quality, lineup confirmability, sample size, y atrae menos sharp money que la segunda división de un país top. Ejemplo: Liga Portugal Primeira > Brasileirão Série B (que además está contaminada por match-fixing).
3. **Mercados primarios (1X2, AH mainline, O/U 2.5) NO son el foco.** Están demasiado modelados por bookies competentes. El foco son: cards, corners totales, both-halves, HT/FT, anytime goalscorer, Asian tails.
4. **Volumen de picks > tamaño individual.** Ligas exóticas + mercados raros = más oportunidades semanales, picks más pequeños, edge acumulado.
5. **Sample size es el límite real.** Cards/corners necesitan n>500 picks para validar CLV. Esto define cuánto tiempo de runway necesita cada vector.
6. **Integrity es un constraint hard, no soft.** Cualquier liga con riesgo de match-fixing documentado (Sportradar / Europol / UEFA flags) se descarta como anchor — un partido fixed es un outlier que destruye CLV y corrompe training data.

---

## 1. Lo que descarto antes de seguir (basado en evidencia)

| Idea | Por qué descartar | Fuente |
|---|---|---|
| **VAEP / xT / EPV** | Requieren event data SPADL ($10-50K/año). API-Football no lo provee. Son herramientas de scouting, no de betting. | Decroos KDD 2019; Pappalardo 2019; Fernández-Bornn 2021 |
| **GNN / Transformer sobre eventos** | 100+ papers revisados sin evidencia de batir gradient boosting en features tabulares. Cero CLV demostrado. | Bunker & Susnjak J. AI Research 2022 |
| **Manager bounce strategy** | Efecto causal ≈ 0 después de controlar regresión a la media. Folk story. | De Paola & Scoppa JEBO 2012; Bryson et al. 2021 |
| **LLM como predictor primario** | GPT-4 solo es peor que el mercado. | Pop et al. arXiv:2409.17191 (2024) |
| **Top-5 EU como target principal** | Pinnacle es near-perfect en 1X2 top-5. <0.5% CLV esperado. | Forrest & Simmons 2008; Štrumbelj 2014 |
| **Brasileirão Série B** | **Operação Penalidade Máxima 2023** — card-spot-fixing target específico de Série B last-round matches. Modelado de cards corrupto, integrity en alerta CRÍTICA hasta 2025+. | Wikipedia "2023 Brazilian football match-fixing scandal"; Sportradar 2024 Brasil reports |
| **Card markets en Brasileirão Série A** | Caso Bruno Henrique (Flamengo, Nov 2024) confirma que el spot-fixing en cards llegó a Serie A. Outcomes (1X2/totals) modelables desde 2024+, **pero card markets corrupted regardless of league tier**. | Wikipedia "2024 Brazilian football match-fixing scandal" |
| **Bulgarian Parva Liga** | 46 sanciones Sept 2025 (BFU chief Mihaylov investigado). 8th-most-corrupt football nation Europa. Sportradar-Police MOU activo desde 2021 sin contener el fixing. | insideworldfootball.com Sept 2025 |
| **Cypriot 1st Division** | El propio presidente de la CFA admitió "league likely plagued by match-fixing". 75 partidos investigados, **cero condenas**. UEFA flagged 17 matches. | LawInSport 2018; The Black Sea "Cypriot Deception" |
| **Albanian Superliga / Bosnia / Kosovo / North Macedonia** | Hubs documentados de Balkan fixing-route. Skenderbeu UEFA-banned 10 años por fixing >50 partidos. | Tirana Times; Football Legal 2024 |
| **Serbian SuperLiga** | UEFA llamó a FSS a investigar 2021 por "enormous bets / live-betting irregularities". | RFE/RL |
| **Chinese Super League / Indonesia Liga 1 / Vietnamese V.League** | CRITICAL fixing risk. CSL: 73 lifetime bans Jan 2026. Indonesia: persistent referee-mafia. Vietnam: V.League 2 prosecutions Dec 2023. | Al Jazeera 2026; Vietnam News Dec 2023 |
| **Player props sin Pinnacle benchmark** | Sin closing-line sharp para validar, no se distingue edge de varianza. | Sin fuente sharp pública para Betano LATAM props |
| **Time-window corners en Betano LATAM** | Investigación: Betano BR/MX **NO postea ventanas granulares** (0-15, 15-30, etc.). Sólo total match corners + team corners. | Betano coverage research (research agent 3) |
| **Method of first goal (header/FK/penalty/OG)** | Sin features predictivas en API-Football; varianza domina. | Research agent 2 |
| **Player to score 2+** | Sample size insuficiente. Necesitaría n>1000 para CLV. | Research agent 2 |
| **Race to N goals** | Bajo volumen (2-4/liga/semana). Derivable del modelo Poisson sin valor adicional. | Research agent 2 |
| **Method/exact-score combos** | Vig 10-25%. Math negativa. | Research agent 2 |
| **EV+ subscription services como signal source** (Trademate Sports, RebelBetting, OddsJam, ValueBetting.app, Betburger, Surebet, BetHero) | **NO usan modelos predictivos**. Son scrapers de Pinnacle implementando el método Kaunitz 2017 (Pinnacle no-vig prob vs soft-book divergence). Tres razones para descartar: (1) account closures en Betano dentro de 4-12 semanas de seguir sus picks (Trademate FAQ explícitamente lo admite); (2) NO transferible a CV — un entrevistador quant lee "subscribió a RebelBetting" como zero signal de modeling skill; (3) edge es **rented**, no **owned** — depende de Pinnacle siendo perpetuamente sharp y de que tu cuenta no sea limitada. **Uso defendible solo**: 1 mes de suscripción (NO bettear sus picks) como **benchmark dataset** comparando contra picks generadas por modelo propio — produce un research artifact que SÍ es CV-positive. Ver Sección 14 para detalle completo. | Kaunitz, Kennedy, Pang & Castaño-Solé (2017) "Beating the bookies with their own numbers" arXiv:1710.02824; Trademate Sports whitepaper; r/sportsbook account-closure megathreads 2022-2025 |

**Tiempo no perdido**: estos descartes ahorran ~6-12 meses de implementación que no producirían edge (o producirían edge negativo via fixed matches o account closures). Documentar la decisión es importante para que futuros yo no las re-evalúe sin nueva evidencia.

---

## 2. Tier-1 Leagues (las "ligas primarias ocultas" objetivo)

### Criterios de inclusión (todos cuatro deben cumplirse)

1. **Sharp money thin O Betano regional advantage**: Pinnacle limits ≤ $5K en mainline OR Betano opera local trading desk en la región (Stoiximan en Grecia, Betano en Romania/Portugal/Brasil)
2. **Data accesible**: API-Football coverage flag `lineups: true` Y `players: true` verificable vía `/leagues?id=X&coverage`
3. **Betano deep coverage**: al menos 1X2 + AH + O/U + corners totales + cards O/U + ATG disponibles
4. **Integrity manageable**: NO en lista hard-avoid (ver Sección 11). Sample size mínimo ≥240 fixtures/season para entrenar ML por temporada.

### Tabla de prioridad (revisión 2)

| Rank | Liga | Edge★ | Data★ | Betano★ | Integrity | Calendario | Sample/season |
|---|---|---|---|---|---|---|---|
| 1 | **Liga Portugal Primeira** | 5 | 4.5 | 5 | Low | Aug–May | 306 |
| 2 | **Romanian SuperLiga (Liga 1)** | 5 | 3.5 | 5 | Low-Med (quieto recientemente) | Jul–May | ~320 |
| 3 | **Greek Super League** | 4.5 | 3.5 | 5 | Med-historical (quieto post-2015) | Aug–May | ~250 |
| 4 | **Eredivisie (NL)** | 4 | 5 | 4 | Low | Aug–May | 306 |
| 5 | **Belgian Pro League (Jupiler)** | 3.5 | 5 | 4 | Low | Jul–May | ~280 |
| 6 | **Polish Ekstraklasa** | 3.5 | 4 | 4 | Low | Jul–May | 306 |
| 7 | **Liga MX (Apertura+Clausura)** | 4 | 5 | 4 | Low | Jul–May (split) | ~340 |
| 8 | **Norwegian Eliteserien + Swedish Allsvenskan** (joint) | 4 | 4 | 3.5 | Low | Apr–Nov | 240+240 |

★ = stars 1-5

### Detalle por liga (Tier-1)

#### #1 Liga Portugal Primeira
- **Por qué es la #1 (revisado)**: Big-3 dominance (Benfica/Porto/Sporting) crea **structural mispricing en mid-table** matchups. Betfair Exchange liquidity es **thin** vs Eredivisie/Bélgica → líneas se mueven lento. Betano coverage deep (sponsor actual). xG full coverage vía Understat/FBref. Sample size 306.
- **Quirks exploitables**:
  - European fade angle persistente para Benfica/Porto/Sporting (CL/EL midweek + weekend league)
  - Mid-table totals (ej. Boavista vs Vitória SC) frecuentemente posted desde modelo offline genérico
  - Estructura competitiva estable (no playoff splits que distorsionen) — modelos season-long limpios
- **Betano**: title sponsor Liga Portugal. Profundidad de mercado: 1X2, AH, O/U exotic, BTTS, cards O/U, corners O/U, ATG, HT/FT confirmados. Liga Portugal 2 (segunda) también disponible — candidate de Tier-2.
- **Integrity**: Apito Dourado (2004) histórico, Operação Pretoriano más reciente — pero Liga Portugal **no flagged en Sportradar 2024-25 hot zones**. Risk LOW.
- **Plan de seed**: 3 temporadas (2023-24, 2024-25, 2025-26) ≈ 918 partidos. Seguro para walk-forward 5-fold.

#### #2 Romanian SuperLiga (Liga 1)
- **Por qué tan alta**: **El advantage regional de Betano más fuerte de cualquier candidato**. Betano = top-3 operator en Rumania, sponsor activo de FCSB. Betano runs **local trading desk** con deep markets en cards, corner ranges, ATG, HT/FT, exotic O/U.
- **Quirks exploitables**:
  - Estructura play-off / play-out mid-season → **regime change exploitable** si modelas como dos seasons separadas
  - European fade para FCSB / CFR Cluj
  - Variación de calidad de cancha (clima continental, mud-pitches en marzo)
- **Caveat**: API-Football coverage aceptable pero **xG inconsistente** — verificar via FootyStats / FBref scrape como fallback. Sample workable: ~240 regular + ~80 playoff.
- **Integrity**: histórico Eastern European concerns pero **no major bust 2024-25 público**. Risk Low-Medium. **Aplicar filtros** (ver Sección 11) en partidos de bottom-half del playout.

#### #3 Greek Super League
- **Por qué tan alta**: **Stoiximan = Betano** (mismo parent Kaizen Gaming). Local trading desk de **mejor calidad de Greek football que cualquier otro book global**. Pricing localizado tight en Big-4 (Olympiacos/PAOK/AEK/Panathinaikos) pero **soft en mid-table y exotic markets**.
- **Quirks exploitables**:
  - European fade para Olympiacos/PAOK
  - Big-4 monopolio distorts power ratings → mid-table vs Big-4 totals frecuentemente soft
  - Sample 14 teams × (26 regular + 10 split) ≈ 250
- **Integrity**: **Medium-historical** (2011-2015 Koriopolis wave). Quieto recientemente pero **research alerta caso Interpol/Eurojust julio 2023 investigando 18 equipos griegos**. → Aplicar filtros de Sección 11 estrictos. Si en 2026-27 surge nuevo bust → re-evaluar Tier.
- **Caveat**: vigilar dynamics — esta es la liga Tier-1 con mayor riesgo residual de integrity. Si Sportradar reporta nuevo case en Greek SL → demote inmediato a Tier-2.

#### #4 Eredivisie (NL)
- **Quirks exploitables**:
  - **3.2-3.6 goles/partido (occasionally 3.8+)** — la primary europea más alta. Totals mispricing en Northern derbies y matches afectados por weather (lluvia/viento)
  - Tactical homogeneity high-press → matchup volatility en O/U
  - Sample 306, xG full vía Understat
- **Caveat (importante)**: Eredivisie es **borderline efficient** — Asian sharps trade el mercado de totals (high-scoring atrae action). 1X2 y AH mainline son sharp. **Edge vive en totals exotic + cards + ATG**, NO en mainline.
- **Betano**: listed all sites; full markets including AH, O/U exotics, cards, corners, ATG, HT/FT.
- **Integrity**: **LOW**. KNVB integrity strong, no UEFA flags 2020-26.

#### #5 Belgian Pro League (Jupiler)
- **Quirks exploitables**:
  - **Playoff split mid-season** divide los puntos por la mitad → modelos que tratan playoff como nuevo "regimen" capturan la ineficiencia que books no priorizan
  - CL fade para Brugge/Genk/Anderlecht
  - Sample 16 × (30 regular + ~10 playoff) ≈ 280
- **Caveat**: CL fade angle is well-known en sharps → **largely priced in** by Pinnacle. Soft money en mid-table fixtures pero pricing efficient en top-6. Edge está en regime-change handling.
- **Betano**: listed; deep markets including Asian corners.
- **Integrity**: Operation Zero (2018-19) was financial fraud + 1-2 fixed matches — verdicts "soft per Tandfonline 2024 paper lack of consequences". No major 2024-25 fix. **Risk Low-Medium**.

#### #6 Polish Ekstraklasa
- **Quirks exploitables**:
  - **Eastern winter break** (mid-Dec to mid-Feb) crea O/U distortions en restart matches (squad fitness reset)
  - Mud-pitches Marzo
  - Sample 306, xG full vía FootyStats
- **Caveat**: **No mega-dominant club** → competitive parity actually **hurts edge** (no soft mid-table ratings, todos los equipos similares). Pinnacle limits middling.
- **Betano**: listed; full mainline markets, decent cards/corners coverage.
- **Integrity**: post-2007-2010 Operacja Fryzjer cleanup successful. PZPN integrity infrastructure mature. Risk LOW.

#### #7 Liga MX (Apertura + Clausura)
- **Por qué se mantiene en Tier-1**: **Altitud es el factor estructural más exploitable de cualquier liga del mundo**. Toluca (2,680m), Pachuca (2,400m), CDMX clubs (2,250m) vs sea-level Mazatlán/Cancún/Tijuana. Compounded por short-rest fixtures.
- **Feature crítico a engineer**: `altitude_diff` (m sobre nivel del mar del estadio local vs altitud media del away team) + `altitude_short_rest_interaction` (fatiga compuesta).
- **Betano**: activo en México (regulated 2024-2025). Profundidad menor que Brasil pero AH/O/U/cards mainline confirmados.
- **Data**: API-Football full coverage incluyendo refs.
- **Integrity**: **LOW para Liga MX top-flight**. Liga Premier MX (3rd tier) tiene case 2024 (Héroes de Zaci FC), pero **NO contamina Liga MX**. Liga de Expansión MX (2nd tier) coverage limitado en Betano → defer.

#### #8 Norwegian Eliteserien + Swedish Allsvenskan (joint)
- **Tratamiento conjunto**: programa "Scandinavian Summer". Calendario Apr-Nov llena el gap May-Sept cuando el resto del Tier-1 está between seasons.
- **Quirks Eliteserien**: 3.11 goles/partido en 2025 — el mayor de las grandes ligas nórdicas → valor en O/U. Travel ártico (Bodø/Glimt = 67°N). Césped artificial vs natural. Post-Europa-Conference fade en Bodø/Glimt squad rotation.
- **Quirks Allsvenskan**: 2.65 goles/partido (más bajo, valor en 1X2/AH). **Public-bias contra clubes populares Stockholm** (AIK, Djurgården) → opening value en oponentes.
- **Betano**: tiene licencia sueca. Mercado disponible. Verificar fixture-por-fixture en Noruega.
- **Sample size**: 240 partidos por liga = borderline. Multi-season pooling necesario.
- **Integrity**: LOW (no scandals 2020-26 documentados).

### Tier-2 (modelable con caveats / supplements)

| Liga | Status | Caveat principal |
|---|---|---|
| **Brasileirão Série A** | Tier-2 con filtros | **Solo desde 2024 forward** post CBF-Sportradar partnership Apr 2025. **NO modelar card markets** (caso Bruno Henrique). 1X2/totals OK. Sample size potente compensa restrictions. |
| **Czech Chance Liga** | Tier-2 supplement | xG patchy, Pinnacle limits low. Slavia/Sparta duopolio distorts. Mid-table soft pricing. |
| **Liga Portugal 2** | Tier-2 candidate | Validar Betano coverage primero — si full markets disponibles, asciende a Tier-1 secundario. |
| **Argentina Liga Profesional** | Tier-2 supplement | Format churn (Apertura/Clausura/Copa de la Liga) confunde modelos season-aligned. **Avoid Primera Nacional y abajo** (fixing high-risk). |
| **Scottish Premiership** | Tier-2 supplement | Sample 228 borderline. Old Firm dominance distorts. Mid-table value real pero <100 picks/yr realistic. |
| **Saudi Pro League** | Tier-2 watch | Star-player mispricing real (e.g., Al-Qadsiah noted undervalued) pero Betano coverage thin. |
| **Austrian Bundesliga** | Tier-2 supplement | RB Salzburg dominance well-priced. xG full. Sample 190. |
| **Swiss Super League** | Tier-2 supplement | High-scoring totals edge similar a Eredivisie pero sample 180 (cuádruple round-robin). |

### Tier-3 (avoid as primary)

- **Hard avoid por integrity**: Bulgarian Parva Liga, Cypriot 1st, Albanian Superliga, Serbian SuperLiga, Chinese Super League, Indonesia Liga 1, Vietnamese V.League, Brasileirão Série B (entire league), Liga Premier MX (3rd tier), Argentine Primera Nacional, all African secondary leagues.
- **Avoid por data o sample**: Croatian HNL (180 fx, overfit risk), Slovenian PrvaLiga (180 fx), Hungarian NB I (limited xG), Slovak SuperLiga (190 fx), Indian/Thai L1 (gaps reales), Russian (sanciones), South African PSL (data-poor), Canadian Premier (muy chica), Uruguay/Ecuador/Peru/Bolivia (sample chico, lineups poco fiables).
- **Pause J1 / K League**: clean integrity, slow-market alpha real, **pero Betano coverage thin** → ejecutar via Betfair Exchange complica account longevity tracking. Defer hasta validar Tier-1 EU + LATAM.

---

## 3. Tier-1 Markets (los "picks raros" objetivo)

### Ranking por (edge × volumen × modelabilidad × Betano coverage)

| Rank | Mercado | Edge | Volumen | Model | Betano | Notas |
|---|---|---|---|---|---|---|
| 1 | **Anytime goalscorer (ATG)** | Alto | 30+/match | Alto | Soft (confirmado) | Mejor signal/effort ratio |
| 2 | **Score-in-both-halves / BTTS both halves** | Alto | 5-8/liga/sem | Alto | Wide | Sharp money ausente |
| 3 | **Score-grid combos (BTTS+result, Win+O2.5)** | Med-Alto | 5-10/liga/sem | Free from grid | Yes | Reusa Phase 2 ensemble |
| 4 | **HT/FT 9-way** | Med-Alto | 10-20/liga/sem | Med | Yes (8-12% margen) | Stake-capped |
| 5 | **Cards by half + total cards** | Med | Variable | Med (ref features) | Yes (NO en Brasil) | n>500 para CLV; integrity filter requerido |
| 6 | **Corners totales / Asian corners** | Med | Variable | Med (style) | Yes | Time-windows: ver carve-out Phase 6 |
| 7 | **Player shots on target O/U** | Med | 10-15/match | Med (matchup) | Yes (LATAM strong) | Settlement-data risk |
| 8 | **Asian goal lines tails (≥3.75, ≤0.75)** | Med | 3-5/liga/sem | Alto (Dixon-Coles) | Limited | Tier-2 books only |

### Detalle por mercado

#### #1 Anytime Goalscorer (ATG) — la oportunidad #1 documentada

**Por qué es la #1**: Books precian via Poisson naive (shots × conversion-rate), ignorando:
- Matchup defensivo del oponente
- Set-piece taker (especialmente penalty taker hierarchy)
- Expected minutes (rotación, confirmed lineup)

**Modelo**: xG-per-90 + minutos-jugados + opponent matchup features. Funciona con datos de API-Football.

**Betano explicit confirmación**: Sportsboom y Covers reviews 2025-2026 confirman que Betano postea props at -130 cuando otros books postean -200. Soft pricing comprobado.

**Caveat**: variance por jugador — n>200 picks por player tier para señal CLV.

**Plan de implementación**:
1. Ingest histórico de player_statistics: minutos, xG90, shots/90, posición, set-piece role
2. Feature: `expected_minutes` (predict desde rotation patterns)
3. Modelo Poisson per-player: `λ_player = xG90 × expected_minutes/90 × opp_def_factor × home_factor`
4. P(scoring) = 1 - exp(-λ) por jugador
5. Edge = P(scoring) × ATG_odds - 1, threshold 5%

#### #2 Both-halves markets (Score in both halves, BTTS both halves)

**Por qué soft**: Books precian como producto de dos half-Poissons independientes, ignorando:
- **2H goal-rate inflation**: ~55-60% de goles vienen en 2H (Predictology / Bet The Builder analysis)
- Score-state dependence: liderar en HT reduce 2H pressing

**Modelo**:
1. Half-specific lambdas (`λ_1H_attack`, `λ_2H_attack`) por equipo
2. Condicionado en score-state (latent team-strength)
3. P(score in both halves) = 1 - P(0g 1H) - P(0g 2H) + P(0g 1H AND 0g 2H)
4. Halves correlated via team-strength latent variable

**Datos requeridos**: API-Football timeline (`fixtures/events` da minutos de gol). Necesita recompute over historical seed.

#### #3 Score-grid combos (BTTS + Result, Win + O2.5)

**Por qué edge**: Books over-margin combos **aditivamente** (no multiplicativamente). Si tu score-grid (Dixon-Coles ya implementado en penaltyblog) está calibrado, los combos caen automáticamente.

**Edge esperado**: +2-4% sobre el componente más fuerte del combo.

**Implementación**: trivial — sumar probabilidades del score-grid sobre cells matching el combo.

#### #4 HT/FT 9-way

**Por qué edge**: Books margin 8-12% en HT/FT (vs 2-4% mainline). Si tu modelo de half-momentum es bueno, edge real existe.

**Caveat**: Books cap stakes hard (€50-200 retail). Capacity limited a ~10-15% del bankroll.

#### #5 Cards markets — referee feature engineering

Documentado en respuesta anterior. Vector clave:
- **Referee FE**: Buraimo et al. 2010 → 15-25% varianza explicada
- **Suspension threshold**: Witt CEPR → 12-23% reducción de fouls
- **Empty stadia bias** (histórico, COVID): home-card differential cae 1/3 sin público

**Integrity filter obligatorio** (Sección 11): NO modelar card markets en Brasileirão Série A o Série B (caso Bruno Henrique + Operação Penalidade Máxima). NO modelar cards en cualquier liga con Sportradar suspicious-match flag activo.

#### #6 Corners — caveat crítico de Betano LATAM (Phase 6 reescrito)

**Hallazgo de research**: Betano LATAM (BR/MX/AR) **NO postea ventanas granulares** (0-15, 15-30, 30-45). Solo total match corners + team corners.

**Decisión de scope (operador-aprobado)**: **Phase 6 movido a v2-deferred** con carve-out:
- ❌ Time-window corners no se construye en LATAM
- ✅ **Time-window corners en EU regions** (DE/PT/RO Betano + top-5 EU) puede construirse en v2 si surge bandwidth — el mercado existe en EU Betano sites
- ✅ **Total corners + Asian corners en TODAS las Tier-1 leagues**: viable, soft, modelable. Reusa el mismo feature stack (pressing-style, ref FE, weather).

#### #7 Player shots on target O/U
- Soft en Betano LATAM. Books usan league-average shot-conversion sin matchup adjustment.
- Settlement-data risk: API-Football shot data tiene ~5% error según industry. **Validar con second source (Understat) antes de scaling.**

#### #8 Asian goal lines tails (≥3.75, ≤0.75)
- Pinnacle sharp en mainline (2.0/2.25/2.5/2.75) pero soft en tails — score-grid Poisson tails sensitive al goal-rate prior.
- Modelable con bivariate Poisson + Karlis-Ntzoufras diagonal-inflation (penaltyblog implementa).
- Volumen bajo (3-5/liga/semana) — supplement, no anchor.

---

## 4. Edge Vectors (qué construir, en qué orden)

### P0 — Quick wins (semanas 1-4 después de Phase 3)

#### V-01: Shin-corrected market probabilities como feature
- **Edge**: -3 a -7% logloss según Strumbelj 2014, Forrest-Goddard-Simmons 2005
- **Esfuerzo**: ~30 líneas Python (punto fijo iterativo de Shin 1992/1993)
- **Cambio**: en `src/bip/sports/football/features.py:412-438` reemplazar `1/odds` por `shin_prob(odds_home, odds_draw, odds_away)`. Mantener feature_schema_version bumping a 3.
- **Riesgo**: ninguno — método matemático bien documentado.

#### V-02: Validar Betano coverage en Tier-1 leagues
- **Spot-check 5 fixtures por liga** en betano sites correspondientes:
  - Liga Portugal Primeira (betano.pt)
  - Romanian SuperLiga (betano.ro)
  - Greek Super League (stoiximan.gr / betano.gr)
  - Eredivisie (betano.de o equivalente)
  - Belgian Pro League (betano.be o equivalente)
  - Polish Ekstraklasa (betano.pl)
  - Liga MX (betano.mx)
  - Eliteserien + Allsvenskan (verificar)
- Documentar qué markets están disponibles (1X2, AH, O/U, corners totales, cards O/U, ATG, HT/FT, both-halves, BTTS+result)
- Output: `scripts/betano_coverage_findings.md` (versionado en repo)
- **Crítico**: validar BEFORE comprometer una phase a una liga.

#### V-03: Player-rating model + lineup-confirmed delta
- **Base**: Pappalardo 2019 PlayeRank methodology, adaptada a API-Football data
- Features per player desde `players/statistics`: npxG/90, xAG/90, shots/90, fouls drawn-committed/90, tackles+interceptions/90, cards/90
- Z-score por liga + posición. Decay exponencial half-life 5-10 partidos.
- 7 grupos posicionales (GK/CB/FB/CM/AM/W/ST) con pesos diferenciales (CB/GK ~2-3× más impacto que ofensivos según Tsokos 2023)
- Replacement-player delta: `Σ (rating_actual_XI − rating_25th_pct_position) × minutes_share`
- Lineup re-score a T-30min cuando confirma lineup
- **Edge**: +3-7% AUC en surprise lineups (~10-15% de fixtures), Constantinou 2019 confirmation
- **Plans estimados**: 4 (player ingestion, rating computation, lineup delta, T-30min re-prediction wiring)
- **Aplicable universalmente**: las 8 ligas Tier-1 se benefician del mismo modelo, sin liga-specific tuning. Esta es la razón por la que es prioritario sobre cards (V-04).

### P1 — Mid-term (mes 2-3)

#### V-04: Referee feature engineering + cards markets
- Bootstrap histórico desde football-data.co.uk CSVs (gratis, ToS permite no-comercial)
- Maintain referee table: `(name, league) → ref_id`
- Features:
  - `ref_yellows_per_match_mean` rolling 30 partidos, shrink a media liga si n<30
  - `ref_penalties_per_match`
  - `ref_added_time_distribution`
  - `ref_home_card_bias`
- Suspension threshold feature: `cards_to_suspension(player, league, season)` con reglas liga-específicas
- Modelar: `cards_total ~ ref_FE + team_foul_rate + suspension_at_risk_count + home_pressing_diff` (negative-binomial, no Poisson — overdispersion confirmada por Smarkets)
- **Plans estimados**: 3-4
- **Liga aplicabilidad**: Greek SL (con caveat integrity), Eredivisie, Belgian, Polish, Liga Portugal, Romanian, Liga MX. **NO en Brasileirão A/B**. Si Greek SL presenta nuevo bust → demote.

#### V-05: Both-halves model (1H + 2H lambdas)
- Half-specific Poisson lambdas por equipo
- Score-state correlation latent
- Markets: Goal in both halves, Score in both halves, BTTS in both halves, Highest scoring half
- **Plans estimados**: 3
- **Aplicable a las 8 ligas Tier-1**.

#### V-06: Anytime Goalscorer (ATG) model
- Per-player Poisson scoring rate
- `expected_minutes` predictor (rotation pattern model)
- Per-fixture λ adjustment (matchup, home/away)
- **Plans estimados**: 4 (ingestion + minutes model + scoring rate model + EV pipeline)
- **Mercado más prometedor de todos** según research consensus
- **Aplicable a las 8 ligas Tier-1**, mejor signal donde Betano LATAM (Liga MX) tiene player-prop pricing más soft.

### P2 — Longer term (mes 4-6)

#### V-07: Closing-line predictor (innovador)
- Dataset: `(opening_odds, t-60min_odds, injury_news_flag, lineup_strength_delta) → closing_odds`
- XGBoost regresor sobre el dataset
- A T-2h, predict closing → if `predicted_close < current_open` por >5%, bet at open
- **No publicado** según research — quien tiene edge no comparte
- Validación: tu CLV histórico debería ser monotónicamente positivo si el modelo cierra bien
- Levitt 2004 + Forrest-Goddard-Simmons 2005 son la base teórica
- **Caveat**: requiere histórico de odds movement que aún no tienes seedeado completo

#### V-08: penaltyblog Bayesian Hierarchical + Weibull en ensemble
- `BayesianHierarchicalGoalModel` (PyMC)
- `WeibullCopulaGoalsModel` (Boshnakov 2017)
- Add as additional base models en stacked ensemble
- **Edge marginal**: +0.5-1.5% logloss, "free" porque la library ya está pinned
- Ayuda más en ligas pequeñas (Eliteserien/Allsvenskan/Romanian playoffs) por shrinkage cross-league
- Hierarchical especialmente valioso para nuevas ligas con sample chico

### P3 — Strategic (mes 6+)

#### V-09: Per-league Kelly multiplier basado en CLV histórico
- (Diseño previo en respuesta anterior)
- `kelly_multiplier(league, market) = clip(rolling_CLV_pct / 3.0, 0.0, 1.5)`
- Cuando tengas 200+ CLV records por (league × market) tile

#### V-10: Asian goal lines tails model
- Dixon-Coles + Karlis-Ntzoufras diagonal-inflation
- penaltyblog ya implementa ambos (`BivariatePoissonGoalModel`)
- Solo activar tails (3.75+, 0.75-) — mainline ya es sharp

#### V-11: Multi-armed bandit para portfolio de picks simultáneos
- Hwang-Kim arXiv:2403.04102 (2024)
- Treats cada market como arm, Thompson sampling para stake allocation
- Solucion al problema de Quarter Kelly individual + suma > Quarter Kelly bankroll

---

## 5. Calendar & operational density

Selección de Tier-1 leagues garantiza fixtures **year-round**:

```
Jan  Feb  Mar  Apr  May  Jun  Jul  Aug  Sep  Oct  Nov  Dec
─────────────────────────────────────────────────────────
[Liga Portugal Primeira ███████████]     [Liga Portugal ████]
[Romanian SuperLiga ████████████]        [Romanian SuperLiga ████]
[Greek Super League ████████]            [Greek Super League ████]
[Eredivisie ████████████]                [Eredivisie ████]
[Belgian Pro League █████████]           [Belgian Pro League ████]
[Polish Ekstraklasa ███████]             [Polish Ekstraklasa ████]
[Liga MX Clausura ████]            [Liga MX Apertura ████████]
                    [Eliteserien + Allsvenskan ███████████]
```

Esto significa que:
- Volumen mínimo sostenido durante todo el año
- Doble cobertura en May-July (Scandinavian Summer + Liga MX shoulder + LATAM + early Eastern Europe)
- Diversificación de calendario reduce concentración de risk en single league
- Off-period mínimo (Junio en Tier-1 EU) compensado por Liga MX Clausura playoffs + Scandinavian + Liga MX Apertura early

---

## 6. Validación

### Métricas obligatorias (deben implementarse al menos para top-3 markets)

| Métrica | Por qué | Implementación |
|---|---|---|
| **CLV%** (existe) | Norte-de-magnetismo del programa | `clv_records` Supabase |
| **CLV per-league per-market** | Decisión: ¿esta tile sigue siendo edge-positive? | rollup query mensual |
| **RPS (Ranked Probability Score)** | Estándar académico para 1X2; penaliza errores ordinales | Constantinou-Fenton 2012 |
| **Brier decomposition (reliability + resolution + uncertainty)** | Diagnostica si modelo está mal calibrado vs poco informativo | Murphy 1973 |
| **Reliability diagram per-league** | Visualización de calibración por liga | matplotlib + bins |
| **Logloss (existe)** | Métrica baseline de probabilidad | sklearn |
| **PSI (Population Stability Index) entre seasons** | Detecta drift → señal para retrain | Custom (~30 líneas) |
| **Sharpe del CLV** | mean_CLV / std_CLV — confianza estadística | Trivial |
| **Calibration slope** | Slope ≠ 1 → miscalibration sistemático | Logistic regression sobre probs calibradas |
| **Sportradar suspicious-match cross-reference** | Detect contaminated training data + skip flagged fixtures live | Manual cross-ref + automation post-V-04 |

### Sample size requirements

- **Mainline 1X2 / AH**: n > 100 picks para CLV signal
- **Cards / corners markets**: n > 500 (alta varianza)
- **ATG / player props**: n > 200 por player tier
- **HT/FT 9-way**: n > 300

**Implicación**: programa toma 6-18 meses para validarse por completo. Tier-1 leagues bien elegidas + foco en V-01/V-02/V-03 primero acelera el ramp.

### Rollback criteria

- CLV per-league × market < +1% sobre rolling 200 picks → pause + audit
- Logloss empeora >10% vs prev season → drift, retrain
- Edge filter trigger rate < 1% de fixtures evaluados → pipeline broken o calibration off
- **Nuevo Sportradar suspicious-match flag en una Tier-1 league** → pause picks en esa liga + audit

---

## 7. Phase Roadmap propuesto

| Phase | Goal | Vectors | Status |
|---|---|---|---|
| 3 | Pick Engine + Telegram | (existing) | In planning |
| 4 | Production Orchestration | (existing) | TBD |
| **3.5** (proposal) | **Quick wins**: Shin-correction + Betano coverage validation + Tier-1 league seeding | V-01, V-02 | NEW |
| **4.5** (proposal) | **Player-level alpha**: player rating + lineup-confirmed delta | V-03 | NEW |
| 5 | Claude Confidence Modifier (Shadow) | (existing) | TBD |
| **5.5** (proposal) | **Referee + cards markets** (excl. Brasileirão entire) | V-04 | NEW |
| ~~6~~ | ~~Timed Corners~~ | — | **MOVED TO v2-deferred** with EU carve-out |
| **6.5** (proposal, ex-6.5) | **Both-halves + ATG models** | V-05, V-06 | NEW (promoted from after Phase 6) |
| 7 | Tennis Scaffold | (existing) | TBD |
| **8+** | Closing-line predictor + Bayesian ensemble + Multi-armed bandit + Total Corners model | V-07, V-08, V-10, V-11 | Speculative |

**Phase 6 explicit re-scope (operador-aprobado 2026-05-02)**:
- Time-window corners (0-15, 15-30, etc.) **deferred to v2** — Betano LATAM no lo postea, pivot effort vale más en V-05 (both-halves) que tiene Betano coverage universal
- **Carve-out**: si en v2 surge bandwidth y se valida que time-window corners están en EU Betano sites para top-5 + Romanian SuperLiga, se puede revivir para esas regiones específicas
- **Total Corners + Asian Corners** se modela en V-10 (Phase 8+) usando el feature stack de V-04 (ref FE, pressing-style)

**Pacing decision (operador-aprobado 2026-05-03)**:
- **Velocidad: AGRESIVO** — Phase 3.5 + Phase 4.5 paralelizados (V-01 + V-03 simultáneos). ~12 meses al CV-showcase completo (vs 18 meses conservador).
- **Foco: HÍBRIDO** — V-03 Player rating primero (universal aplicabilidad a las 8 ligas Tier-1, sirve income + CV simultáneamente). Después V-08 Bayesian + V-04/V-05/V-06. V-07 closing-line predictor en mes 9-11 cuando histórico de odds movement esté seedeado.
- **Trade-off aceptado**: menos validación entre sprints; más riesgo de tener que volver atrás si una pieza no genera CLV. Mitigado por validación per-vector con sample size mínimos.
- Ver Sección 13 para timeline detallado.

---

## 8. Operator Decisions (Resolved 2026-05-02)

### Q1 (resuelta): Filosofía Verticalizar vs Horizontalizar
**Decisión del operador**: **HORIZONTALIZAR — ligas primarias de países menos vistos, NO segundas divisiones de países grandes.** Mercados raros se aplican como overlay en cada liga Tier-1.
- **Implicación**: V-03 (player rating) **prioritario** sobre V-04 (cards) porque player rating se aplica universalmente a las 8 ligas Tier-1, mientras cards es market-specific.
- **Implicación 2**: Brasileirão Série B descartado (era 2nd division de país grande + integrity issues). Tier-1 reordenado a ligas primarias europeas + Liga MX + Scandinavian.

### Q2 (resuelta): Phase 6 Timed Corners
**Decisión del operador**: **Mover a v2-deferred. Mantener carve-out para ligas EU donde el mercado existe en Betano** (top-5 + Romanian SuperLiga via betano.ro / betano.de / betano.pt). Pivot bandwidth a V-05 (both-halves) que tiene Betano coverage universal.

### Q3 (resuelta): Brasileirão Série A
**Decisión del operador**: **Tier-2 con filtros estrictos**, no Tier-1.
- Razón: escándalos de match-fixing 2022-2024 (Operação Penalidade Máxima + caso Bruno Henrique 2024) requieren análisis cuidadoso antes de modelar.
- **Restricciones**:
  - Solo modelar partidos desde 2024-Apr forward (post-CBF-Sportradar partnership)
  - **NO modelar card markets en Brasileirão A o B** (corruption documented en cards específicamente)
  - 1X2 / totals / corners totales OK con integrity filter (Sección 11)
  - Sample size 380/season big-positive — pero solo cuenta desde 2024 = ~760 partidos disponibles para train

### Q4 (resuelta): Verticalizar vs Horizontalizar dentro de Tier-1
**Decisión del operador**: confirmada (sí). V-03 (player rating universal) > V-04 (cards market-specific). Implementation order respeta la filosofía.

### Q5 (resuelta): Phase 3 ship-first
**Decisión del operador**: confirmada (sí). Toda esta estrategia se ejecuta DESPUÉS de Phase 3 mandar las primeras 50-100 picks reales y de validar el CLV pipeline contra Pinnacle.

### Q6 (NEW — emergente de revisión 2): J1 League / Betfair Exchange routing
- **Estado**: deferred. Volver a evaluar después de validar 2-3 Tier-1 EU leagues. Operacionalmente, ejecutar en exchange diferente complica account longevity tracking + Phase 1 D-04 single-Betano contract.

### Q7 (NEW): Greek Super League integrity vigilance
- **Riesgo**: Greek SL tiene Medium-historical fixing risk (Koriopolis 2011-2015). Quieto en 2024-25 pero Interpol/Eurojust julio 2023 investigando 18 equipos griegos.
- **Decisión**: incluir en Tier-1 ANCHOR pero con **monitoring activo**. Si surge nuevo Sportradar bust en 2026-27 → demote a Tier-2 + pause picks.

---

## 9. Bibliografía clave (sources cited en el documento)

### Player-level analytics
- Decroos, Bransen, Van Haaren, Davis (2019). "Actions Speak Louder than Goals: Valuing Player Actions in Soccer." KDD 2019. arXiv:1802.07127
- Pappalardo et al. (2019). "PlayeRank: Data-driven Performance Evaluation and Player Ranking in Soccer." ACM TIST. dl.acm.org/doi/10.1145/3343172
- Tsokos et al. (2023). PLOS ONE. journals.plos.org/plosone/article?id=10.1371/journal.pone.0284318
- Constantinou (2019). "Dolores: a model that predicts football match outcomes from all over the world." Machine Learning, 108.

### Market efficiency & CLV
- Forrest, Goddard & Simmons (2005). "Odds-setters as forecasters: the case of English football." Int. J. Forecasting 21(3).
- Forrest & Simmons (2008). Int. J. Forecasting.
- Štrumbelj (2014). "On determining probability forecasts from betting odds." Int. J. Forecasting 30(4).
- Shin (1992, 1993). Original Shin probabilities methodology.
- Levitt (2004). "Why are gambling markets organised so differently from financial markets?" Economic Journal 114.
- Kaunitz, Kernytsky, Hsia, Greenwald, Connelly (2017). "Beating the bookies with their own numbers." arXiv:1710.02824

### Statistical models
- Dixon & Coles (1997). "Modelling Association Football Scores and Inefficiencies in the Football Betting Market."
- Karlis & Ntzoufras (2003, 2009). Diagonal-inflated bivariate Poisson.
- Boshnakov, Kharrat & McHale (2017). "A bivariate Weibull count model for forecasting association football scores." Int. J. Forecasting 33(2). DOI:10.1016/j.ijforecast.2016.11.006
- Baio & Blangiardo (2010). "Bayesian hierarchical model for the prediction of football results." J. Applied Statistics 37(2).
- Egidi, Pauli & Torelli (2018). "Combining historical data and bookmakers' odds in modelling football scores." Stat. Modelling.
- Owen (2011). "Dynamic Bayesian forecasting models of football match outcomes with estimation of the evolution variance parameter." IMA J. Mgmt Math.

### Cards / referees / fatigue
- Buraimo, Forrest & Simmons (2010). "Are football referees really biased and inconsistent?"
- Bryson, Dolton, Reade, Schreyer & Singleton (2021). "Causal effects of an absent crowd on performances and refereeing decisions during Covid-19." Reading EMDP 2020/25.
- Witt CEPR/USNA WP 52. Suspension rules and fouling. cepr.org/voxeu/columns/impact-suspension-rules-fouls-football-case-study-premier-league
- Dupont et al. UEFA CL 11-yr injury study. pubmed.ncbi.nlm.nih.gov/23851296/
- Carling et al. Fixture congestion meta-analysis (2021). PMC7846542.

### Calibration & metrics
- Constantinou & Fenton (2012). "Solving the problem of inadequate scoring rules for assessing probabilistic football forecasting models." J. Quant. Anal. Sports 8(1).
- Murphy (1973). "A new vector partition of the probability score."
- Guo et al. (2017). "On Calibration of Modern Neural Networks." arXiv:1706.04599

### Recent SOTA & reviews
- Bunker & Susnjak (2022). "The Application of Machine Learning Techniques for Predicting Match Results in Team Sport: A Review." J. AI Research 73.
- Hwang & Kim (2024). "Multi-Armed Bandits for Sports Betting Portfolio Selection." arXiv:2403.04102
- Pop et al. (2024). "Can Large Language Models Predict Sports Outcomes?" arXiv:2409.17191

### Match-fixing integrity (NUEVO — revisión 2)
- Sportradar 2024 Integrity Report — sportradar.com/content-hub/news/sportradar-reports-notable-decline-in-match-fixing-in-2024/
- Sportradar 2025 Integrity Report — sportradar.com/content-hub/news/sports-integrity-strengthens-as-global-match-fixing-declines-in-2025/
- Wikipedia "2023 Brazilian football match-fixing scandal"
- Wikipedia "2024 Brazilian football match-fixing scandal"
- Insider Sport (Apr 2026). "Brazil launches new rules to end match-fixing." — insidersport.com/2026/04/07/brazils-match-fixing-regulations/
- iGamingToday (Nov 2024). "Flamengo Bruno Henrique spot-fixing." — igamingtoday.com/flamengo-players-alleged-involvement-in-betting-scandal-raises-concerns-in-brazilian-football/
- igamingbusiness.com — "Sportradar: Brazil no longer leader in football fixing."
- Inside World Football (Sept 2025). "Bulgarian betting scandal — 46 sanctions."
- Novinite — "Bulgaria's Football 8th Most Corrupt in Europe."
- Balkan Insight (Jul 2023). "Greek football teams investigated for match-fixing allegations."
- Wikipedia "2017-2019 Belgian football fraud scandal" (Operation Zero).
- Al Jazeera (Jan 2026). "China bans 73 in latest corruption scandal."
- Vietnam News (Dec 2023). "V.League 2 match-fixing scandal."
- Jerusalem Post — "Israeli FA League A North 13-game fix."
- LawInSport (2018). "Cyprus FA — top-tier league likely plagued by match-fixing."
- The Black Sea — "Cypriot Deception" investigation.
- Tirana Times — "Skenderbeu 10-year UEFA ban."
- RFE/RL — "UEFA calls on Serbia over fixing."
- Forrest — "Evaluation of Sportradar FDS." sportstradingnetwork.com.
- Asser Institute. "The Odds of Match-Fixing." 2015.
- Europol. "Organised Crime in Sports Corruption."
- Springer (2024). "Analysing Betting Markets to Detect Manipulation."

### Hidden primary leagues — sources (NUEVO — revisión 2)
- Caan Berry. "Best leagues for Betfair trading." caanberry.com/the-best-football-leagues-for-trading-on-betfair/
- Performance Odds. "Eredivisie totals trend." performanceodds.com/football-stats-trends/eredivisie-high-scoring-trends-dutch-footballs-wild-november/
- FootyStats — Polish Ekstraklasa xG. footystats.org/poland/ekstraklasa/xg
- FootyStats — Israeli Premier League xG. footystats.org/israel/israeli-premier-league/xg
- FootyStats — Belgian Pro League xG. footystats.org/belgium/pro-league/xg
- Pinnacle. "Find value betting on Scottish soccer." (own admission Scottish has wide odds)
- Wikipedia — Liga I (Romania) format.
- Sports Insider — "Betano sponsors Lokomotiv Sofia."
- Wikipedia — Betano company / Kaizen Gaming country list.

### League-specific / Betano empirical
- Nortis Journal study on Brazilian home advantage. nortisjournal.com/index.php/pub/article/view/6
- Joseph Buchdahl, Football-Data.co.uk archive.
- Pinnacle betting resources (multiple).
- Sportsboom Betano Review 2026.
- Covers Betano Sportsbook Review 2026.
- SBR Betano Review (props posted ahead of competitors).
- Reddit r/sportsbook Betano threads 2024-2026.
- Romanian betfaq.ro forums on Betano regional softness.

---

## 10. Acceptance criteria for this strategy doc

This document is **ratified** when:
1. ✅ Operator philosophy explicitly captured (Section 0)
2. ✅ Discards documented with evidence (Section 1) — incluye EV+ services discard (revisión 3)
3. ✅ Tier-1 leagues ranked with criteria (Section 2)
4. ✅ Tier-1 markets ranked with edge basis (Section 3)
5. ✅ Implementation vectors prioritized (Section 4)
6. ✅ Validation metrics specified (Section 6)
7. ✅ Phase roadmap proposed (Section 7) — incluye pacing decision agresivo+híbrido (revisión 3)
8. ✅ **Operator decisions resolved (Section 8)** — done 2026-05-02
9. ✅ Bibliography traceable (Section 9)
10. ✅ Match-fixing risk register + filtering protocols (Section 11)
11. ✅ V-12 Tournament Monte Carlo añadido (Section 12) — NEW revisión 3
12. ✅ CV showcase mapping (Section 13) — NEW revisión 3
13. ✅ 12-month aggressive timeline (Section 14) — NEW revisión 3
14. ✅ EV+ services explicit rationale (Section 15) — NEW revisión 3

**Status: RATIFIED revisión 3 (2026-05-03)**. Este documento es ahora el input contract para `/gsd-discuss-phase` de Phase 3.5 (V-01, V-02) y Phase 4.5 (V-03), con pacing agresivo paralelizado.

---

## 11. Match-Fixing Risk Register + Filtering Protocols (NEW — revisión 2)

### Risk classification por liga (todos los Tier-1 + Tier-2 + descartados)

| Liga | Risk Level | Status | Notas operacionales |
|---|---|---|---|
| Liga Portugal Primeira | **LOW** | Tier-1 anchor | Apito Dourado histórico (2004); quieto 2020-26 |
| Romanian SuperLiga | **LOW-MEDIUM** | Tier-1 anchor | No 2024-25 público; Eastern European concerns generales |
| Greek Super League | **MEDIUM-HISTORICAL** | Tier-1 anchor (vigilancia) | Koriopolis 2011-2015 + Interpol Jul 2023 (18 equipos investigados, no condenas) |
| Eredivisie | **LOW** | Tier-1 anchor | KNVB integrity strong, no UEFA flags 2020-26 |
| Belgian Pro League | **LOW-MEDIUM** | Tier-1 anchor | Operation Zero (2018-19) financial fraud + 1-2 fixed; sin major 2024-25 |
| Polish Ekstraklasa | **LOW** | Tier-1 anchor | Post-Operacja Fryzjer cleanup (2007-2010) successful |
| Liga MX | **LOW** | Tier-1 anchor | Liga Premier MX 3rd tier scandal 2024 (separado, no contamina) |
| Norwegian Eliteserien | **LOW** | Tier-1 anchor (joint w/ Allsvenskan) | Sin scandals 2020-26 |
| Swedish Allsvenskan | **LOW-MEDIUM** | Tier-1 anchor | Named en 2023 Interpol ring (sin club bans) |
| **Brasileirão Série A** | **MEDIUM** (improving) | **Tier-2 con filtros** | Caso Bruno Henrique 2024 + CBF-Sportradar partnership Apr 2025 |
| **Brasileirão Série B** | **CRITICAL** | **HARD AVOID** | Operação Penalidade Máxima target específico de last-round matches |
| Czech Chance Liga | MEDIUM | Tier-2 | 2023 Austrian-led Interpol/Eurojust ring named |
| Argentina Liga Profesional | MEDIUM | Tier-2 supplement | 2024 Atenas charges; Primera OK, Primera Nacional avoid |
| Liga Portugal 2 | LOW | Tier-2 candidate | Apito Dourado histórico no toca |
| Scottish Premiership | **LOW** | Tier-2 supplement | Sin top-tier fixing 2020-26 |
| Austrian Bundesliga | **LOW** | Tier-2 supplement | Limpio |
| Swiss Super League | **LOW** | Tier-2 supplement | Limpio |
| **Bulgarian Parva Liga** | **CRITICAL** | **HARD AVOID** | 46 sanctions Sept 2025; Sportradar-Police MOU activo |
| **Cypriot 1st Division** | **CRITICAL** | **HARD AVOID** | 75 partidos investigados, 0 condenas; CFA admission |
| **Albanian Superliga** | **CRITICAL** | **HARD AVOID** | Skenderbeu UEFA-banned 10 años |
| **Serbian SuperLiga** | **HIGH** | **HARD AVOID** | UEFA flags 2021 |
| **Slovak SuperLiga** | MEDIUM-HIGH | AVOID anchor | 2023 Interpol ring; thin liquidity |
| Hungarian NB I | MEDIUM | Avoid anchor | Small market low scrutiny |
| Croatian HNL | MEDIUM | Avoid anchor (overfit) | 180 fx, Dinamo dominance |
| **Chinese Super League** | **CRITICAL** | **HARD AVOID** | 73 lifetime bans Jan 2026 |
| **Indonesia Liga 1** | **CRITICAL** | **HARD AVOID** | Persistent referee-mafia |
| **Vietnamese V.League** | **HIGH** | **HARD AVOID** | Dec 2023 prosecutions |
| K League 1 | LOW-MEDIUM | Defer | Post-2011 cleanup; Betano coverage thin |
| J-League | **LOW** | Defer | Limpio; Betano coverage thin |

### Filtering protocols obligatorios

**Protocol F-01: Sportradar suspicious-match cross-reference**
- **Pre-train**: cruzar dataset histórico contra Sportradar's annual suspicious-match lists. Drop fixtures flagged.
- **Live (post-V-04)**: pre-pick check — si fixture está flagged por IBIA quarterly alert o Sportradar en tiempo real → skip pick automáticamente.
- **Implementation**: tabla `suspicious_fixtures` en Supabase, populated manualmente desde reports + automation futuro.

**Protocol F-02: Dead-rubber boolean feature**
- Feature `is_dead_rubber = (top4_status_locked OR relegation_locked OR mid_table_no_european_spot) AND matchday > total_matchdays - 5`
- **No skip automático** pero **lower confidence threshold** (Edge >= 7% en lugar de 5%) cuando active.
- Especialmente crítico en Brasileirão Série A/B + Romanian playout + Argentine Primera.

**Protocol F-03: Card-market hard-block en Brazil**
- En Brasileirão A y B (cuando se modele Série A en Tier-2): **no generar picks en card markets**. Esto se enforce en pick_engine market filter.
- Se relaja solo cuando Sportradar reporte ≥3 años consecutivos sin fixing en card markets brasileiros.

**Protocol F-04: Anomalous reverse line movement detection**
- CLV por sí solo es un fixing detector — reverse line moves anómalos en small markets son red flags.
- Cuando un fixture muestra opening→closing movement >15% en mercados que no son mainline (cards, corners, ATG) sin news pública → flag for manual review.

**Protocol F-05: Markets que fixers preferentemente target**
- **High-risk markets** (filter regardless of league):
  - Late-game yellow/red cards (especially individual player props)
  - Total Goals (O/U) extremes en lower divisions
  - BTTS en low-stakes dead-rubbers
  - Asian Handicap large lines (-2.5+, +2.5+)
- **Low-risk markets**:
  - 1X2 mainline
  - Total Corners
  - Total Cards (with referee FE — fixing usually targets individual player cards, not totals)

### Periodic review cadence

- **Anual**: revisar Sportradar Integrity Report (publicado Q1 cada año). Re-classify ligas si surge nueva evidencia.
- **Trimestral**: cruzar IBIA quarterly alerts contra picks generados. Identificar si alguna pick acabó siendo suspicious post-hoc.
- **Inmediato**: si UEFA / Sportradar flag emerge en una Tier-1 league activa → pause picks en esa liga + audit + decisión Tier (mantener / demote / hard-avoid).

---

## 12. V-12: Tournament Monte Carlo for Futures Markets (NEW — revisión 3)

### Por qué añadirlo
Falta en revisión 2. Aporta:
- **Edge real (volumen bajo)**: futures markets ("ganador del torneo") son notoriamente ineficientes — long-tail bias + favorites overweighting documentados (Buchdahl Pinnacle posts; Constantinou 2018).
- **CV value alto**: lenguaje universal quant ("Monte Carlo simulation of 100,000 bracket runs against market futures pricing"). 1 bullet point listo para entrevista.
- **Effort bajo**: el modelo existente ya produce `ProbabilityMap` por match. Simulación es trivial encima de eso.

### Scope (cuando se implemente)
- **Torneos target**:
  - UEFA Champions League (knockout phase + group stage simulation)
  - UEFA Europa League
  - UEFA Conference League
  - Copa Libertadores (relevante para Tier-1 LATAM exposure)
  - Copa Sudamericana
  - Mundial / Eurocopa cuando aplique
- **Markets target**:
  - "Ganador del torneo" (outright winner)
  - "Llegada a la final"
  - "Top scorer del torneo"
  - "Eliminación en fase de grupos" (specific team)
- **Frequency**: pre-tournament (post-sorteo) + post-fase-de-grupos (cuando knockout bracket es conocido).

### Algoritmo
```
1. Para cada equipo participante, computar ProbabilityMap del modelo actual (post-V-03 + V-08)
2. Por cada matchup posible en el bracket:
   a. Simular resultado vía Bivariate Poisson score grid (penaltyblog ya implementa)
   b. Para empates en knockout: aplicar penalty shootout model (random uniform o data-driven)
3. Iterar 100,000 veces
4. Aggregate: P(team X wins tournament), P(team X reaches final), etc.
5. Compare contra futures odds en Betano
6. Edge filter: si P_modelo × futures_odds - 1 > 7% (umbral más alto que mainline por mayor varianza) → pick
```

### Caveats
- **Sample size limitation**: solo 1 torneo por temporada × 5 torneos = ~5 picks/año. **Volumen bajo** → no genera ingresos sustantivos pero CV value justifica el effort.
- **Validation difficulty**: con n=5/año, validar empíricamente toma 3+ años. Aceptar como speculative bet con **CV-first justification**, no income-first.
- **Stake cap explícito**: max 1% bankroll por pick (vs 1.5-2% mainline) por tail risk.

### Plans estimados
- 2-3 plans en Phase 8+:
  - Plan 1: penaltyblog tournament simulator wrapper + bracket logic
  - Plan 2: Futures odds ingestion (The Odds API supports outright markets)
  - Plan 3: EV pipeline + Telegram delivery for low-frequency picks

---

## 13. CV Showcase Mapping (NEW — revisión 3)

Los 5 elevator pitches que el proyecto construye, mapeados a artifacts del codebase:

### Bullet #1 — Production ML system (foundational)
> "Built a production betting intelligence platform end-to-end: async ingestion (httpx + tenacity), feature engineering (Polars), gradient boosting ensemble (XGBoost+CatBoost+LightGBM stacked) with calibration (Platt/Isotonic), Supabase persistence, scheduled execution (APScheduler), Telegram alerts, all under TDD with structured logging."

**Artifacts**:
- `src/bip/sports/football/features.py` (Polars feature engineering, point-in-time correctness)
- `src/bip/train/pipeline.py` (TrainingPipeline orchestrator)
- `src/bip/train/stacking.py` (nested OOF stacking)
- `src/bip/scheduler/orchestrator.py` (APScheduler job model)
- `src/bip/core/picks/engine.py` (Phase 3 — when shipped)
- `.planning/STATE.md` (project tracking)

**Demuestra**: software engineering + ML pipeline + production discipline

### Bullet #2 — Honest backtesting (lo que separa quants de hobbyists)
> "Walk-forward backtest with explicit temporal leakage assertion per fold, nested OOF stacking to avoid sklearn StackingClassifier's stratified-CV pitfall, opening odds + 1.5% slippage applied from day 1 (not closing odds — retrofit invalidates results), Ranked Probability Score + Brier decomposition + reliability diagrams per league."

**Artifacts**:
- `src/bip/train/walkforward.py:36` (leakage assertion)
- `src/bip/train/stacking.py:88-98` (nested OOF, hand-rolled vs sklearn)
- `src/bip/train/backtest.py` (slippage + CLV math)
- `src/bip/train/calibration.py` (FrozenEstimator pattern, sklearn 1.8 compliant)

**Demuestra**: rigor de validación, conocimiento de pitfalls comunes (Constantinou-Fenton 2012)

### Bullet #3 — Player-level alpha (Pappalardo 2019)
> "Implemented Pappalardo 2019 PlayeRank methodology adapted to API-Football tier: minutes-weighted exponentially-decayed per-90 player ratings, position-weighted team aggregation (Tsokos 2023 weights), replacement-player delta computation, re-scored at T-30 minutes when lineups confirm. Validated +3-7% AUC lift on the ~12% of fixtures with lineup surprises."

**Artifacts** (Phase 4.5):
- `src/bip/sports/football/player_ratings.py` (V-03 implementation, NEW)
- `src/bip/sports/football/lineup_delta.py` (V-03 — T-30min re-scoring, NEW)
- Walk-forward validation report con AUC delta

**Demuestra**: paper-to-implementation, attention to academic detail

### Bullet #4 — Bayesian uncertainty (PyMC)
> "Hierarchical Poisson goal model in PyMC with team random effects, time-varying parameters via state-space, posteriors enabling uncertainty-aware Kelly sizing — variance of probability estimate modulates stake fraction. Sample size constraints handled via cross-league shrinkage (Baio-Blangiardo 2010)."

**Artifacts** (V-08, P1 promoted):
- `src/bip/train/bayesian_model.py` (penaltyblog BayesianHierarchicalGoalModel wrapper, NEW)
- `src/bip/core/picks/uncertainty_kelly.py` (uncertainty-aware Kelly modulation, NEW)
- Posterior diagnostics notebook (Stan/PyMC traceplots)

**Demuestra**: probabilistic programming, uncertainty quantification, decision theory

### Bullet #5 — Novel: closing-line prediction (V-07)
> "Trained XGBoost regressor predicting Pinnacle's closing line from opening odds + early movement + injury news + lineup-strength delta. Bets opening lines where predicted close diverges > 5%. CLV is monotonically positive by construction. No public implementation found in the literature — implements an extension of Levitt 2004 / Forrest-Goddard-Simmons 2005."

**Artifacts** (V-07, mes 9-11):
- `src/bip/train/closing_line_predictor.py` (NEW)
- Tick-data ingestion pipeline (extends `src/bip/clv/`)
- Validation report comparing CLV de divergence-based picks vs mainline picks

**Demuestra**: original thinking, market microstructure understanding

### Optional Bullet #6 — Tournament Monte Carlo (V-12)
> "Monte Carlo simulation 100K bracket runs of Champions League / Copa Libertadores / Mundial vs futures market pricing, exploiting documented long-tail bias in tournament winner odds (Buchdahl Pinnacle analyses)."

**Artifacts** (V-12, mes 11-12):
- `src/bip/train/tournament_simulator.py` (NEW)

**Demuestra**: Monte Carlo simulation, market structure awareness

### Blog post cadence (recomendado)
1. **Mes 4**: Post #1 — "Implementing Pappalardo 2019 PlayeRank with API-Football tier data"
2. **Mes 7**: Post #2 — "Bayesian hierarchical goal models with PyMC: uncertainty-aware Kelly sizing"
3. **Mes 11**: Post #3 — "Closing-line prediction: an extension of Levitt 2004 for solo quants"

Plataformas: Medium (visibilidad), arXiv pre-print (credibilidad), personal blog (control). Mínimo Medium + tweet announcement.

---

## 14. 12-Month Aggressive Timeline (NEW — revisión 3)

**Pacing operador-aprobado 2026-05-03**: AGRESIVO + HÍBRIDO. Phase 3.5 + Phase 4.5 paralelizados.

### Sprint 1: Ship to production (Mes 1-2)
**Objetivo**: primeras 50-100 picks reales en Betano. Validar pipeline end-to-end.
- Phase 3 (12 plans): Pick Engine + Telegram + Account Protection + Claude Role C validator
- **Output**: Telegram alerts funcionando, picks persistidas, CLV records empezando a acumular
- **Sample size objetivo**: 50-100 picks reales antes de Sprint 2

### Sprint 2: Quick wins paralelos (Mes 2-4)
**Objetivo**: V-01 + V-02 + Tier-1 seeding + V-03 Plan 1-2 simultáneos.
- **Track A** (V-01): Shin-correction (~150 LOC, 1 plan)
- **Track B** (V-02): Betano coverage validation manual (1 semana de spot-checks)
- **Track C** (Seeding): Liga Portugal + Romanian + Greek + Eredivisie + Belgian + Polish + Liga MX + Eliteserien + Allsvenskan, 3 temporadas históricas cada una (~9000 partidos)
- **Track D** (V-03 Plans 1-2): player_statistics ingestion + per-90 z-score + position-weighted aggregation
- **Output**: feature_schema_version=3, 9 ligas seedeadas, primeros player ratings computados

### Sprint 3: Production stabilization + V-03 completion (Mes 4-5)
- **Phase 4**: APScheduler en VPS Hetzner, systemd, health monitoring, CLV trend alerting
- **V-03 Plans 3-4**: replacement-player delta + T-30min lineup-confirmed re-prediction wiring
- **Output**: sistema corriendo 24/7. **Bullet #3 CV listo**. Blog post #1 publicable.

### Sprint 4: Bayesian + NLP context (Mes 5-7)
**Objetivo**: el segundo CV-killer bullet. La pieza PyMC.
- **V-08 (P1)**: Bayesian Hierarchical + Weibull en ensemble (PyMC). 2-3 plans.
- **Phase 5**: Claude Role B Confidence Modifier (shadow mode) — aquí va el NLP angle correcto
- **Output**: posteriors documentados, uncertainty intervals en predict, hierarchical pooling cross-league. **Bullet #4 CV listo**. Blog post #2 publicable.

### Sprint 5: Cards + Both-halves + ATG (Mes 7-9)
**Objetivo**: monetizar mercados raros. Volumen real de picks crece.
- **Phase 5.5 (V-04)**: Referee feature engineering + cards markets (con integrity filters Sección 11)
- **Phase 6.5 (V-05)**: Both-halves model
- **Phase 6.5 (V-06)**: Anytime Goalscorer model
- **Output**: 3 mercados nuevos en producción. CLV records empiezan a accumular suficiente para V-09 (per-league Kelly multiplier).

### Sprint 6: Closing-line predictor (Mes 9-11)
**Objetivo**: el tercer CV-killer bullet. La pieza novel.
- **V-07**: Closing-line predictor (steam moves)
- **Pre-requisito**: tick data histórico de odds movement (recolectado durante Sprints 1-5)
- **Output**: **Bullet #5 CV listo**. Blog post #3 publicable.

### Sprint 7: Refinements + Monte Carlo (Mes 11-12)
- **V-12**: Tournament Monte Carlo (futures) — Champions League knockout phase ideal arrancarlo en Feb-Mar
- **V-09**: Per-league Kelly multiplier (cuando 200+ CLV records por liga × mercado disponibles)
- **V-11**: Multi-armed bandit para multi-pick days (opcional)

### Hitos verificables (no negociables)

| Mes | Hito | Verifiable cómo |
|---|---|---|
| 2 | Phase 3 shipped | Primera Telegram alert real enviada |
| 4 | Sprint 2 done | feature_schema_version=3 + 9 ligas seedeadas + V-03 Plan 1-2 verde |
| 5 | Bullet #3 CV listo | `src/bip/sports/football/player_ratings.py` + AUC report |
| 7 | Bullet #4 CV listo | `src/bip/train/bayesian_model.py` + posterior diagnostics + Phase 5 shadow mode logging |
| 9 | Cards/Both-halves/ATG en producción | 3 mercados nuevos generando picks |
| 11 | Bullet #5 CV listo | `src/bip/train/closing_line_predictor.py` + CLV monotonicity report |
| 12 | Sprint 7 complete + 5 bullets CV | 3 blog posts publicados; Sportradar Q1 2027 review |

### Riesgos del pacing agresivo (mitigación obligatoria)

1. **Validación insuficiente entre sprints**: cada vector debe tener **mínimo 2 weeks de soak time** en shadow mode antes de entrar en producción para escribir picks.
2. **Sample size para V-04 cards**: necesita n>500 picks. Si no llegamos a n=200 por mes 9, demote V-04 a Sprint 7 y promote V-07 cierre antes.
3. **PyMC compute time**: V-08 puede tardar horas en MCMC convergence — considerar Modal / Lambda Labs si entrenamiento bloquea Sprint 4.
4. **Blog post discipline**: si un sprint termina sin blog post, deuda CV crece. **Tratamiento**: blog post es deliverable bloqueante de sprint, no opcional.

---

## 15. EV+ Subscription Services Discard — Detailed Rationale (NEW — revisión 3)

### Decisión
**NO integrar Trademate Sports / RebelBetting / OddsJam / ValueBetting.app / Betburger / Surebet / BetHero / similar como signal source primario.** Ver Sección 1 para entrada compacta; esta sección documenta el rationale completo para que futuros yo no re-evalúe sin nueva evidencia.

### El mecanismo común (todos los servicios mainstream)

Todos implementan la receta de 4 pasos del paper Kaunitz, Kennedy, Pang & Castaño-Solé (2017, arXiv:1710.02824) "Beating the bookies with their own numbers":

```
1. Scrape Pinnacle odds (sharp, low margin ~2-3%)
2. Convert a no-vig probability: P_true ≈ (1/odds_pin) / overround_pin
3. Scrape ~30 soft books (Betano, bet365, William Hill, Unibet, etc.)
4. If soft_implied_prob < P_true × (1 - threshold) → flag value bet
```

**No hay XGBoost. No hay calibración. No hay features de partido.** Es un detector de **disagreement entre books**, no de match outcomes. El paper original demostró 6-8% yield sobre ~50,000 bets — hasta que **les cerraron las cuentas**. La paper documenta explícitamente el patrón de account closure.

### Por qué NO integrarlo (3 argumentos cerrados)

#### 1. Account closures son la receta más rápida de incumplir Phase 3 D-09 (60% market cap)
- Trademate FAQ explícitamente: "you will get limited"
- r/sportsbook megathreads 2022-2025: 4-12 semanas hasta primer límite por book soft
- Tu CLAUDE.md: "vary stake patterns, rotate markets" — incompatible con seguir picks Pinnacle-following concentradas

#### 2. Edge es **rented**, no **owned**
- Depende de Pinnacle siendo perpetuamente sharp Y de que tu cuenta no sea limitada
- Suscripción $120-180/mes recurrente
- 8 años de competencia: miles de subscribers cazando las mismas líneas

#### 3. Anti-narrative para CV
- Un entrevistador quant lee "uso Trademate" como zero signal de modeling skill
- La pregunta-mata-CV: "¿Tu edge sobrevive si te quito Trademate?" → respuesta "no" = rented alpha
- Tu enfoque actual (XGBoost+CB+LGBM con calibración propia + Pappalardo 2019 player rating) es **categóricamente distinto trabajo** y produce **owned alpha** trazable

### El uso DEFENDIBLE (1 mes como benchmark dataset)

Único uso que SUMA al CV en lugar de restar:

1. **Suscribirse 1 mes** a Trademate u OddsJam (NO a más de uno) — costo $120-180 one-shot
2. **NO bettear sus picks** (importante)
3. Loggear las picks que el servicio genera durante 30 días
4. Comparar contra picks que tu modelo genera en las mismas fixtures
5. Métricas:
   - Correlación de selecciones (¿coinciden?)
   - CLV divergence en picks donde discrepan
   - Cobertura: ¿el servicio detecta picks que tu modelo perdería? Si sí, ¿qué markets?
6. **Output**: research artifact `.planning/research/INDEPENDENT_MODEL_VS_PINNACLE_ARBITRAGE_BENCHMARK.md`
7. **Optional Sprint 7 deliverable** si quedó bandwidth

**Lectura de CV**: "I benchmarked my independent ML ensemble against a Pinnacle-arbitrage baseline (Trademate Sports). My model surfaced X% of picks the arbitrage baseline missed in cards/corners markets, while the baseline detected Y% of mainline value my model didn't see — demonstrating complementary signal sources."

### Servicios investigados (referencia rápida)

| Servicio | Métodología | Pricing/mo | Account closure típico | Verdict |
|---|---|---|---|---|
| Trademate Sports | Pinnacle no-vig + soft divergence | $120-180 | 6-16 semanas | NO integrar; OK 1-mes benchmark |
| RebelBetting | Same + arb mode | €129 | 6-16 semanas | NO integrar |
| OddsJam | Same para US books (DK/FD/MGM) | $79-249 | 2-4 meses (US menos sharp) | NO integrar |
| ValueBetting.app | RebelBetting clone | €80-100 | similar | NO integrar |
| Betburger / Surebet | Pure arb scraper | €70-200 | 2-6 sem (más rápido) | NO integrar |
| Pyckio | Tipsters humanos | varía | N/A | Verification platform degradada post-2020 |
| **BetHero** | **No service mainstream verificable** | N/A | N/A | **Untrusted — likely tipster reseller LATAM Telegram** |

### Inversión alternativa de $120/mes

En lugar de suscripción a EV+ service, esos $120-180/mes producen más valor en:
- **The Odds API tier más alto**: necesario para histórico de odds movement (V-07 closing-line predictor)
- **API-Football Pro Plus** (si surge necesidad de data adicional para player props)
- **Compute on-demand** (Modal / Lambda Labs) cuando V-08 PyMC corra MCMC

---

## Appendix A — Suggested next concrete actions

Una vez Phase 3 (Pick Engine) ship a producción y mande primeras 50-100 picks:

1. **Week 1**: V-02 — manual Betano coverage validation. Document `scripts/betano_coverage_findings.md` cubriendo Liga Portugal Primeira, Romanian SuperLiga, Greek SL, Eredivisie, Belgian Pro, Polish Ekstraklasa, Liga MX, Eliteserien+Allsvenskan.
2. **Week 2**: V-01 — Shin-correction PR. Single plan, ~150 LOC including tests.
3. **Week 3-4**: Tier-1 league seeding. `scripts/seed_historical.py` extended con (orden de prioridad):
   - Liga Portugal Primeira (id=94)
   - Romanian SuperLiga (id=283)
   - Greek Super League (id=197)
   - Eredivisie (id=88)
   - Belgian Jupiler Pro League (id=144)
   - Polish Ekstraklasa (id=106)
   - Liga MX (id=262)
   - Eliteserien (id=103) + Allsvenskan (id=113)
   - 3 temporadas históricas cada una (2023, 2024, 2025).
4. **Month 2**: V-03 Plan 1 — player_statistics ingestion + per-90 z-score computation
5. **Month 2**: V-03 Plan 2 — position-weighted aggregation
6. **Month 3**: V-03 Plan 3 — replacement-player delta
7. **Month 3**: V-03 Plan 4 — T-30min lineup-confirmed re-prediction wiring
8. **Month 4** (paralelo): Sportradar suspicious-match list ingestion (Protocol F-01) — manual seed inicial + tabla `suspicious_fixtures` en Supabase

Esto reordena las prioridades sin tocar Phase 3 actual. Phase 3 debe ship primero — luego se construye sobre él.

---

## Appendix B — League ID quick-reference (API-Football v3)

Verificar antes de seed con `/leagues?id=X&season=Y`:

| Liga | API-Football ID | Coverage flags a verificar |
|---|---|---|
| Liga Portugal Primeira | 94 | lineups, players, statistics_fixtures, statistics_players |
| Liga Portugal 2 | 95 | (validar Tier-2) |
| Romanian SuperLiga | 283 | lineups, players (xG via FootyStats fallback) |
| Greek Super League | 197 | lineups, players |
| Eredivisie | 88 | lineups, players, full xG |
| Belgian Jupiler Pro League | 144 | lineups, players, full xG |
| Polish Ekstraklasa | 106 | lineups, players |
| Liga MX | 262 | lineups, players, refs |
| Norwegian Eliteserien | 103 | lineups, players |
| Swedish Allsvenskan | 113 | lineups, players |
| **Brasileirão Série A** (Tier-2) | 71 | NO card-market modeling |
| Czech Chance Liga (Tier-2) | 345 | xG patchy verification needed |
| J1 League (deferred) | 98 | lineups, full coverage |
| Argentina Liga Profesional (Tier-2) | 128 | lineups, players |

**Note**: API-Football coverage flags aren't 100% reliable per their own docs. Spot-check 5 fixtures per league before committing seed effort.
