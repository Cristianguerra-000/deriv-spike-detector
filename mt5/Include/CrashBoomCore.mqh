//+------------------------------------------------------------------+
//|                                              CrashBoomCore.mqh   |
//|  Núcleo compartido del toolkit Crash/Boom para MT5.              |
//|  Réplica fiel de algorithms/crash_boom/spike_detector.py         |
//+------------------------------------------------------------------+
#property copyright "Crash/Boom MT5 Toolkit"
#property strict

#ifndef CRASH_BOOM_CORE_MQH
#define CRASH_BOOM_CORE_MQH

//------------------------------------------------------------------//
// Constantes globales (idénticas al pipeline Python)                //
//------------------------------------------------------------------//
#define CB_SPIKE_ATR_MULTIPLIER  6.0   // Calibrado: Crash 1000 M1, 100k velas
#define CB_DEFAULT_LOOKBACK      200
#define CB_SIGNAL_WINDOW         500

//------------------------------------------------------------------//
// Identificación CRASH / BOOM por nombre del símbolo                //
//------------------------------------------------------------------//
bool CB_IsCrash(const string symbol)
{
   string s = symbol; StringToUpper(s);
   return (StringFind(s, "CRASH") >= 0);
}

bool CB_IsBoom(const string symbol)
{
   string s = symbol; StringToUpper(s);
   return (StringFind(s, "BOOM") >= 0);
}

bool CB_IsSynthetic(const string symbol)
{
   return CB_IsCrash(symbol) || CB_IsBoom(symbol);
}

//------------------------------------------------------------------//
// Intervalo declarado del símbolo (Crash 500 → 500, Boom 1000 →1000)//
//------------------------------------------------------------------//
int CB_DeclaredInterval(const string symbol)
{
   string s = symbol;
   int len = StringLen(s);
   string num = "";
   for(int i = 0; i < len; i++)
   {
      ushort c = StringGetCharacter(s, i);
      if(c >= '0' && c <= '9') num += ShortToString(c);
      else if(StringLen(num) > 0) break;
   }
   if(StringLen(num) == 0) return 500;
   return (int)StringToInteger(num);
}

//------------------------------------------------------------------//
// Quantile-75 de un array (equivalente a pandas .quantile(0.75))     //
// Algoritmo "linear" — el mismo método que numpy/pandas por defecto. //
//------------------------------------------------------------------//
double CB_Quantile75(const double &arr[])
{
   int n = ArraySize(arr);
   if(n == 0) return 0.0;
   if(n == 1) return arr[0];

   double sorted[];
   ArrayResize(sorted, n);
   ArrayCopy(sorted, arr);
   ArraySort(sorted);

   double pos = 0.75 * (n - 1);
   int    lo  = (int)MathFloor(pos);
   int    hi  = (int)MathCeil(pos);
   if(lo == hi) return sorted[lo];
   double frac = pos - lo;
   return sorted[lo] * (1.0 - frac) + sorted[hi] * frac;
}

//------------------------------------------------------------------//
// Cargar últimos N bares en arrays open/high/low/close (orden       //
// cronológico ascendente: índice 0 = más antiguo, N-1 = más reciente)//
//------------------------------------------------------------------//
bool CB_LoadCandles(const string symbol, ENUM_TIMEFRAMES tf, int count,
                    double &op[], double &hi[], double &lo[], double &cl[],
                    datetime &tm[])
{
   ArraySetAsSeries(op, false);
   ArraySetAsSeries(hi, false);
   ArraySetAsSeries(lo, false);
   ArraySetAsSeries(cl, false);
   ArraySetAsSeries(tm, false);

   int copied_o = CopyOpen (symbol, tf, 0, count, op);
   int copied_h = CopyHigh (symbol, tf, 0, count, hi);
   int copied_l = CopyLow  (symbol, tf, 0, count, lo);
   int copied_c = CopyClose(symbol, tf, 0, count, cl);
   int copied_t = CopyTime (symbol, tf, 0, count, tm);

   if(copied_o <= 0 || copied_h <= 0 || copied_l <= 0 || copied_c <= 0 || copied_t <= 0)
      return false;

   int min_len = MathMin(MathMin(copied_o, copied_h), MathMin(copied_l, copied_c));
   min_len = MathMin(min_len, copied_t);

   ArrayResize(op, min_len);
   ArrayResize(hi, min_len);
   ArrayResize(lo, min_len);
   ArrayResize(cl, min_len);
   ArrayResize(tm, min_len);
   return (min_len > 0);
}

