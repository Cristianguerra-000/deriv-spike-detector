# Laboratorio Deriv — Roadmap 50 CRASH + 50 BOOM

> Cada algoritmo vive en su propio archivo.
> Tachamos con [x] cuando está implementado y testeado en producción.

---

## CRASH Index — 50 Algoritmos

### Bloque A · Detección y Timing de Spikes (10)
| # | Archivo | Nombre | Qué mide |
|---|---------|--------|----------|
| 1 | `spike_detector.py` | `cb.spike_detector` ✅ | Detecta spike en vela actual + riesgo acumulado |
| 2 | `spike_overdue_score.py` | `crash.spike_overdue` ✅ | % del intervalo declarado consumido (0–100) |
| 3 | `spike_magnitude.py` | `crash.spike_magnitude` ✅ | Tamaño promedio de los últimos spikes en puntos |
| 4 | `spike_interval_variance.py` | `crash.spike_interval_var` ✅ | ¿Los intervalos entre spikes son regulares o caóticos? |
| 5 | `spike_cluster_risk.py` | `crash.spike_cluster` ✅ | ¿Hubo otro spike reciente? → riesgo de cluster |
| 6 | `tick_countdown.py` | `crash.tick_countdown` ✅ | Estimación de ticks restantes hasta próximo spike |
| 7 | `consecutive_spike_detector.py` | `crash.consec_spikes` ✅ | Detecta 2+ spikes en N barras |
| 8 | `spike_depth_score.py` | `crash.spike_depth` ✅ | Profundidad del último crash en puntos y % |
| 9 | `spike_frequency_change.py` | `crash.freq_change` ✅ | ¿Los spikes se están acelerando o espaciando? |
| 10 | `spike_calendar.py` | `crash.spike_calendar` ✅ | Distribución histórica de intervalos entre spikes |

### Bloque B · Análisis del Drift (10)
| # | Archivo | Nombre | Qué mide |
|---|---------|--------|----------|
| 11 | `inter_spike_drift.py` | `crash.drift_slope` ✅ | Pendiente del drift alcista entre spikes |
| 12 | `drift_channel.py` | `crash.drift_channel` ✅ | Canal de precios entre spikes (sup/inf/mid) |
| 13 | `drift_acceleration.py` | `crash.drift_accel` ✅ | ¿El drift se acelera? (2ª derivada) |
| 14 | `drift_exhaustion.py` | `crash.drift_exhaust` ✅ | Signos de que el drift alcista se agota |
| 15 | `drift_linearity.py` | `crash.drift_linear` ✅ | R² del drift: ¿qué tan limpio es el canal? |
| 16 | `drift_volatility.py` | `crash.drift_vol` ✅ | Ruido (ATR) dentro del drift |
| 17 | `micro_drift_slope.py` | `crash.micro_drift` ✅ | Pendiente de las últimas 10 velas |
| 18 | `drift_consistency.py` | `crash.drift_consist` ✅ | ¿Las velas del drift son consistentes en tamaño? |
| 19 | `recovery_trajectory.py` | `crash.recovery_traj` ✅ | Ángulo y velocidad de recuperación post-spike |
| 20 | `recovery_completion.py` | `crash.recovery_pct` ✅ | % del precio recuperado desde el último spike |

### Bloque C · Tensión Pre-Spike (10)
| # | Archivo | Nombre | Qué mide |
|---|---------|--------|----------|
| 21 | `pre_spike_tension.py` | `crash.bull_streak` ✅ | Racha de velas alcistas consecutivas |
| 22 | `pre_spike_tension.py` | `crash.body_expand` ✅ | ¿Los cuerpos crecen? → tensión compradora |
| 23 | `pre_spike_tension.py` | `crash.wick_compress` ✅ | Mechas superiores reduciéndose → euforia compradora |
| 24 | `pre_spike_tension.py` | `crash.price_vel` ✅ | Velocidad de subida del precio |
| 25 | `pre_spike_tension.py` | `crash.mom_div` ✅ | Precio sube pero momentum baja → divergencia bajista |
| 26 | `pre_spike_tension.py` | `crash.consolidation` ✅ | Rango estrecho antes del crash |
| 27 | `pre_spike_tension.py` | `crash.tension` ✅ | Score compuesto de tensión pre-crash (0–100) |
| 28 | `pre_spike_tension.py` | `crash.upper_wick` ✅ | Ratio mecha superior / cuerpo → presión vendedora latente |
| 29 | `pre_spike_tension.py` | `crash.range_compress` ✅ | ATR contrayéndose → explosión próxima |
| 30 | `pre_spike_tension.py` | `crash.body_seq` ✅ | Patrón de tamaño de cuerpos en últimas N velas |

