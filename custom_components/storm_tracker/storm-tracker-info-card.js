/**
 * storm-tracker-info-card.js
 * Storm Tracker — sector activity list card.
 *
 * Usage:
 *   type: custom:storm-tracker-info-card
 *   entity_prefix: storm_tracker
 *   title: Storm Activity   # optional
 */

const SECTOR_KEYS = ['n','ne','e','se','s','sw','w','nw'];

const TREND_LABELS = {
  approaching: 'Approaching',
  receding:    'Receding',
  stationary:  'Stationary',
  clear:       'Clear',
};

const DEFAULT_COLORS = {
  approaching: '#cc2200',
  receding:    '#0066aa',
  stationary:  '#cc6600',
  clear:       '#1e2a1e',
};

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

class StormTrackerInfoCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = null;
    this._hass   = null;
  }

  static getStubConfig() {
    return { entity_prefix: 'storm_tracker' };
  }

  setConfig(config) {
    if (!config.entity_prefix) {
      throw new Error('storm-tracker-info-card: entity_prefix is required');
    }
    this._config = {
      title:         config.title  ?? 'Storm Activity',
      entity_prefix: config.entity_prefix,
      colors:        { ...DEFAULT_COLORS, ...(config.colors ?? {}) },
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 3; }

  // -----------------------------------------------------------------------

  _sectorRows() {
    if (!this._hass || !this._config) return [];
    const p = this._config.entity_prefix;

    const rows = SECTOR_KEYS.map(key => {
      const trendId = `sensor.${p}_${key}_trend`;
      const state   = this._hass.states[trendId];
      if (!state) return null;

      const trend    = state.state;
      if (trend === 'clear' || trend === 'unavailable' || trend === 'unknown') return null;

      const attrs    = state.attributes ?? {};
      const dist     = parseFloat(attrs.closest_distance);
      const unit     = attrs.distance_unit ?? 'mi';
      const dir      = attrs.direction     ?? key.toUpperCase();
      const city     = attrs.nearest_city  ?? null;
      const count    = attrs.strike_count  ?? 0;

      if (isNaN(dist)) return null;

      return { trend, dist, unit, dir, city, count };
    }).filter(Boolean);

    // Sort closest first
    rows.sort((a, b) => a.dist - b.dist);
    return rows;
  }

  _render() {
    if (!this._config) return;

    if (!this._hass) {
      this.shadowRoot.innerHTML =
        `<ha-card><div style="padding:16px;color:var(--primary-text-color)">Loading…</div></ha-card>`;
      return;
    }

    const rows   = this._sectorRows();
    const colors = this._config.colors;

    const rowsHtml = rows.length === 0
      ? `<div class="empty">No active storm sectors</div>`
      : rows.map(r => {
          const color    = escHtml(colors[r.trend] ?? DEFAULT_COLORS.clear);
          const label    = escHtml(TREND_LABELS[r.trend] ?? r.trend);
          const dir      = escHtml(r.dir);
          const dist     = escHtml(`${r.dist} ${r.unit}`);
          const city     = r.city ? escHtml(r.city) : null;
          const strikes  = r.count === 1 ? '1 strike' : `${r.count} strikes`;

          return `
            <div class="row">
              <div class="badge" style="background:${color}">${dir}</div>
              <div class="body">
                <div class="top">
                  <span class="dist">${dist}</span>
                  <span class="trend" style="color:${color}">${label}</span>
                </div>
                <div class="sub">
                  ${city ? `<span class="city">Near ${escHtml(city)}</span>` : ''}
                  <span class="count">${escHtml(strikes)}</span>
                </div>
              </div>
            </div>`;
        }).join('');

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 12px 16px 8px; box-sizing: border-box; }
        .card-header {
          font-size: 1.05rem;
          font-weight: 600;
          padding: 0 0 10px;
          color: var(--primary-text-color);
          letter-spacing: 0.02em;
        }
        .empty {
          padding: 12px 0;
          color: var(--secondary-text-color);
          font-size: 0.9rem;
        }
        .row {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 8px 0;
          border-top: 1px solid var(--divider-color, rgba(255,255,255,0.1));
        }
        .badge {
          width: 36px;
          height: 36px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 0.75rem;
          font-weight: 700;
          color: #fff;
          flex-shrink: 0;
          letter-spacing: 0.03em;
        }
        .body { flex: 1; min-width: 0; }
        .top {
          display: flex;
          align-items: baseline;
          gap: 8px;
          flex-wrap: wrap;
        }
        .dist {
          font-size: 1rem;
          font-weight: 600;
          color: var(--primary-text-color);
        }
        .trend {
          font-size: 0.8rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }
        .sub {
          display: flex;
          gap: 8px;
          margin-top: 2px;
          flex-wrap: wrap;
        }
        .city {
          font-size: 0.85rem;
          color: var(--secondary-text-color);
        }
        .count {
          font-size: 0.8rem;
          color: var(--disabled-text-color, rgba(255,255,255,0.4));
        }
      </style>
      <ha-card>
        <div class="card-header">${escHtml(this._config.title)}</div>
        ${rowsHtml}
      </ha-card>
    `;
  }
}

if (!customElements.get('storm-tracker-info-card')) {
  customElements.define('storm-tracker-info-card', StormTrackerInfoCard);
  console.info(
    '%c STORM-TRACKER-INFO-CARD %c loaded ',
    'color:#fff;background:#1565c0;padding:2px 4px;border-radius:3px 0 0 3px;font-weight:bold',
    'color:#1565c0;background:#e3f2fd;padding:2px 4px;border-radius:0 3px 3px 0'
  );
}

window.customCards = window.customCards || [];
window.customCards.push({
  type:        'storm-tracker-info-card',
  name:        'Storm Tracker Activity',
  description: 'Lists active storm sectors sorted by distance with nearest city',
  preview:     false,
});
