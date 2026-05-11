//+------------------------------------------------------------------+
//|                                       CB_AnalysisDashboard.mq5   |
//|  Expert Advisor de SOLO ANÁLISIS (no opera).                     |
//|  Muestra el panel de señal final + alertas en cada cambio de     |
//|  acción (BUY/SELL/WAIT/AVOID/EXIT).                              |
//+------------------------------------------------------------------+
#property copyright "Crash/Boom MT5 Toolkit"
#property version   "1.00"
#property strict

#include <CrashBoomCore.mqh>

input bool   InpAlertPopup     = true;
input bool   InpAlertSound     = true;
input string InpSoundFile      = "alert.wav";
input int    InpRefreshSec     = 3;

string g_last_action = "";

int OnInit()
{
   if(!CB_IsSynthetic(_Symbol))
   {
      Print("CB_AnalysisDashboard: símbolo no es Crash/Boom (", _Symbol, ").");
   }
   EventSetTimer(InpRefreshSec);
   Comment("CB_AnalysisDashboard activo (solo análisis, no opera).");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int r) { EventKillTimer(); Comment(""); }

void OnTimer()
{
   if(!CB_IsSynthetic(_Symbol)) return;

   CB_SignalSummary s;
   if(!CB_ComputeSignal(_Symbol, _Period, s)) return;

   if(s.action != g_last_action && g_last_action != "")
   {
      string msg = StringFormat("[%s %s] %s · %s · score %.0f · ciclo %.0f%% · riesgo %.0f",
                                _Symbol, EnumToString(_Period), s.action, s.regime,
                                s.score, s.cycle_pct, s.risk);
      Print(msg);
      if(InpAlertPopup) Alert(msg);
      if(InpAlertSound) PlaySound(InpSoundFile);
   }
   g_last_action = s.action;
}

void OnTick() { /* no opera */ }
//+------------------------------------------------------------------+