### Bloque D · Análisis Post-Spike (10)
| # | Archivo | Nombre | Qué mide |
|---|---------|--------|----------|
| 31 | `post_spike_behavior.py` | `crash.post_spike` | Comportamiento de las 5 velas tras el spike |
| 32 | `crash_retracement.py` | `crash.retracement` | Niveles de retroceso Fibonacci desde el spike |
| 33 | `recovery_speed.py` | `crash.recovery_speed` | Barras necesarias para recuperar el 50% / 100% |
| 34 | `crash_impact_score.py` | `crash.impact` | Tamaño × velocidad del crash → score de impacto |
| 35 | `post_crash_momentum.py` | `crash.post_mom` | Momentum RSI en las 10 barras post-crash |
| 36 | `crash_echo.py` | `crash.echo` | Spike pequeño después de spike grande |
| 37 | `crash_volume_proxy.py` | `crash.vol_proxy` | Tamaño de cuerpo como proxy de volumen |
| 38 | `crash_aftermath_duration.py` | `crash.aftermath` | Cuántas barras tarda en normalizarse |
| 39 | `double_bottom_crash.py` | `crash.double_bot` | Doble suelo post-crash |
| 40 | `reversal_confirmation.py` | `crash.reversal` | Confirmación técnica de reversión post-crash |

### Bloque E · Probabilidad y Señal Final (10)
| # | Archivo | Nombre | Qué mide |
|---|---------|--------|----------|
| 41 | `crash_probability.py` | `crash.probability` | Modelo probabilístico de crash en próximas N velas |
| 42 | `crash_risk_composite.py` | `crash.risk_composite` | Score compuesto ponderado de todos los señales |
| 43 | `safe_zone.py` | `crash.safe_zone` | Zona segura para mantener posición larga |
| 44 | `danger_zone.py` | `crash.danger_zone` | Zona de máximo riesgo de crash |
| 45 | `regime_classifier.py` | `crash.regime` | Clasificador: DRIFT / TENSIÓN / SPIKE / RECUPERACIÓN |
| 46 | `cycle_phase.py` | `crash.cycle_phase` | Fase del ciclo: inicio / medio / final del drift |
| 47 | `optimal_entry.py` | `crash.optimal_entry` | Mejor momento para entrar después de un crash |
| 48 | `crash_confidence.py` | `crash.confidence` | Confianza estadística en la señal actual |
| 49 | `next_crash_price.py` | `crash.next_price` | Estimación del precio cuando ocurra el próximo crash |
| 50 | `crash_signal_final.py` | `crash.signal_final` | **SEÑAL FINAL**: BUY / WAIT / AVOID / EXIT |

---

## BOOM Index — 50 Algoritmos

### Bloque A · Detección y Timing de Spikes (10)
| # | Archivo | Nombre | Qué mide |
|---|---------|--------|----------|
| 1 | *(shared)* | `cb.spike_detector` ✅ | Detecta spike actual + riesgo acumulado |
| 2 | `boom_overdue_score.py` | `boom.spike_overdue` ✅ | % del intervalo declarado consumido (0–100) |
| 3 | `boom_magnitude.py` | `boom.spike_magnitude` ✅ | Tamaño promedio de los últimos booms en puntos |
| 4 | `boom_interval_variance.py` | `boom.spike_interval_var` ✅ | ¿Los intervalos son regulares o caóticos? |
| 5 | `boom_cluster_risk.py` | `boom.spike_cluster` ✅ | ¿Hubo otro boom reciente? → riesgo de cluster |
| 6 | `boom_tick_countdown.py` | `boom.tick_countdown` ✅ | Estimación de ticks restantes hasta próximo boom |
| 7 | `boom_consecutive.py` | `boom.consec_spikes` ✅ | Detecta 2+ booms en N barras |
| 8 | `boom_height_score.py` | `boom.spike_depth` ✅ | Altura del último boom en puntos y % |
| 9 | `boom_frequency_change.py` | `boom.freq_change` ✅ | ¿Los booms se están acelerando o espaciando? |
| 10 | `boom_spike_calendar.py` | `boom.spike_calendar` ✅ | Distribución histórica de intervalos |

### Bloque B · Análisis del Drift (10)
| # | Archivo | Nombre | Qué mide |
|---|---------|--------|----------|
| 11 | `boom_drift_analysis.py` | `boom.drift_slope` ✅ | Pendiente del drift BAJISTA entre booms |
| 12 | `boom_drift_analysis.py` | `boom.drift_channel` ✅ | Canal de precios entre booms |
| 13 | `boom_drift_analysis.py` | `boom.drift_decel` ✅ | ¿El drift bajista se desacelera? (boom próximo) |
| 14 | `boom_drift_analysis.py` | `boom.drift_exhaust` ✅ | Signos de que el drift bajista se agota |
| 15 | `boom_drift_analysis.py` | `boom.drift_linear` ✅ | R² del drift bajista |
| 16 | `boom_drift_analysis.py` | `boom.drift_vol` ✅ | Ruido dentro del drift bajista |
| 17 | `boom_drift_analysis.py` | `boom.micro_drift` ✅ | Pendiente de las últimas 10 velas |
| 18 | `boom_drift_analysis.py` | `boom.drift_consist` ✅ | ¿Las velas del drift son consistentes? |
| 19 | `boom_drift_analysis.py` | `boom.correction_traj` ✅ | Ángulo y velocidad de corrección post-boom |
| 20 | `boom_drift_analysis.py` | `boom.correction_pct` ✅ | % corregido desde el último boom |

