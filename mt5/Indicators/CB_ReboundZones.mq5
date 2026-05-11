//+------------------------------------------------------------------+
//|                                           CB_ReboundZones.mq5    |
//|  Pinta zonas de rebote / rompimiento post-spike:                 |
//|   - Línea horizontal en el extremo del spike (low/high)          |
//|   - Rectángulo con la zona Fib 38.2%-61.8% del rebote            |
//|  Estos niveles son los patrones repetitivos que el precio        |
//|  tiende a respetar en spikes futuros.                            |
//+------------------------------------------------------------------+
#property copyright "Crash/Boom MT5 Toolkit"
#property version   "1.00"
#property indicator_chart_window

#include <CrashBoomCore.mqh>

input int    InpLookback        = 3000;     // Velas a analizar
input int    InpRecoveryWindow  = 30;       // Velas usadas para medir el rebote
input double InpMultiplier      = CB_SPIKE_ATR_MULTIPLIER;
input color  InpExtremeColor    = clrYellow;
input color  InpZoneColor       = clrDodgerBlue;
input int    InpZoneTransparency= 80;       // 0-255 (mayor = más transparente)
input int    InpMaxZones        = 30;       // máximo de zonas dibujadas (las más recientes)
input string InpPrefix          = "CB_RBZ_";

//------------------------------------------------------------------//
int OnInit()
{
   if(!CB_IsSynthetic(_Symbol))
   {
      Print("CB_ReboundZones: símbolo no es Crash/Boom.");
      return(INIT_SUCCEEDED);
   }
   IndicatorSetString(INDICATOR_SHORTNAME, "CB_ReboundZones");
   ScanAndDraw();
   return(INIT_SUCCEEDED);
}

int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[],
                const double &close[], const long &tv[],
                const long &v[], const int &sp[])
{
   static datetime last_bar = 0;
   if(rates_total == 0) return 0;
   datetime t = time[rates_total - 1];
   if(t != last_bar) { last_bar = t; ScanAndDraw(); }
   return rates_total;
}

void OnDeinit(const int reason) { ObjectsDeleteAll(0, InpPrefix); }

//------------------------------------------------------------------//
void ScanAndDraw()
{
   if(!CB_IsSynthetic(_Symbol)) return;
   bool is_crash = CB_IsCrash(_Symbol);

   double op[], hi[], lo[], cl[]; datetime tm[];
   if(!CB_LoadCandles(_Symbol, _Period, InpLookback, op, hi, lo, cl, tm)) return;
   int n = ArraySize(op);

   ObjectsDeleteAll(0, InpPrefix);

   int spikes[];
   int nsp = CB_FindSpikes(is_crash, op, hi, lo, cl, spikes, InpMultiplier);
   if(nsp == 0) { Comment("CB_ReboundZones: sin spikes en ", InpLookback, " velas."); return; }

   int start = MathMax(0, nsp - InpMaxZones);
   for(int k = start; k < nsp; k++)
   {
      int sidx = spikes[k];
      double extreme = is_crash ? lo[sidx] : hi[sidx];

      // Línea horizontal en el extremo del spike
      string ln = StringFormat("%sext_%d", InpPrefix, tm[sidx]);
      datetime t_end = tm[n - 1] + PeriodSeconds(_Period) * 50;
      if(ObjectCreate(0, ln, OBJ_TREND, 0, tm[sidx], extreme, t_end, extreme))
      {
         ObjectSetInteger(0, ln, OBJPROP_COLOR, InpExtremeColor);
         ObjectSetInteger(0, ln, OBJPROP_STYLE, STYLE_DOT);
         ObjectSetInteger(0, ln, OBJPROP_WIDTH, 1);
         ObjectSetInteger(0, ln, OBJPROP_RAY_RIGHT, false);
         ObjectSetInteger(0, ln, OBJPROP_HIDDEN, true);
         ObjectSetInteger(0, ln, OBJPROP_SELECTABLE, false);
      }

      // Calcular zona Fib del rebote
      int rec_end = MathMin(n - 1, sidx + InpRecoveryWindow);
      if(rec_end - sidx < 4) continue;
      double rec_extreme = is_crash ? hi[sidx + 1] : lo[sidx + 1];
      for(int i = sidx + 1; i <= rec_end; i++)
      {
         if(is_crash) { if(hi[i] > rec_extreme) rec_extreme = hi[i]; }
         else         { if(lo[i] < rec_extreme) rec_extreme = lo[i]; }
      }
      double range = MathAbs(rec_extreme - extreme);
      if(range <= 0) continue;

      double fib382 = is_crash ? rec_extreme - range * 0.382 : rec_extreme + range * 0.382;
      double fib618 = is_crash ? rec_extreme - range * 0.618 : rec_extreme + range * 0.618;
      double zone_top = MathMax(fib382, fib618);
      double zone_bot = MathMin(fib382, fib618);

      string rect = StringFormat("%szone_%d", InpPrefix, tm[sidx]);
      if(ObjectCreate(0, rect, OBJ_RECTANGLE, 0, tm[sidx + 1], zone_top, t_end, zone_bot))
      {
         ObjectSetInteger(0, rect, OBJPROP_COLOR, InpZoneColor);
         ObjectSetInteger(0, rect, OBJPROP_FILL, true);
         ObjectSetInteger(0, rect, OBJPROP_BACK, true);
         ObjectSetInteger(0, rect, OBJPROP_HIDDEN, true);
         ObjectSetInteger(0, rect, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(0, rect, OBJPROP_WIDTH, 1);
      }
   }
   Comment(StringFormat("CB_ReboundZones · %s · %d spikes · ventana rebote=%d",
                        _Symbol, nsp, InpRecoveryWindow));
}
//+------------------------------------------------------------------+
