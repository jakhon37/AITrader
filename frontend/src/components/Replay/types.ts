export interface PendingOrder {
  order_id: string;
  signal_id: string;
  instrument: string;
  side: 'buy' | 'sell';
  size_lots: number;
  entry_price: number;
  sl: number | null;
  tp: number | null;
  created_at: string;
}