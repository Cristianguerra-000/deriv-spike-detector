//+------------------------------------------------------------------+
//|                                          CB_ExportSpikes.mq5     |
//|  Exporta a CSV todos los spikes detectados con:                  |
//|     time, type, price, magnitude_x, bars_since_prev, hour, dow   |
//|  Archivo: MQL5/Files/spikes_<SYMBOL>_<TIMEFRAME>.csv             |
//+------------------------------------------------------------------+
#property copyright "Crash/Boom MT5 Toolkit"
#property version   "1.00"
#property script_show_inputs

#include <CrashBoomCore.mqh>

input int    InpBars       = 100000;
input double InpMultiplier = CB_SPIKE_ATR_MULTIPLIER;

void OnStart()
{
   if(!CB_IsSynthetic(_Symbol))
   {
      Print("CB_ExportSpikes: símbolo no es Crash/Boom.");
      return;
   }
   bool is_crash = CB_IsCrash(_Symbol);

   double op[], hi[], lo[], cl[]; datetime tm[];
   if(!CB_LoadCandles(_Symbol, _Period, InpBars, op, hi, lo, cl, tm))
   {
      Print("Error cargando velas.");
      return;
   }
   int n = ArraySize(op);

   int spikes[];
   int ns = CB_FindSpikes(is_crash, op, hi, lo, cl, spikes, InpMultiplier);
   double thr = CB_SpikeThreshold(op, cl, InpMultiplier);

   string fname = StringFormat("spikes_%s_%s.csv", _Symbol, EnumToString(_Period));
   int h = FileOpen(fname, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(h == INVALID_HANDLE)
   {
      Print("No se pudo abrir ", fname, " err=", GetLastError());
      return;
   }
   FileWrite(h, "time", "type", "price", "magnitude_x", "bars_since_prev", "hour", "day_of_week");

   int prev = -1;
   for(int k = 0; k < ns; k++)
   {
      int idx = spikes[k];
      double price = is_crash ? lo[idx] : hi[idx];
      double w = CB_ExtremeWick(idx, is_crash, op, hi, lo, cl);
      double mag = (thr > 0) ? w / thr : 0;
      int gap = (prev >= 0) ? (idx - prev) : 0;

      MqlDateTime dt; TimeToStruct(tm[idx], dt);
      FileWrite(h,
                TimeToString(tm[idx], TIME_DATE | TIME_SECONDS),
                is_crash ? "CRASH" : "BOOM",
                DoubleToString(price, _Digits),
                DoubleToString(mag, 2),
                IntegerToString(gap),
                IntegerToString(dt.hour),
                IntegerToString(dt.day_of_week));
      prev = idx;
   }
   FileClose(h);
   PrintFormat("CB_ExportSpikes · %s · %d spikes exportados → %s", _Symbol, ns, fname);
}
//+------------------------------------------------------------------+
