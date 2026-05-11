//+------------------------------------------------------------------+
//|                                      CB_CalibrateThreshold.mq5   |
//|  Recorre el histórico actual con multiplicadores de 2.5 a 6.0    |
//|  en pasos de 0.25, y para cada uno mide:                         |
//|     - número de spikes detectados                                |
//|     - intervalo promedio entre spikes                            |
//|     - desviación frente al intervalo declarado del símbolo       |
//|  Imprime una tabla en el log (Experts → Journal).                |
//+------------------------------------------------------------------+
#property copyright "Crash/Boom MT5 Toolkit"
#property version   "1.00"
#property script_show_inputs

#include <CrashBoomCore.mqh>

input int    InpBars       = 50000;   // velas a analizar
input double InpMultMin    = 2.5;
input double InpMultMax    = 6.0;
input double InpMultStep   = 0.25;

void OnStart()
{
   if(!CB_IsSynthetic(_Symbol))
   {
      Print("CB_CalibrateThreshold: símbolo no es Crash/Boom: ", _Symbol);
      return;
   }
   bool is_crash = CB_IsCrash(_Symbol);
   int declared = CB_DeclaredInterval(_Symbol);

   double op[], hi[], lo[], cl[]; datetime tm[];
   if(!CB_LoadCandles(_Symbol, _Period, InpBars, op, hi, lo, cl, tm))
   {
      Print("No se pudieron cargar ", InpBars, " velas.");
      return;
   }
   int n = ArraySize(op);
   PrintFormat("=== Calibración de SPIKE_ATR_MULTIPLIER · %s · %s · %d velas · intervalo declarado=%d ===",
               _Symbol, EnumToString(_Period), n, declared);
   PrintFormat("%-6s | %-7s | %-12s | %-10s", "MULT", "SPIKES", "INTERV.PROM", "DESV.DECL");

   double best_mult = 0; double best_dev = 1e18;
   for(double m = InpMultMin; m <= InpMultMax + 1e-9; m += InpMultStep)
   {
      int spikes[];
      int ns = CB_FindSpikes(is_crash, op, hi, lo, cl, spikes, m);
      double avg_iv = (ns > 0) ? (double)n / ns : 0.0;
      double dev = (declared > 0) ? MathAbs(avg_iv - declared) : 1e18;
      PrintFormat("%-6.2f | %-7d | %-12.1f | %-10.1f", m, ns, avg_iv, dev);
      if(ns >= 5 && dev < best_dev) { best_dev = dev; best_mult = m; }
   }
   PrintFormat("→ Recomendación: SPIKE_ATR_MULTIPLIER = %.2f  (desv=%.1f vs declarado %d)",
               best_mult, best_dev, declared);
}
//+------------------------------------------------------------------+
