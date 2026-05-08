# Laboratorio de Análisis Deriv

Sistema modular para ejecutar **100+ algoritmos** de análisis sobre los mercados de Deriv (Crash, Boom, Volatility, Forex, Índices…), persistir resultados en **Firebase** y visualizarlos en un **dashboard web** con velas en vivo.

## ⚠️ Seguridad antes de empezar

1. **Revoca cualquier token compartido en chat** desde https://app.deriv.com/account/api-token y crea uno nuevo.
2. Nunca subas `.env` ni `serviceAccountKey.json` al repositorio (ya están en `.gitignore`).

## Arquitectura

```
config/        → carga de variables de entorno
core/          → cliente Deriv WS, cliente Firebase, loader de mercados
algorithms/    → 1 algoritmo por archivo, organizados por categoría
  ├─ mathematical/
  ├─ historical/
  ├─ microstructure/
  ├─ trend/
  ├─ volatility/
  └─ statistical/
pipeline/      → orquestador
dashboard/     → HTML/CSS/JS con drawer y gráfico de velas
```

## Instalación

```powershell
# 1. Clonar / abrir carpeta
cd C:\Users\galan\dERIV

# 2. Crear venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Dependencias
pip install -r requirements.txt

# 4. Configuración
copy .env.example .env
# edita .env con tu nuevo DERIV_API_TOKEN y los datos de Firebase
```

### Firebase

1. Crea un proyecto en https://console.firebase.google.com
2. Habilita **Firestore**.
3. Genera una **cuenta de servicio**: *Configuración → Cuentas de servicio → Generar nueva clave privada*.
4. Guarda el JSON como `serviceAccountKey.json` en la raíz (ya ignorado por git).
5. Copia las credenciales web a `dashboard/js/firebase-config.js`.

## Ejecutar el pipeline

```powershell
python -m pipeline.runner
```

Esto:
- Conecta al WebSocket de Deriv y se autentica.
- Descarga el catálogo completo de mercados → Firestore (`markets/*`).
- Toma velas históricas y ejecuta cada algoritmo registrado.
- Guarda resultados en Firestore (`results/{algoritmo}/{simbolo}`).

## Dashboard

Sirve la carpeta `dashboard/` con cualquier HTTP estático:

```powershell
cd dashboard
python -m http.server 5500
# abre http://localhost:5500
```

El dashboard se conecta directo al WS público de Deriv (sin token) para mostrar el catálogo y las velas en vivo. Los resultados de algoritmos se leerán de Firestore (próximo paso).

## Añadir un algoritmo

1. Crea `algorithms/<categoria>/<nombre>.py`.
2. Define una clase que herede de `AlgorithmBase` y decórala con `@register`.
3. Implementa `run(df, symbol)` que devuelva un `AlgorithmResult`.
4. Listo: el auto-loader la registrará al arrancar.

Ejemplo mínimo:

```python
from algorithms._base import AlgorithmBase, AlgorithmResult, register

@register
class MiAlgo(AlgorithmBase):
    name = "math.mi_algo"
    category = "mathematical"
    description = "Descripción corta"

    def run(self, df, symbol):
        return AlgorithmResult(self.name, symbol, value=float(df["close"].iloc[-1]))
```

## Roadmap de algoritmos (siguiente fase)

- **mathematical** (≥20): SMA, EMA, WMA, HMA, KAMA, derivada, integral, FFT, wavelets, Hilbert, Fibonacci, Gann…
- **historical** (≥15): rangos, breakouts históricos, días tipo, estacionalidad, ciclos, draw-downs…
- **microstructure** (≥15): anatomía de velas, gaps, imbalances, tick rule, footprint, VPIN…
- **trend** (≥15): regresión, MACD, ADX, SuperTrend, Aroon, Ichimoku, Donchian…
- **volatility** (≥15): ATR, Bollinger, Keltner, Chaikin, GARCH, Parkinson, Yang-Zhang…
- **statistical** (≥20): z-score, Hurst, autocorrelación, ADF, Jarque-Bera, entropía, kurtosis…

Iremos añadiéndolos uno a uno tras validar el flujo end-to-end.
