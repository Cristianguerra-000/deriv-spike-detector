//+------------------------------------------------------------------+
//|                                          CB_SpikeDetector.mq5    |
//|  Marca con flechas todos los spikes Crash/Boom detectados en el  |
//|  histórico visible. Réplica de algorithms/crash_boom/spike_detector.py
//+------------------------------------------------------------------+
#property copyright "Crash/Boom MT5 Toolkit"
#property version   "1.00"
#property indicator_chart_window
#property indicator_buffers 0
#property indicator_plots   0

#include <CrashBoomCore.mqh>

input int    InpLookback     = 2000;            // Velas hacia atrás a escanear
input double InpMultiplier   = CB_SPIKE_ATR_MULTIPLIER; // Umbral wick / cuerpo p75
input color  InpCrashColor   = clrRed;          // Color flecha CRASH (apunta arriba bajo la vela)
input color  InpBoomColor    = clrLime;         // Color flecha BOOM
input int    InpArrowSize    = 2;
input bool   InpDrawLabels   = true;            // Etiqueta con magnitud
input string InpPrefix       = "CB_SPK_";

//------------------------------------------------------------------//
int OnInit()
{
   if(!CB_IsSynthetic(_Symbol))
   {
      Print("CB_SpikeDetector: símbolo no es Crash ni Boom (", _Symbol, "). Indicador inactivo.");
      return(INIT_SUCCEEDED);
   }
   IndicatorSetString(INDICATOR_SHORTNAME, "CB_SpikeDetector");
   ScanAndDraw();
   return(INIT_SUCCEEDED);
}

//------------------------------------------------------------------//
int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[],
                const double &close[], const long &tick_volume[],
                const long &volume[], const int &spread[])
{
   static datetime last_bar_time = 0;
   if(rates_total == 0) return 0;
   datetime cur = time[rates_total - 1];
   if(cur != last_bar_time)
   {
      last_bar_time = cur;
      ScanAndDraw();
   }
   return rates_total;
}

//------------------------------------------------------------------//
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, InpPrefix);
}

//------------------------------------------------------------------//
void ScanAndDraw()
{
   if(!CB_IsSynthetic(_Symbol)) return;
   bool is_crash = CB_IsCrash(_Symbol);

   double op[], hi[], lo[], cl[]; datetime tm[];
   if(!CB_LoadCandles(_Symbol, _Period, InpLookback, op, hi, lo, cl, tm)) return;

   ObjectsDeleteAll(0, InpPrefix);

   int spikes[];
   int nsp = CB_FindSpikes(is_crash, op, hi, lo, cl, spikes, InpMultiplier);
   double thr = CB_SpikeThreshold(op, cl, InpMultiplier);

   for(int k = 0; k < nsp; k++)
   {
      int idx = spikes[k];
      string nm = InpPrefix + IntegerToString(tm[idx]);
      double w = CB_ExtremeWick(idx, is_crash, op, hi, lo, cl);
      double price_anchor = is_crash ? lo[idx] - (hi[idx] - lo[idx]) * 0.05
                                     : hi[idx] + (hi[idx] - lo[idx]) * 0.05;

      ENUM_OBJECT obj_type = is_crash ? OBJ_ARROW_UP : OBJ_ARROW_DOWN;
      if(ObjectCreate(0, nm, obj_type, 0, tm[idx], price_anchor))
      {
         ObjectSetInteger(0, nm, OBJPROP_COLOR,    is_crash ? InpCrashColor : InpBoomColor);
         ObjectSetInteger(0, nm, OBJPROP_WIDTH,    InpArrowSize);
         ObjectSetInteger(0, nm, OBJPROP_BACK,     false);
         ObjectSetInteger(0, nm, OBJPROP_HIDDEN,   true);
         ObjectSetInteger(0, nm, OBJPROP_SELECTABLE, false);
      }

      if(InpDrawLabels)
      {
         string lbl = nm + "_lbl";
         double mag = (thr > 0) ? w / thr : 0;
         if(ObjectCreate(0, lbl, OBJ_TEXT, 0, tm[idx], price_anchor))
         {
            ObjectSetString (0, lbl, OBJPROP_TEXT, StringFormat("%.1fx", mag));
            ObjectSetInteger(0, lbl, OBJPROP_COLOR, is_crash ? InpCrashColor : InpBoomColor);
            ObjectSetInteger(0, lbl, OBJPROP_FONTSIZE, 8);
            ObjectSetInteger(0, lbl, OBJPROP_ANCHOR, is_crash ? ANCHOR_UPPER : ANCHOR_LOWER);
            ObjectSetInteger(0, lbl, OBJPROP_HIDDEN, true);
         }
      }
   }
   Comment(StringFormat("CB_SpikeDetector · %s · %d spikes · umbral=%.5f", _Symbol, nsp, thr));
}
//+------------------------------------------------------------------+
