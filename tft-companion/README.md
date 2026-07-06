# TFT Companion

Herramienta de escritorio (Python + PySide6) de análisis y planificación de estrategia para Teamfight Tactics: calculadora de probabilidades de tienda, navegador de composiciones meta, planificador de tablero, motor de recomendaciones de compra, tracker de economía y overlay transparente.

> Proyecto personal de aprendizaje. Estado inicial pero funcional: los cinco módulos arrancan y se retroalimentan entre sí desde el primer `run`.

## Instalación y ejecución

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  ·  source .venv/bin/activate en Linux/mac
pip install -e .                # instala PySide6 + requests y el paquete en editable
tft-companion                   # o: python -m tft_companion
```

Tests del núcleo (no requieren Qt):

```bash
pip install -e .[dev]
pytest
```

## Arquitectura

Capas estrictas, dependencia solo hacia abajo. `core/` es Python puro (sin Qt, sin red, sin disco): todo lo testeable vive ahí.

```
src/tft_companion/
├── core/                  # DOMINIO — puro, testeado
│   ├── models.py          #   Champion, SetData, GameState, MetaComp, GameSnapshot…
│   ├── odds.py            #   matemática del pool y la tienda (+ Monte Carlo)
│   ├── economy.py         #   interés, ingreso, XP, consejos
│   └── recommender.py     #   motor de recomendaciones (patrón Strategy)
├── data/                  # ACCESO A DATOS
│   ├── cache.py           #   caché de disco con TTL (obligatoria para APIs públicas)
│   ├── providers/         #   StaticDataProvider / CompProvider (protocolos)
│   │   ├── cdragon.py     #     CommunityDragon: campeones y traits del set actual
│   │   └── comps.py       #     comps: JSON local (default) + MetaTFT (no oficial)
│   └── local/             #   datos por set: shop_odds.set17.json, comps.sample.json
├── game/                  # LECTURA DE LA PARTIDA (GameDataSource, pluggable)
│   ├── source.py          #   el contrato + análisis de enfoques
│   ├── manual.py          #   input del usuario (prioridad máxima, siempre gana)
│   ├── live_client.py     #   Live Client Data API de Riot (127.0.0.1:2999)
│   ├── lcu.py             #   LCU/lockfile: contexto pre/post partida
│   └── ocr.py             #   experimental: captura de pantalla + Tesseract
├── services/              # ORQUESTACIÓN (Qt, sin UI)
│   ├── game_tracker.py    #   fusiona fuentes por prioridad → señal state_changed
│   ├── static_data.py     #   monta SetData (CDragon + JSON local) con fallback offline
│   ├── bus.py             #   EventBus (señales comp_selected, notify)
│   └── workers.py         #   trabajo bloqueante en QThreadPool
├── ui/                    # PRESENTACIÓN — solo reacciona a señales
│   ├── main_window.py
│   ├── widgets/           #   odds, comps, tablero, recomendaciones, economía
│   └── overlay/           #   overlay transparente always-on-top
├── app.py                 # composition root: TODO el wiring vive aquí
└── config.py
```

Flujo de datos: `GameDataSource(s) → GameTracker → señal state_changed → widgets/overlay`, y `CompBrowser → EventBus.comp_selected → tablero + recomendaciones + overlay`. Ningún widget conoce a otro widget.

## Decisión clave: cómo leer el estado del juego

No existe una vía única y fiable, así que la app lo modela como **fuentes intercambiables** que emiten observaciones parciales (`GameSnapshot`) fusionadas por prioridad:

| Enfoque | Qué da | Fiabilidad | Riesgo/coste | Veredicto |
|---|---|---|---|---|
| **Manual (UI)** | Todo, incluido scouting (copias en rivales), que ninguna API expone | Total | Requiere clicks del usuario | **Base. Implementado y con prioridad máxima** |
| **Live Client Data API** (`https://127.0.0.1:2999`) | API local *oficial*; en TFT expone solo un subconjunto del payload de LoL | Media; cambia por parche | Cero riesgo; hay que mapear campos empíricamente | **Implementado** como enriquecimiento, con `dump()` para explorar el payload real en partida |
| **LCU (lockfile)** | Lobby, invocador, historial. **No** el tablero en vivo | Alta pre/post partida | No oficial pero tolerado y de solo lectura | **Implementado** como utilidad de contexto |
| **OCR de pantalla** | Nombres de la tienda, oro, nivel… leyendo *tu propia pantalla* | Baja-media; depende de resolución/skins | Sin inyección ni memoria → sin problema con Vanguard; frágil | **Stub experimental** (`pip install .[ocr]`), prioridad mínima |
| Lectura de memoria / hooks / automatización | — | — | Contra las políticas de Riot y territorio Vanguard | **Descartado por diseño** |

