import { useEffect, useMemo, useState } from 'react';
import { Globe, ChevronDown, ChevronUp, Clock, Zap } from 'lucide-react';
import { getNews, getUpcomingCalendar } from '../../api/client';
import { useChartTimezone } from '../../hooks/useChartTimezone';
import { useSignalsStore } from '../../store/signals';
import type { FundamentalSignal, NewsArticle, UpcomingCalendarEvent } from '../../types';
import { formatCalendarEventTime } from '../../utils/chartTimezone';
import { plainTextFromLlm } from '../../utils/plainText';

interface NewsFeedProps {
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

const IMPACT_COLOR: Record<string, string> = {
  high: 'var(--neon-red)',
  medium: 'var(--neon-orange)',
  low: 'var(--text-muted)',
};

function impactBars(level: string) {
  const filled = level === 'high' ? 3 : level === 'medium' ? 2 : 1;
  return (
    <span style={{ display: 'inline-flex', gap: 2, alignItems: 'flex-end' }}>
      {[1, 2, 3].map((bar) => (
        <span
          key={bar}
          style={{
            width: 3,
            height: 4 + bar * 3,
            borderRadius: 1,
            background: bar <= filled ? IMPACT_COLOR[level] ?? 'var(--text-muted)' : 'rgba(255,255,255,0.12)',
          }}
        />
      ))}
    </span>
  );
}

function formatCountdown(minutes: number) {
  if (minutes <= 0) return 'now';
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function sentimentColor(score: number) {
  if (score >= 0.15) return 'var(--neon-green)';
  if (score <= -0.15) return 'var(--neon-red)';
  return 'var(--text-muted)';
}

function sentimentLabel(score: number, direction?: string) {
  if (direction === 'neutral' || (score > -0.15 && score < 0.15)) return 'WATCH';
  if (score >= 0.15) return 'BULLISH';
  return 'BEARISH';
}

function isUpcomingBriefing(sig: FundamentalSignal) {
  return sig.source_headline?.startsWith('Upcoming:');
}

function isDevBootstrap(sig: FundamentalSignal) {
  return sig.source_headline?.startsWith('Dev bootstrap:');
}

type LiveFeedItem =
  | { kind: 'article'; article: NewsArticle; signal?: FundamentalSignal }
  | { kind: 'signal'; signal: FundamentalSignal };

const NEWS_LOOKBACK_HOURS = 48;

function newsWindowIso() {
  const end = new Date();
  const start = new Date(end.getTime() - NEWS_LOOKBACK_HOURS * 60 * 60 * 1000);
  return { start: start.toISOString(), end: end.toISOString() };
}

export function NewsFeed({ isCollapsed, onToggleCollapse }: NewsFeedProps) {
  const fundamentalSignals = useSignalsStore((s) => s.fundamentalSignals);
  const { timezone, displayLabel } = useChartTimezone();
  const [upcoming, setUpcoming] = useState<UpcomingCalendarEvent[]>([]);
  const [newsArticles, setNewsArticles] = useState<NewsArticle[]>([]);

  useEffect(() => {
    let active = true;

    const load = () => {
      getUpcomingCalendar(48, 'low')
        .then((events) => {
          if (!active) return;
          const list = Array.isArray(events) ? events : [];
          setUpcoming(list.filter((e) => e.status === 'upcoming'));
        })
        .catch(() => {
          if (active) setUpcoming([]);
        });
    };

    load();
    const timer = window.setInterval(load, 60_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let active = true;

    const load = () => {
      const { start, end } = newsWindowIso();
      getNews(start, end)
        .then((articles) => {
          if (!active) return;
          setNewsArticles(Array.isArray(articles) ? articles : []);
        })
        .catch(() => {
          if (active) setNewsArticles([]);
        });
    };

    load();
    const timer = window.setInterval(load, 120_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const releasedSignals = useMemo(
    () =>
      fundamentalSignals.filter(
        (sig) => !isUpcomingBriefing(sig) && !isDevBootstrap(sig),
      ),
    [fundamentalSignals],
  );

  const liveFeedItems = useMemo((): LiveFeedItem[] => {
    const signalByHeadline = new Map(
      releasedSignals.map((sig) => [sig.source_headline, sig]),
    );
    const articleHeadlines = new Set(newsArticles.map((art) => art.headline));

    const fromArticles: LiveFeedItem[] = newsArticles.map((article) => ({
      kind: 'article',
      article,
      signal: signalByHeadline.get(article.headline),
    }));

    const orphanSignals: LiveFeedItem[] = releasedSignals
      .filter((sig) => !articleHeadlines.has(sig.source_headline))
      .map((signal) => ({ kind: 'signal', signal }));

    const itemTime = (item: LiveFeedItem) =>
      item.kind === 'article' ? item.article.published_at : item.signal.timestamp;

    return [...fromArticles, ...orphanSignals]
      .sort((a, b) => new Date(itemTime(b)).getTime() - new Date(itemTime(a)).getTime())
      .slice(0, 15);
  }, [newsArticles, releasedSignals]);

  const briefingByEvent = useMemo(() => {
    const map = new Map<string, FundamentalSignal>();
    for (const sig of fundamentalSignals) {
      if (!isUpcomingBriefing(sig)) continue;
      const key = sig.source_headline.replace('Upcoming: ', '').split(' in ')[0]?.trim();
      if (key && !map.has(key)) map.set(key, sig);
    }
    return map;
  }, [fundamentalSignals]);

  return (
    <div
      className={`glass-panel ${isCollapsed ? '' : 'panel-shell'}`}
      style={{ padding: 16, gap: isCollapsed ? 0 : 12 }}
    >
      <div
        className="panel-header"
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}
      >
        <h3
          style={{
            fontSize: 11,
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: 'var(--text-secondary)',
            margin: 0,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <Globe size={14} color="var(--neon-cyan)" /> News Sentinel
        </h3>
        {onToggleCollapse && (
          <button
            onClick={onToggleCollapse}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: 0,
              display: 'flex',
              alignItems: 'center',
            }}
          >
            {isCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </button>
        )}
      </div>

      {!isCollapsed && (
        <div className="panel-body panel-body-stack" style={{ gap: 12 }}>
          <section>
            <div
              style={{
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: '0.06em',
                color: 'var(--text-muted)',
                marginBottom: 8,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <Clock size={11} /> Scheduled ({upcoming.length})
            </div>
            {upcoming.length === 0 ? (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', paddingBottom: 4 }}>
                No upcoming events in the next 48h.
              </div>
            ) : (
              upcoming.slice(0, 8).map((evt) => {
                const briefing = briefingByEvent.get(evt.name);
                return (
                  <div
                    key={evt.event_id}
                    style={{
                      paddingBottom: 10,
                      marginBottom: 10,
                      borderBottom: '1px solid rgba(255,255,255,0.04)',
                      flexShrink: 0,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 12, fontWeight: 700, lineHeight: 1.3 }}>{evt.name}</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                        {impactBars(evt.impact)}
                        <span style={{ fontSize: 10, color: IMPACT_COLOR[evt.impact], fontWeight: 700 }}>
                          {evt.impact.toUpperCase()}
                        </span>
                      </span>
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        marginTop: 4,
                        fontSize: 10,
                        color: 'var(--text-secondary)',
                      }}
                    >
                      <span>
                        {formatCalendarEventTime(evt.timestamp, timezone)} {displayLabel} ·{' '}
                        {evt.instruments.join(', ') || '—'}
                      </span>
                      <span style={{ color: 'var(--neon-cyan)', fontWeight: 600 }}>
                        {formatCountdown(evt.minutes_until)}
                      </span>
                    </div>
                    {(evt.forecast != null || evt.previous != null) && (
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
                        Fcst {evt.forecast ?? '—'} · Prev {evt.previous ?? '—'}
                      </div>
                    )}
                    {briefing?.narrative && (
                      <p style={{ fontSize: 10, color: 'var(--text-secondary)', lineHeight: 1.45, margin: '6px 0 0' }}>
                        {plainTextFromLlm(briefing.narrative)}
                      </p>
                    )}
                  </div>
                );
              })
            )}
          </section>

          <section>
            <div
              style={{
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: '0.06em',
                color: 'var(--text-muted)',
                marginBottom: 8,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <Zap size={11} /> Live Feed ({liveFeedItems.length})
            </div>
            {liveFeedItems.length === 0 ? (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--text-muted)',
                  fontSize: 11,
                  minHeight: 32,
                  gap: 4,
                  textAlign: 'center',
                  lineHeight: 1.45,
                }}
              >
                <span>No headlines in the last {NEWS_LOOKBACK_HOURS}h.</span>
                <span style={{ fontSize: 10 }}>Ingest runs via Finnhub + RSS (~10m).</span>
              </div>
            ) : (
              liveFeedItems.map((item) => {
                if (item.kind === 'signal') {
                  const sig = item.signal;
                  return (
                    <div
                      key={sig.signal_id}
                      style={{ paddingBottom: 10, borderBottom: '1px solid rgba(255,255,255,0.04)', flexShrink: 0 }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 700 }}>{sig.instrument}</span>
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 700,
                            color: sentimentColor(sig.sentiment_score),
                          }}
                        >
                          {sentimentLabel(sig.sentiment_score, sig.direction)}
                        </span>
                      </div>
                      <p style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
                        {sig.source_headline}
                      </p>
                      {sig.narrative && (
                        <p style={{ fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.45, margin: '4px 0 0' }}>
                          {plainTextFromLlm(sig.narrative)}
                        </p>
                      )}
                    </div>
                  );
                }

                const { article, signal } = item;
                const instruments =
                  article.instruments.length > 0 ? article.instruments.join(', ') : 'general';
                const headline = article.url ? (
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}
                  >
                    {article.headline}
                  </a>
                ) : (
                  article.headline
                );

                return (
                  <div
                    key={article.article_id}
                    style={{ paddingBottom: 10, borderBottom: '1px solid rgba(255,255,255,0.04)', flexShrink: 0 }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, gap: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--neon-cyan)' }}>
                        {instruments}
                      </span>
                      {signal ? (
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 700,
                            color: sentimentColor(signal.sentiment_score),
                            flexShrink: 0,
                          }}
                        >
                          {sentimentLabel(signal.sentiment_score, signal.direction)}
                        </span>
                      ) : null}
                    </div>
                    <p style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
                      {headline}
                    </p>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        marginTop: 4,
                        fontSize: 10,
                        color: 'var(--text-muted)',
                        gap: 8,
                      }}
                    >
                      <span>{article.source}</span>
                      <span>
                        {formatCalendarEventTime(article.published_at, timezone)} {displayLabel}
                      </span>
                    </div>
                    {signal?.narrative && (
                      <p style={{ fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.45, margin: '4px 0 0' }}>
                        {plainTextFromLlm(signal.narrative)}
                      </p>
                    )}
                  </div>
                );
              })
            )}
          </section>
        </div>
      )}
    </div>
  );
}