//------------------------------------------------------------------//
// Calcula el umbral de spike (cuerpo p75 × multiplicador)            //
//------------------------------------------------------------------//
double CB_SpikeThreshold(const double &op[], const double &cl[], double mult = CB_SPIKE_ATR_MULTIPLIER)
{
   int n = ArraySize(op);
   if(n == 0) return 0.0;
   double bodies[];
   ArrayResize(bodies, n);
   for(int i = 0; i < n; i++)
      bodies[i] = MathAbs(cl[i] - op[i]);
   return CB_Quantile75(bodies) * mult;
}

//------------------------------------------------------------------//
// Wick extrema en una vela (inferior para crash, superior para boom)//
//------------------------------------------------------------------//
double CB_ExtremeWick(int idx, bool is_crash,
                      const double &op[], const double &hi[], const double &lo[], const double &cl[])
{
   if(is_crash)
   {
      double base = (op[idx] > cl[idx]) ? op[idx] : cl[idx]; // max(open, close) actuando como techo
      // Python: open.clip(lower=close) - low  → equivale a max(open, close) - low? NO:
      // open.clip(lower=close) significa: si open < close, sustituir por close.
      // Resultado: max(open, close)  →  max - low  =  wick inferior desde el cuerpo.
      return base - lo[idx];
   }
   else
   {
      double top = (op[idx] > cl[idx]) ? op[idx] : cl[idx];
      return hi[idx] - top;
   }
}

//------------------------------------------------------------------//
// Detecta todos los índices de spike en una ventana                  //
// Devuelve cuántos encontró (escritos en spike_idx[])                //
//------------------------------------------------------------------//
int CB_FindSpikes(bool is_crash,
                  const double &op[], const double &hi[], const double &lo[], const double &cl[],
                  int &spike_idx[], double mult = CB_SPIKE_ATR_MULTIPLIER)
{
   int n = ArraySize(op);
   ArrayResize(spike_idx, 0);
   if(n < 4) return 0;

   double thr = CB_SpikeThreshold(op, cl, mult);
   if(thr <= 0.0) return 0;

   for(int i = 0; i < n; i++)
   {
      double w = CB_ExtremeWick(i, is_crash, op, hi, lo, cl);
      if(w > thr)
      {
         int sz = ArraySize(spike_idx);
         ArrayResize(spike_idx, sz + 1);
         spike_idx[sz] = i;
      }
   }
   return ArraySize(spike_idx);
}

//------------------------------------------------------------------//
// RSI simple (período corto, p.ej. 7) sobre array de cierres        //
//------------------------------------------------------------------//
double CB_RSI(const double &closes[], int period)
{
   int n = ArraySize(closes);
   if(n < period + 1) return 50.0;

   double gain = 0.0, loss = 0.0;
   int start = n - period;
   for(int i = start; i < n; i++)
   {
      double diff = closes[i] - closes[i - 1];
      if(diff > 0) gain += diff;
      else         loss -= diff;
   }
   if(loss == 0.0) return 100.0;
   double rs = gain / loss;
   return 100.0 - (100.0 / (1.0 + rs));
}

//------------------------------------------------------------------//
// Estructura con métricas de la "Señal Final" (réplica de signal_final.py)
//------------------------------------------------------------------//
struct CB_SignalSummary
{
   string action;       // BUY / SELL / WAIT / AVOID / EXIT
   double score;        // 0-100
   string regime;       // SPIKE / RECUPERACIÓN / CORRECCIÓN / DRIFT / TENSIÓN
   double cycle_pct;    // 0-100
   double risk;         // 0-100
   double confidence;   // 0-100
   double rsi;          // 0-100
   int    bars_since;   // velas desde el último spike (999 si ninguno)
   string reason;       // explicación textual
};