Límites intencionados del proyecto: nada de leer memoria del proceso, modificar el cliente ni automatizar inputs (comprar/rollear por ti). Los overlays informativos sin inyección son la categoría que Riot tolera (MetaTFT, Blitz, etc. funcionan así); si algún día lo distribuyes públicamente, regístralo en el [portal de desarrolladores de Riot](https://developer.riotgames.com/) y revisa su política de apps de terceros. El overlay requiere el juego en **Borderless/Ventana** (la pantalla completa exclusiva no muestra overlays externos, y las "soluciones" a eso son inyección).

## Datos por set (importante)

Riot **no publica por API** los tamaños de pool ni las odds de tienda: son conocimiento de patch notes / UI del juego, y **cambian con cada set**. Por eso viven en `data/local/shop_odds.set17.json`:

- `pool_sizes` 30/25/18/10/9 (confirmados Sets 14–17).
- Odds Set 17 ancladas en los puntos verificados (nivel 8 → 30% de 4-costes; nivel 9 → 33%/15%); el resto es la tabla base histórica → **verifica** contra el icono de odds del propio juego o [metatft.com/tables/shop-odds](https://www.metatft.com/tables/shop-odds).
- **Set 18 llega el 12 de agosto de 2026**: crea `shop_odds.set18.json` y apunta `AppConfig.local_odds_file` al nuevo fichero. Los campeones se actualizan solos (CDragon `latest`).

## APIs consumidas

- **CommunityDragon** (`raw.communitydragon.org/latest/cdragon/tft/en_us.json`): campeones/traits del set vigente. Sin key, siempre al día. Cacheado 12 h.
- **Data Dragon** (`ddragon.leagueoflegends.com`): alternativa oficial con esquema parecido; suele ir un pelín por detrás. Hueco previsto en `providers/`.
- **MetaTFT**: **no tiene API pública documentada**. `MetaTFTCompProvider` es un adaptador best-effort: captura el endpoint real en la pestaña Network de su web, ponlo en `TFT_COMPANION_METATFT_URL` y adapta `_normalize()`. Cachea agresivo y respeta sus términos. La vía robusta a largo plazo: calcular tus propias stats con la **Riot Match API** (key propia gratuita).
- El formato canónico de comps es el de `data/local/comps.sample.json`; todo provider remoto normaliza a ese esquema, así que la app funciona 100% offline con tu JSON curado a mano.

## Patrones usados (y por qué)

- **Strategy** en el recommender: cada señal (rol en la comp, proximidad de estrella, sinergias, escasez de pool) es una clase `Scorer` independiente que devuelve puntos + razón legible. Añadir una señal = una clase nueva, cero cambios en el motor.
- **Observer** vía señales Qt: `GameTracker.state_changed` y `EventBus.comp_selected` desacoplan todo de todo.
- **Protocol/puertos** (`GameDataSource`, `CompProvider`, `StaticDataProvider`): las capas altas dependen de contratos, no de implementaciones.
- **Composition root** (`app.py`): una sola función construye y cablea; cambiar una pieza es cambiar una línea.

## Roadmap sugerido

1. Jugar una partida con `LiveClientSource().dump()` y mapear los campos reales que expone TFT en tu parche.
2. Calibrar `SHOP_REGIONS` del OCR con capturas a tu resolución.
3. Provider de Data Dragon + imágenes de campeones (CDragon sirve los assets) para tokens del tablero con retrato.
4. Persistir el estado del planner (posiciones editadas) por comp.
5. Hotkey global para el overlay (`pynput`) y opacidad configurable.
6. Historial de partidas vía LCU + Riot Match API para stats propias.

## Licencia y descargo

MIT. Proyecto de fans sin afiliación con Riot Games; Teamfight Tactics y League of Legends son marcas de Riot Games, Inc.
