export interface PositionSummary {
  instrument: string;
  side: string;
  size: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  open_since: string;
}

export interface PortfolioState {
  balance: number;
  equity: number;
  margin_used: number;
  free_margin: number;
  open_positions: PositionSummary[];
  realized_pnl_today: number;
  drawdown_pct: number;
}

export interface TradeSignal {
  signal_id: string;
  instrument: string;
  timestamp: string;
  direction: string;
  confidence: number;
  strength: string;
  suggested_side: string | null;
  suggested_entry: number | null;
  suggested_sl: number | null;
  suggested_tp: number | null;
  suggested_size: number | null;
  narrative: string | null;
}

export interface FundamentalSignal {
  signal_id: string;
  instrument: string;
  timestamp: string;
  direction: string;
  confidence: number;
  sentiment_score: number;
  event_type: string;
  source_headline: string;
}

export interface TimeframeBias {
  timeframe: string;
  direction: string;
  confidence: number;
  regime: string;
  indicators: Record<string, number>;
  support: number | null;
  resistance: number | null;
}

export interface TechnicalSignal {
  signal_id: string;
  instrument: string;
  timestamp: string;
  direction: string;
  confidence: number;
  regime: string;
  per_timeframe: TimeframeBias[];
}

export interface WsMessage {
  type: string;
  data: unknown;
}
