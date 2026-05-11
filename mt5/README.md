# Crash & Boom MT5 Toolkit

Plantilla de MetaTrader 5 que porta los algoritmos clave de `algorithms/crash_boom/` al lenguaje nativo **MQL5**, aprovechando todo el potencial de MT5: historial completo, ticks reales, Strategy Tester y dibujo nativo en el gráfico.

---

## Filosofía

El sistema Python/Firebase sigue siendo la fuente de decisión en producción. Esta plantilla MT5 cumple **tres roles complementarios** que el pipeline web no puede:

1. **Análisis histórico profundo**: ejecutar los algoritmos sobre **años** de velas reales para descubrir patrones repetitivos (zonas de rebote, hora de mayor frecuencia de spikes, magnitud típica por símbolo).
2. **Calibración de parámetros**: medir empíricamente si `SPIKE_ATR_MULTIPLIER = 4.0` es óptimo por símbolo, o si debería variar.
3. **Visualización rica**: dibujar zonas de rebote, canales de drift, marcadores de spike y un panel de señal final directamente sobre el gráfico de MT5.

---

## Estructura

```
mt5/
├─ Include/
│  └─ CrashBoomCore.mqh        Núcleo: detección de spike, ATR de cuerpo, helpers
├─ Indicators/
│  ├─ CB_SpikeDetector.mq5     Marca todos los spikes históricos en el chart
│  ├─ CB_ReboundZones.mq5      Pinta zonas de rebote/rompimiento post-spike
│  ├─ CB_DriftChannel.mq5      Canal de regresión lineal del drift inter-spike
│  └─ CB_SignalFinal.mq5       Panel BUY/SELL/WAIT/AVOID/EXIT (mismo que Python)
├─ Experts/
│  └─ CB_AnalysisDashboard.mq5 EA panel: régimen, ciclo, riesgo, confianza, RSI
└─ Scripts/
   ├─ CB_CalibrateThreshold.mq5  Recorre histórico y sugiere SPIKE_ATR_MULTIPLIER óptimo
   └─ CB_ExportSpikes.mq5        Exporta a CSV todos los spikes detectados (timestamp, magnitud, intervalo)
```

---

## Instalación

1. En MT5: `Archivo → Abrir carpeta de datos` → carpeta `MQL5/`.
2. Copia el contenido de `mt5/` respetando las subcarpetas:
   - `mt5/Include/*.mqh` → `MQL5/Include/`
   - `mt5/Indicators/*.mq5` → `MQL5/Indicators/`
   - `mt5/Experts/*.mq5` → `MQL5/Experts/`
   - `mt5/Scripts/*.mq5` → `MQL5/Scripts/`
3. En MT5 abre cada `.mq5` con `MetaEditor` → F7 para compilar. No requiere DLLs.
4. Asegúrate de tener símbolos `Crash 500 Index`, `Crash 1000 Index`, `Boom 500 Index`, `Boom 1000 Index` en `Vista del mercado` (cuenta Deriv MT5).

---

## Uso típico

### A) Marcar spikes históricos
Arrastra **CB_SpikeDetector** al chart. Se pintarán flechas en cada spike detectado en las últimas N barras (configurable). Comparable visualmente con el detector de Python.

### B) Descubrir zonas de rebote
Arrastra **CB_ReboundZones**. Para cada spike pinta:
- Una **línea horizontal** en el `low` del crash (o `high` del boom) → nivel candidato de rebote.
- Un **rectángulo** con la zona de retroceso 38.2% / 61.8% Fibonacci del rebote inmediato.
- Estos niveles son los *patrones repetitivos* que buscas: el precio tiende a respetarlos en spikes futuros.

### C) Operar con la señal final
Adjunta **CB_AnalysisDashboard** (EA, no opera por sí solo, solo muestra). Verás un panel con:
```
SÍMBOLO: Crash 1000 Index
ACCIÓN:  BUY · score 78/100
Régimen: RECUPERACIÓN
Ciclo:   24%
Riesgo:  31/100
Confianza: 67%
RSI(7): 52
Velas desde crash: 18
```

### D) Calibrar el umbral
Carga **CB_CalibrateThreshold** (Script, F5). Recorre los últimos 50 000 bares con multiplicadores 2.5 → 6.0 en pasos de 0.25 y muestra en el log cuál genera intervalos más cercanos al declarado del símbolo (500, 1000…).

### E) Exportar spikes a CSV
**CB_ExportSpikes** genera `MQL5/Files/spikes_<symbol>_<period>.csv` con columnas: `time, type, price, magnitude, bars_since_prev`. Útil para análisis estadístico externo (Python, Excel, R).

---

## Ventaja real frente al sistema web

| Capacidad | Web (Python+Firebase) | Esta plantilla MT5 |
|-----------|----------------------|---------------------|
| Velas | últimas 5 000 | histórico completo del broker |
| Latencia | ~2–5 s por ciclo Railway | tiempo real (cada tick) |
| Backtest | no existe | Strategy Tester nativo |
| Dibujo de zonas | manual en canvas HTML | objetos nativos OBJ_RECTANGLE / OBJ_TREND |
| Alertas | no | popup, sonido, push, email nativos |

---

## Notas

- Los algoritmos portados son los **del bloque crítico**: spike_detector, recovery_trajectory, signal_final. Los 100 algos completos NO se portaron (ver "Reporte de Viabilidad" en la conversación). Se priorizó lo que aporta valor único en MT5.
- El `SPIKE_ATR_MULTIPLIER` por defecto es **4.0** (igual que Python). Calibra con el script antes de operar.
- La detección usa `body.quantile(0.75)` exactamente como en Python — ver implementación en `Quantile75()` dentro de `CrashBoomCore.mqh`.
- No hay puente con Firebase; esta plantilla es **independiente** y funciona offline una vez compilada.
