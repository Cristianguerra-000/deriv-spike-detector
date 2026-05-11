//+------------------------------------------------------------------+
//|                                           CB_SignalFinal.mq5     |
//|  Indicador-panel: muestra BUY/SELL/WAIT/AVOID/EXIT en el chart   |
//|  con regimen, ciclo, riesgo, confianza, RSI y velas-desde-spike. |
//|  Equivalente directo de algorithms/crash_boom/signal_final.py    |
//+------------------------------------------------------------------+
#property copyright "Crash/Boom MT5 Toolkit"
#property version   "1.00"
#property indicator_chart_window

#include <CrashBoomCore.mqh>

input int   InpCorner       = CORNER_RIGHT_UPPER;
input int   InpAnchorXOffset= 12;
input int   InpAnchorYOffset= 18;
input color InpBgColor      = C'25,28,38';
input color InpTextColor    = clrWhiteSmoke;
input color InpLabelColor   = clrSilver;
input int   InpFontSize     = 10;
input string InpFontName    = "Consolas";
input string InpPrefix      = "CB_SF_";

string g_lines[8];

int OnInit()
{
   IndicatorSetString(INDICATOR_SHORTNAME, "CB_SignalFinal");
   CreatePanel();
   Refresh();
   EventSetTimer(2);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   ObjectsDeleteAll(0, InpPrefix);
}

void OnTimer() { Refresh(); }

int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[],
                const double &close[], const long &tv[],
                const long &v[], const int &sp[])
{
   static datetime lt = 0;
   if(rates_total == 0) return 0;
   datetime t = time[rates_total - 1];
   if(t != lt) { lt = t; Refresh(); }
   return rates_total;
}

//------------------------------------------------------------------//
void CreatePanel()
{
   string bg = InpPrefix + "bg";
   ObjectCreate(0, bg, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, bg, OBJPROP_CORNER,    InpCorner);
   ObjectSetInteger(0, bg, OBJPROP_XDISTANCE, InpAnchorXOffset);
   ObjectSetInteger(0, bg, OBJPROP_YDISTANCE, InpAnchorYOffset);
   ObjectSetInteger(0, bg, OBJPROP_XSIZE,     280);
   ObjectSetInteger(0, bg, OBJPROP_YSIZE,     200);
   ObjectSetInteger(0, bg, OBJPROP_BGCOLOR,   InpBgColor);
   ObjectSetInteger(0, bg, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, bg, OBJPROP_COLOR,     clrDimGray);
   ObjectSetInteger(0, bg, OBJPROP_BACK,      false);
   ObjectSetInteger(0, bg, OBJPROP_HIDDEN,    true);
   ObjectSetInteger(0, bg, OBJPROP_SELECTABLE,false);

   for(int i = 0; i < 8; i++)
   {
      string nm = InpPrefix + "line" + IntegerToString(i);
      ObjectCreate(0, nm, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, nm, OBJPROP_CORNER,    InpCorner);
      ObjectSetInteger(0, nm, OBJPROP_XDISTANCE, InpAnchorXOffset + 14);
      ObjectSetInteger(0, nm, OBJPROP_YDISTANCE, InpAnchorYOffset + 12 + i * 22);
      ObjectSetString (0, nm, OBJPROP_FONT,      InpFontName);
      ObjectSetInteger(0, nm, OBJPROP_FONTSIZE,  InpFontSize);
      ObjectSetInteger(0, nm, OBJPROP_COLOR,     InpTextColor);
      ObjectSetInteger(0, nm, OBJPROP_HIDDEN,    true);
      ObjectSetInteger(0, nm, OBJPROP_SELECTABLE,false);
      if(InpCorner == CORNER_RIGHT_UPPER || InpCorner == CORNER_RIGHT_LOWER)
         ObjectSetInteger(0, nm, OBJPROP_ANCHOR, ANCHOR_RIGHT_UPPER);
   }
}

void SetLine(int idx, string txt, color clr)
{
   string nm = InpPrefix + "line" + IntegerToString(idx);
   ObjectSetString (0, nm, OBJPROP_TEXT,  txt);
   ObjectSetInteger(0, nm, OBJPROP_COLOR, clr);
}

//------------------------------------------------------------------//
void Refresh()
{
   if(!CB_IsSynthetic(_Symbol))
   {
      SetLine(0, "Símbolo no Crash/Boom",   clrTomato);
      SetLine(1, _Symbol,                   InpLabelColor);
      for(int i = 2; i < 8; i++) SetLine(i, "", InpTextColor);
      return;
   }

   CB_SignalSummary s;
   if(!CB_ComputeSignal(_Symbol, _Period, s))
   {
      SetLine(0, "Sin datos suficientes", clrGold);
      return;
   }

   color act_clr = CB_ActionColor(s.action);
   SetLine(0, StringFormat("%s · %s", _Symbol, EnumToString(_Period)), InpLabelColor);
   SetLine(1, StringFormat("ACCION : %-6s  %.0f/100", s.action, s.score), act_clr);
   SetLine(2, StringFormat("Regimen: %s", s.regime), InpTextColor);
   SetLine(3, StringFormat("Ciclo  : %5.1f %%", s.cycle_pct), InpTextColor);
   SetLine(4, StringFormat("Riesgo : %5.1f /100", s.risk), InpTextColor);
   SetLine(5, StringFormat("Confian: %5.1f %%", s.confidence), InpTextColor);
   SetLine(6, StringFormat("RSI(7) : %5.1f   bars: %d", s.rsi, s.bars_since), InpTextColor);
   string short_reason = StringSubstr(s.reason, 0, 40);
   SetLine(7, short_reason, clrLightSlateGray);
   ChartRedraw();
}
//+------------------------------------------------------------------+
