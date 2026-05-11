//+------------------------------------------------------------------+
//|                                           CB_DriftChannel.mq5    |
//|  Dibuja un canal de regresión lineal sobre el último drift       |
//|  (segmento entre el penúltimo spike y el último, o desde el      |
//|  último spike hasta la vela actual si no hay otro previo).       |
//+------------------------------------------------------------------+
#property copyright "Crash/Boom MT5 Toolkit"
#property version   "1.00"
#property indicator_chart_window

#include <CrashBoomCore.mqh>

input int    InpLookback   = 1500;
input double InpMultiplier = CB_SPIKE_ATR_MULTIPLIER;
input color  InpColor      = clrAqua;
input string InpPrefix     = "CB_DC_";

int OnInit()
{
   ScanAndDraw();
   return(INIT_SUCCEEDED);
}
int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[],
                const double &close[], const long &tv[],
                const long &v[], const int &sp[])
{
   static datetime lt = 0;
   if(rates_total == 0) return 0;
   datetime t = time[rates_total - 1];
   if(t != lt) { lt = t; ScanAndDraw(); }
   return rates_total;
}
void OnDeinit(const int r) { ObjectsDeleteAll(0, InpPrefix); }

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

   int seg_start, seg_end;
   if(nsp >= 2)      { seg_start = spikes[nsp - 2] + 1; seg_end = spikes[nsp - 1]; }
   else if(nsp == 1) { seg_start = spikes[0] + 1;       seg_end = n - 1; }
   else              { seg_start = MathMax(0, n - 100); seg_end = n - 1; }

   int len = seg_end - seg_start + 1;
   if(len < 8) { Comment("CB_DriftChannel: drift demasiado corto."); return; }

   // Regresión lineal sobre cierres del segmento
   double sx = 0, sy = 0, sxy = 0, sxx = 0, syy = 0;
   for(int i = 0; i < len; i++)
   {
      double x = i, y = cl[seg_start + i];
      sx += x; sy += y; sxy += x * y; sxx += x * x; syy += y * y;
   }
   double denom = (len * sxx - sx * sx);
   if(MathAbs(denom) < 1e-12) return;
   double slope = (len * sxy - sx * sy) / denom;
   double intercept = (sy - slope * sx) / len;

   // Desviación máxima desde la línea
   double max_up = 0, max_dn = 0;
   for(int i = 0; i < len; i++)
   {
      double pred = intercept + slope * i;
      double actual = cl[seg_start + i];
      double d = actual - pred;
      if(d > max_up) max_up = d;
      if(d < max_dn) max_dn = d;
   }

   double y_start_mid = intercept;
   double y_end_mid   = intercept + slope * (len - 1);
   datetime t_start = tm[seg_start];
   datetime t_end   = tm[seg_end];

   // Línea media
   if(ObjectCreate(0, InpPrefix + "mid", OBJ_TREND, 0, t_start, y_start_mid, t_end, y_end_mid))
   {
      ObjectSetInteger(0, InpPrefix + "mid", OBJPROP_COLOR, InpColor);
      ObjectSetInteger(0, InpPrefix + "mid", OBJPROP_WIDTH, 2);
      ObjectSetInteger(0, InpPrefix + "mid", OBJPROP_RAY_RIGHT, true);
      ObjectSetInteger(0, InpPrefix + "mid", OBJPROP_HIDDEN, true);
   }
   // Borde superior
   if(ObjectCreate(0, InpPrefix + "up", OBJ_TREND, 0, t_start, y_start_mid + max_up, t_end, y_end_mid + max_up))
   {
      ObjectSetInteger(0, InpPrefix + "up", OBJPROP_COLOR, InpColor);
      ObjectSetInteger(0, InpPrefix + "up", OBJPROP_STYLE, STYLE_DASH);
      ObjectSetInteger(0, InpPrefix + "up", OBJPROP_RAY_RIGHT, true);
      ObjectSetInteger(0, InpPrefix + "up", OBJPROP_HIDDEN, true);
   }
   // Borde inferior
   if(ObjectCreate(0, InpPrefix + "dn", OBJ_TREND, 0, t_start, y_start_mid + max_dn, t_end, y_end_mid + max_dn))
   {
      ObjectSetInteger(0, InpPrefix + "dn", OBJPROP_COLOR, InpColor);
      ObjectSetInteger(0, InpPrefix + "dn", OBJPROP_STYLE, STYLE_DASH);
      ObjectSetInteger(0, InpPrefix + "dn", OBJPROP_RAY_RIGHT, true);
      ObjectSetInteger(0, InpPrefix + "dn", OBJPROP_HIDDEN, true);
   }

   Comment(StringFormat("CB_DriftChannel · pendiente=%.6f · %d velas", slope, len));
}
//+------------------------------------------------------------------+
