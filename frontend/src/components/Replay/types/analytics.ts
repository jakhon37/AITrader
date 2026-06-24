export interface AnalyticsTrade {
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  size: number;
  side: string;
  pnl: number;
  pnl_pct: number;
  commission?: number;
}

export interface AnalyticsSummary {
  wins: number;
  losses: number;
  avg_win: number;
  avg_loss: number;
  best_trade: number;
  worst_trade: number;
  gross_profit: number;
  gross_loss: number;
}

export interface SessionAnalytics {
  initial_capital: number;
  final_equity: number;
  net_profit: number;
  net_profit_pct: number;
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  average_rr: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  discipline_score: number;
  trades: AnalyticsTrade[];
  equity_curve: { time: string; equity: number }[];
  trade_pnls: { index: number; pnl: number; side: string }[];
  summary?: AnalyticsSummary;
  instrument?: string;
  open_positions?: number;
  session_status?: string;
  current_time?: string | null;
}