//------------------------------------------------------------------//
// Régimen rápido (mismo árbol que _quick_regime de Python)           //
//------------------------------------------------------------------//
string CB_QuickRegime(bool is_crash, int last_idx, int bars_since,
                      const double &op[], const double &cl[])
{
   int n = ArraySize(op);
   if(last_idx >= 0 && bars_since <= 2) return "SPIKE";
   if(last_idx >= 0 && bars_since <= 40) return is_crash ? "RECUPERACION" : "CORRECCION";

   int win = MathMin(10, n);
   if(win < 3) return "DRIFT";
   int dir_count = 0;
   double bodies_sum_first = 0.0, bodies_sum_last = 0.0, bodies_sum_all = 0.0;
   int    nf = 0, nl = 0;
   for(int i = n - win; i < n; i++)
   {
      bool dir = is_crash ? (cl[i] > op[i]) : (cl[i] < op[i]);
      if(dir) dir_count++;
      double b = MathAbs(cl[i] - op[i]);
      bodies_sum_all += b;
      if(i < n - win + 3) { bodies_sum_first += b; nf++; }
      if(i >= n - 3)      { bodies_sum_last  += b; nl++; }
   }
   double dir_pct = (double)dir_count / win * 100.0;
   double avg_body = bodies_sum_all / win;
   double body_trend = (nl > 0 ? bodies_sum_last / nl : 0) - (nf > 0 ? bodies_sum_first / nf : 0);
   double tension_extra = (avg_body > 0) ? MathMin(body_trend / avg_body * 50.0, 40.0) : 0.0;
   double tension = dir_pct * 0.6 + tension_extra;
   return (tension >= 60.0) ? "TENSION" : "DRIFT";
}

//------------------------------------------------------------------//
// Riesgo rápido (réplica de _quick_risk)                             //
//------------------------------------------------------------------//
double CB_QuickRisk(bool is_crash, int last_idx,
                    const double &op[], const double &hi[], const double &lo[], const double &cl[])
{
   int n = ArraySize(op);
   int spikes[];
   int nsp = CB_FindSpikes(is_crash, op, hi, lo, cl, spikes);
   if(nsp < 2) return 30.0;

   double sum_iv = 0.0;
   for(int i = 0; i < nsp - 1; i++) sum_iv += (spikes[i + 1] - spikes[i]);
   double avg_iv = sum_iv / (nsp - 1);

   double bars_since = (last_idx >= 0) ? (double)(n - 1 - last_idx) : avg_iv;
   double overdue = (avg_iv > 0) ? MathMin(bars_since / avg_iv * 100.0, 100.0) : 50.0;

   int win = MathMin(10, n);
   int dir_count = 0;
   for(int i = n - win; i < n; i++)
   {
      bool dir = is_crash ? (cl[i] > op[i]) : (cl[i] < op[i]);
      if(dir) dir_count++;
   }
   double dir_pct = (double)dir_count / win * 100.0;
   return MathRound((overdue * 0.5 + dir_pct * 0.5) * 10.0) / 10.0;
}

//------------------------------------------------------------------//
// Ciclo % rápido (réplica de _quick_cycle, clampeado [0,100])        //
//------------------------------------------------------------------//
double CB_QuickCycle(bool is_crash, int last_idx,
                     const double &op[], const double &hi[], const double &lo[], const double &cl[])
{
   int n = ArraySize(op);
   if(last_idx < 0) return 50.0;

   int pre_lo = MathMax(0, last_idx - 20);
   double current = cl[n - 1];
   double raw = 50.0;

   if(is_crash)
   {
      double low_v = lo[last_idx];
      double high_v = op[last_idx];
      for(int i = pre_lo; i < last_idx; i++) if(hi[i] > high_v) high_v = hi[i];
      if(MathAbs(high_v - low_v) > 1e-12)
         raw = (current - low_v) / (high_v - low_v) * 100.0;
   }
   else
   {
      double high_v = hi[last_idx];
      double low_v = op[last_idx];
      for(int i = pre_lo; i < last_idx; i++) if(lo[i] < low_v) low_v = lo[i];
      if(MathAbs(high_v - low_v) > 1e-12)
         raw = (high_v - current) / (high_v - low_v) * 100.0;
   }
   if(raw < 0.0)   raw = 0.0;
   if(raw > 100.0) raw = 100.0;
   return raw;
}

//------------------------------------------------------------------//
// Confianza rápida (réplica de _quick_confidence)                    //
//------------------------------------------------------------------//
double CB_QuickConfidence(bool is_crash,
                          const double &op[], const double &hi[], const double &lo[], const double &cl[])
{
   int spikes[];
   int n = CB_FindSpikes(is_crash, op, hi, lo, cl, spikes);
   double v = (double)n / 15.0 * 100.0;
   if(v > 100.0) v = 100.0;
   return v;
}

