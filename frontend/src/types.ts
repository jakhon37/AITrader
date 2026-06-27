export interface PositionSummary {
  instrument: string;
  side: string;
  size: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  open_since: string;
  leg_id?: string;
  sl?: number | null;
  tp?: number | null;
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
  fundamental_weight?: number;
  technical_weight?: number;
  suggested_side: string | null;
  suggested_entry: number | null;
  suggested_sl: number | null;
  suggested_tp: number | null;
  suggested_size: number | null;
  narrative: string | null;
  model_version?: string | null;
}

/** Persisted LONG/SHORT flip marker for chart overlay (no NEUTRAL). */
export interface ChartMarker {
  marker_id: string;
  instrument: string | { value?: string };
  direction: 'long' | 'short';
  bar_time: string;
  signal_id: string;
  confidence: number;
  created_at: string;
}

export interface NewsArticle {
  article_id: string;
  headline: string;
  url: string | null;
  source: string;
  published_at: string;
  instruments: string[];
  body_snippet: string | null;
  fetched_at: string;
}

export interface FundamentalSignal {
  signal_id: string;
  instrument: string;
  timestamp: string;
  direction: string;
  confidence: number;
  strength?: string;
  sentiment_score: number;
  event_type: string;
  source_headline: string;
  narrative?: string | null;
}

export interface UpcomingCalendarEvent {
  event_id: string;
  name: string;
  timestamp: string;
  impact: 'low' | 'medium' | 'high';
  instruments: string[];
  forecast: number | null;
  previous: number | null;
  actual: number | null;
  minutes_until: number;
  status: 'upcoming' | 'released';
  volatility_risk: 'low' | 'medium' | 'high';
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