### Bloque C · Tensión Pre-Boom (10)
| # | Archivo | Nombre | Qué mide |
|---|---------|--------|----------|
| 21 | `pre_spike_tension.py` | `boom.bear_streak` ✅ | Racha de velas bajistas consecutivas |
| 22 | `pre_spike_tension.py` | `boom.body_expand` ✅ | ¿Los cuerpos bajistas crecen? → tensión vendedora |
| 23 | `pre_spike_tension.py` | `boom.wick_compress` ✅ | Mechas inferiores reduciéndose → capitulación |
| 24 | `pre_spike_tension.py` | `boom.price_vel` ✅ | Velocidad de caída del precio |
| 25 | `pre_spike_tension.py` | `boom.mom_div` ✅ | Precio baja pero momentum sube → divergencia alcista |
| 26 | `pre_spike_tension.py` | `boom.consolidation` ✅ | Rango estrecho antes del boom |
| 27 | `pre_spike_tension.py` | `boom.tension` ✅ | Score compuesto de tensión pre-boom (0–100) |
| 28 | `pre_spike_tension.py` | `boom.lower_wick` ✅ | Ratio mecha inferior / cuerpo → presión compradora latente |
| 29 | `pre_spike_tension.py` | `boom.range_compress` ✅ | ATR contrayéndose → explosión próxima |
| 30 | `pre_spike_tension.py` | `boom.body_seq` ✅ | Patrón de tamaño de cuerpos en últimas N velas |

### Bloque D · Análisis Post-Boom (10)
| # | Archivo | Nombre | Qué mide |
|---|---------|--------|----------|
| 31 | `post_boom_behavior.py` | `boom.post_spike` | Comportamiento de las 5 velas tras el boom |
| 32 | `boom_correction_levels.py` | `boom.correction_lvl` | Niveles de corrección desde el boom |
| 33 | `boom_correction_speed.py` | `boom.correction_speed` | Barras para corregir 50% / 100% del boom |
| 34 | `boom_impact_score.py` | `boom.impact` | Tamaño × velocidad del boom → score |
| 35 | `post_boom_momentum.py` | `boom.post_mom` | Momentum RSI en las 10 barras post-boom |
| 36 | `boom_echo.py` | `boom.echo` | Boom pequeño después de boom grande |
| 37 | `boom_volume_proxy.py` | `boom.vol_proxy` | Tamaño de cuerpo como proxy de volumen |
| 38 | `boom_aftermath_duration.py` | `boom.aftermath` | Cuántas barras tarda en normalizarse |
| 39 | `double_top_boom.py` | `boom.double_top` | Doble techo post-boom |
| 40 | `boom_reversal_confirmation.py` | `boom.reversal` | Confirmación técnica de reversión post-boom |

### Bloque E · Probabilidad y Señal Final (10)
| # | Archivo | Nombre | Qué mide |
|---|---------|--------|----------|
| 41 | `boom_probability.py` | `boom.probability` | Modelo probabilístico de boom en próximas N velas |
| 42 | `boom_risk_composite.py` | `boom.risk_composite` | Score compuesto ponderado de todas las señales |
| 43 | `boom_safe_zone.py` | `boom.safe_zone` | Zona segura para mantener posición corta |
| 44 | `boom_danger_zone.py` | `boom.danger_zone` | Zona de máximo riesgo de boom |
| 45 | `boom_regime_classifier.py` | `boom.regime` | Clasificador: DRIFT / TENSIÓN / SPIKE / CORRECCIÓN |
| 46 | `boom_cycle_phase.py` | `boom.cycle_phase` | Fase del ciclo: inicio / medio / final del drift |
| 47 | `boom_optimal_entry.py` | `boom.optimal_entry` | Mejor momento para entrar después de un boom |
| 48 | `boom_confidence.py` | `boom.confidence` | Confianza estadística en la señal actual |
| 49 | `next_boom_price.py` | `boom.next_price` | Estimación del precio cuando ocurra el próximo boom |
| 50 | `boom_signal_final.py` | `boom.signal_final` | **SEÑAL FINAL**: SELL / WAIT / AVOID / EXIT |

---

## Progreso global

- CRASH implementados: 30 / 50
- BOOM implementados: 29 / 50
- Total: **59 / 100**

> Actualizar este archivo marcando [x] en la tabla conforme se implementan.