//------------------------------------------------------------------//
// SEÑAL FINAL — equivalente a CrashSignalFinal/BoomSignalFinal       //
//------------------------------------------------------------------//
bool CB_ComputeSignal(const string symbol, ENUM_TIMEFRAMES tf, CB_SignalSummary &out)
{
   if(!CB_IsSynthetic(symbol)) return false;
   bool is_crash = CB_IsCrash(symbol);

   double op[], hi[], lo[], cl[];
   datetime tm[];
   if(!CB_LoadCandles(symbol, tf, CB_SIGNAL_WINDOW, op, hi, lo, cl, tm)) return false;
   int n = ArraySize(op);
   if(n < 50) return false;

   int spikes[];
   int nsp = CB_FindSpikes(is_crash, op, hi, lo, cl, spikes);
   int last_idx   = (nsp > 0) ? spikes[nsp - 1] : -1;
   int bars_since = (last_idx >= 0) ? (n - 1 - last_idx) : 999;

   string regime = CB_QuickRegime(is_crash, last_idx, bars_since, op, cl);
   double risk   = CB_QuickRisk  (is_crash, last_idx, op, hi, lo, cl);
   double cyc    = CB_QuickCycle (is_crash, last_idx, op, hi, lo, cl);
   double conf   = CB_QuickConfidence(is_crash, op, hi, lo, cl);

   double rsi_arr[];
   int rsi_len = MathMin(14, n);
   ArrayResize(rsi_arr, rsi_len);
   for(int i = 0; i < rsi_len; i++) rsi_arr[i] = cl[n - rsi_len + i];
   double rsi = CB_RSI(rsi_arr, 7);

   string action; double score; string reason;

   string entry_action = is_crash ? "BUY" : "SELL";

   if(regime == "SPIKE")
   {
      action = "EXIT"; score = 0.0;
      reason = StringFormat("%s detectado hace %d vela(s). SALIR.", is_crash ? "Crash" : "Boom", bars_since);
   }
   else if((regime == "RECUPERACION" || regime == "CORRECCION") && cyc < 30 && risk < 50)
   {
      action = entry_action;
      score = 100.0 - risk + conf * 0.3;
      reason = StringFormat("Régimen=%s · Ciclo=%.0f%% · Riesgo=%.0f. ZONA ÓPTIMA. RSI=%.0f Conf=%.0f%%.",
                            regime, cyc, risk, rsi, conf);
   }
   else if(regime == "DRIFT" && cyc < 50 && risk < 40)
   {
      action = entry_action;
      score = 80.0 - risk;
      reason = StringFormat("DRIFT estable · Ciclo=%.0f%% · Riesgo=%.0f. RSI=%.0f.", cyc, risk, rsi);
   }
   else if(regime == "DRIFT" && cyc >= 50 && cyc <= 75 && risk < 60)
   {
      action = "WAIT"; score = 50.0;
      reason = StringFormat("DRIFT zona media · Ciclo=%.0f%% · Riesgo=%.0f.", cyc, risk);
   }
   else if(regime == "TENSION" || cyc > 80 || risk > 65)
   {
      action = "AVOID"; score = risk;
      reason = StringFormat("Régimen=%s · Ciclo=%.0f%% · Riesgo=%.0f. Spike próximo.", regime, cyc, risk);
   }
   else
   {
      action = "WAIT"; score = 50.0;
      reason = StringFormat("Señal ambigua · %s · Ciclo=%.0f%% · Riesgo=%.0f.", regime, cyc, risk);
   }

   if(conf < 30.0 && action == entry_action)
   {
      action = "WAIT";
      reason += StringFormat(" [Rebajado a WAIT: confianza %.0f%%]", conf);
   }

   if(score < 0.0)   score = 0.0;
   if(score > 100.0) score = 100.0;

   out.action     = action;
   out.score      = MathRound(score * 10.0) / 10.0;
   out.regime     = regime;
   out.cycle_pct  = MathRound(cyc * 10.0) / 10.0;
   out.risk       = MathRound(risk * 10.0) / 10.0;
   out.confidence = MathRound(conf * 10.0) / 10.0;
   out.rsi        = MathRound(rsi * 10.0) / 10.0;
   out.bars_since = bars_since;
   out.reason     = reason;
   return true;
}

//------------------------------------------------------------------//
// Color asociado a una acción de señal                               //
//------------------------------------------------------------------//
color CB_ActionColor(const string action)
{
   if(action == "BUY")   return clrLime;
   if(action == "SELL")  return clrTomato;
   if(action == "WAIT")  return clrGold;
   if(action == "AVOID") return clrOrangeRed;
   if(action == "EXIT")  return clrMagenta;
   return clrLightGray;
}

#endif // CRASH_BOOM_CORE_MQH
//+------------------------------------------------------------------+
