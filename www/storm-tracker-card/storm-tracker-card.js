/**
 * storm-tracker-card.js
 * Custom Lovelace card for Storm Tracker — sector-based lightning situational awareness.
 *
 * Usage:
 *   type: custom:storm-tracker-card
 *   entity_prefix: storm_tracker
 *   title: Storm Tracker          # optional
 *   rings: [50, 100, 150, 200]    # distance rings in configured units
 *   colors:
 *     approaching: "#cc2200"
 *     receding:    "#0066aa"
 *     stationary:  "#cc6600"
 *     clear:       "#1e2a1e"
 */

const SECTOR_KEYS  = ['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw'];
const SECTOR_LABELS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];

const DEFAULT_COLORS = {
  approaching: '#cc2200',   // dark red     — white text readable
  receding:    '#0066aa',   // steel blue   — white text readable, clearly "safe"
  stationary:  '#cc6600',   // dark amber   — white text readable
  clear:       '#1e2a1e',   // dark green   — white text readable
};

const DEFAULT_RINGS = [50, 100, 150, 200];

// SVG geometry constants
const VB     = 400;   // viewBox width and height
const CX     = 200;   // centre x
const CY     = 200;   // centre y
const MAX_R  = 152;   // radar circle radius (leaves room for outer labels)
const LBL_R  = MAX_R + 24;  // compass label radius
const DATA_R = MAX_R * 0.58; // data label radius (inside wedge)

/** Convert compass bearing (0=N, clockwise) to SVG radians (0=right, clockwise). */
function compassToSVG(deg) {
  return (deg - 90) * Math.PI / 180;
}

/** Escape a value for safe insertion into HTML/SVG text content or attributes. */
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Format a distance value for safe display. */
function fmtDist(val, unit) {
  if (val === null || val === undefined) return '—';
  return `${val}${escHtml(unit)}`;
}

/**
 * Return a legible text color (dark or light) for a given hex background.
 * Uses perceived luminance so the card stays readable regardless of what
 * color the user configures.
 *
 * Returns '#111111' for light backgrounds, 'rgba(255,255,255,0.95)' for dark.
 */
function textColorFor(hex) {
  // Strip leading # and handle shorthand (#rgb → #rrggbb)
  let h = hex.replace(/^#/, '');
  if (h.length === 3) {
    h = h.split('').map(c => c + c).join('');
  }
  if (h.length !== 6) return 'rgba(255,255,255,0.95)';
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  // W3C perceived luminance formula
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.5 ? '#111111' : 'rgba(255,255,255,0.95)';
}

/**
 * Return a slightly dimmed version of textColorFor for secondary labels
 * (e.g. distance line beneath strike count).
 */
function textColorForSecondary(hex) {
  const base = textColorFor(hex);
  return base === '#111111' ? 'rgba(0,0,0,0.6)' : 'rgba(255,255,255,0.65)';
}

// ---------------------------------------------------------------------------

class StormTrackerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = null;
    this._hass   = null;
  }

  // Called by HA card picker to generate a stub config
  static getStubConfig() {
    return {
      entity_prefix: 'storm_tracker',
      rings: DEFAULT_RINGS,
    };
  }

  // -------------------------------------------------------------------------
  // HA card lifecycle
  // -------------------------------------------------------------------------

  setConfig(config) {
    if (!config.entity_prefix) {
      throw new Error('storm-tracker-card: entity_prefix is required');
    }
    this._config = {
      title:         config.title         ?? 'Storm Tracker',
      entity_prefix: config.entity_prefix,
      rings:         config.rings         ?? DEFAULT_RINGS,
      colors:        { ...DEFAULT_COLORS, ...(config.colors ?? {}) },
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 5;
  }

  // -------------------------------------------------------------------------
  // State helpers
  // -------------------------------------------------------------------------

  _numState(entityId, fallback = 0) {
    const s = this._hass?.states[entityId]?.state;
    if (!s || s === 'unavailable' || s === 'unknown') return fallback;
    const v = parseFloat(s);
    return isNaN(v) ? fallback : v;
  }

  _strState(entityId, fallback = '') {
    const s = this._hass?.states[entityId]?.state;
    if (!s || s === 'unavailable' || s === 'unknown') return fallback;
    return s;
  }

  _attrVal(entityId, attr, fallback = '') {
    return this._hass?.states[entityId]?.attributes?.[attr] ?? fallback;
  }

  // -------------------------------------------------------------------------
  // Build per-sector data array
  // -------------------------------------------------------------------------

  _sectorData() {
    const p = this._config.entity_prefix;
    return SECTOR_KEYS.map((key, i) => {
      const countId   = `sensor.${p}_${key}_strike_count`;
      const closestId = `sensor.${p}_${key}_closest_distance`;
      const trendId   = `sensor.${p}_${key}_trend`;

      const count   = this._numState(countId, 0);
      const closest = this._hass?.states[closestId]?.state;
      const trend   = this._strState(trendId, 'clear');
      const unit    = this._attrVal(closestId, 'unit_of_measurement', '');

      const closestVal =
        closest && closest !== 'unavailable' && closest !== 'unknown'
          ? parseFloat(closest)
          : null;

      return {
        label:   SECTOR_LABELS[i],
        count:   count,
        closest: isNaN(closestVal) ? null : closestVal,
        trend:   trend,
        unit:    unit,
      };
    });
  }

  // -------------------------------------------------------------------------
  // SVG generation helpers
  // -------------------------------------------------------------------------

  _svgWedges(sectors) {
    return sectors.map((sec, i) => {
      const color  = escHtml(this._config.colors[sec.trend] ?? this._config.colors.clear);
      const a1     = compassToSVG(i * 45 - 22.5);
      const a2     = compassToSVG(i * 45 + 22.5);
      const x1     = CX + MAX_R * Math.cos(a1);
      const y1     = CY + MAX_R * Math.sin(a1);
      const x2     = CX + MAX_R * Math.cos(a2);
      const y2     = CY + MAX_R * Math.sin(a2);
      // large-arc-flag=0 (45° < 180°), sweep-flag=1 (clockwise)
      return `<path d="M${CX},${CY} L${x1.toFixed(2)},${y1.toFixed(2)} ` +
             `A${MAX_R},${MAX_R} 0 0,1 ${x2.toFixed(2)},${y2.toFixed(2)} Z" ` +
             `fill="${color}" stroke="#111" stroke-width="1.5" stroke-linejoin="round"/>`;
    }).join('\n');
  }

  _svgRings(rings) {
    const sorted  = [...rings].sort((a, b) => a - b);
    const maxRing = sorted[sorted.length - 1];
    return sorted.map((ring) => {
      const r  = (ring / maxRing) * MAX_R;
      // Ring label: just inside the top of the ring, nudged right of the N spoke
      const lx = CX + 6;
      const ly = CY - r + 11;
      return `<circle cx="${CX}" cy="${CY}" r="${r.toFixed(2)}" ` +
             `fill="none" stroke="rgba(255,255,255,0.18)" stroke-width="1" stroke-dasharray="5 4"/>\n` +
             `<text x="${lx}" y="${ly}" fill="rgba(255,255,255,0.45)" ` +
             `font-size="9" text-anchor="start" font-family="sans-serif">${ring}</text>`;
    }).join('\n');
  }

  _svgSpokes() {
    return Array.from({ length: 8 }, (_, i) => {
      const a  = compassToSVG(i * 45 - 22.5);
      const x2 = CX + MAX_R * Math.cos(a);
      const y2 = CY + MAX_R * Math.sin(a);
      return `<line x1="${CX}" y1="${CY}" x2="${x2.toFixed(2)}" y2="${y2.toFixed(2)}" ` +
             `stroke="rgba(255,255,255,0.18)" stroke-width="0.75"/>`;
    }).join('\n');
  }

  _svgLabels(sectors) {
    return sectors.map((sec, i) => {
      const ca = compassToSVG(i * 45);

      // Compass direction label
      const lx = CX + LBL_R * Math.cos(ca);
      const ly = CY + LBL_R * Math.sin(ca);
      const compassLabel =
        `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" ` +
        `text-anchor="middle" dominant-baseline="central" ` +
        `fill="var(--primary-text-color, #e0e0e0)" ` +
        `font-size="13" font-weight="700" font-family="sans-serif">${sec.label}</text>`;

      // Data labels inside wedge (only when strikes present)
      let dataLabel = '';
      if (sec.count > 0) {
        const dx = CX + DATA_R * Math.cos(ca);
        const dy = CY + DATA_R * Math.sin(ca);

        // Resolve wedge color to determine readable text color
        const bgColor   = this._config.colors[sec.trend] ?? this._config.colors.clear;
        const textPri   = escHtml(textColorFor(bgColor));
        const textSec   = escHtml(textColorForSecondary(bgColor));

        dataLabel =
          `<text x="${dx.toFixed(1)}" y="${(dy - 7).toFixed(1)}" ` +
          `text-anchor="middle" dominant-baseline="central" ` +
          `fill="${textPri}" ` +
          `font-size="11" font-weight="600" font-family="sans-serif">${sec.count}</text>\n` +
          `<text x="${dx.toFixed(1)}" y="${(dy + 8).toFixed(1)}" ` +
          `text-anchor="middle" dominant-baseline="central" ` +
          `fill="${textSec}" ` +
          `font-size="9" font-family="sans-serif">${fmtDist(sec.closest, sec.unit)}</text>`;
      }

      return compassLabel + '\n' + dataLabel;
    }).join('\n');
  }

  _svgLegend() {
    const entries = [
      { key: 'approaching', label: 'Approaching' },
      { key: 'stationary',  label: 'Stationary'  },
      { key: 'receding',    label: 'Receding'     },
      { key: 'clear',       label: 'Clear'        },
    ];
    const itemW = VB / entries.length;
    return entries.map((e, i) => {
      const x = i * itemW + itemW / 2;
      const color = escHtml(this._config.colors[e.key] ?? DEFAULT_COLORS[e.key]);
      return `<rect x="${x - 16}" y="4" width="12" height="12" rx="2" fill="${color}" stroke="#555" stroke-width="0.5"/>
              <text x="${x}" y="11" dominant-baseline="central" fill="var(--secondary-text-color,#aaa)" font-size="10" font-family="sans-serif">${e.label}</text>`;
    }).join('\n');
  }

  // -------------------------------------------------------------------------
  // Main render
  // -------------------------------------------------------------------------

  _render() {
    if (!this._config) return;

    // Loading state before first hass update
    if (!this._hass) {
      this.shadowRoot.innerHTML =
        `<ha-card><div style="padding:16px;color:var(--primary-text-color)">Loading…</div></ha-card>`;
      return;
    }

    const sectors   = this._sectorData();
    const wedges    = this._svgWedges(sectors);
    const rings     = this._svgRings(this._config.rings);
    const spokes    = this._svgSpokes();
    const outerRing = `<circle cx="${CX}" cy="${CY}" r="${MAX_R}" fill="none" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/>`;
    const centre    = `<circle cx="${CX}" cy="${CY}" r="5" fill="rgba(255,255,255,0.25)"/>`;
    const labels    = this._svgLabels(sectors);
    const legend    = this._svgLegend();

    // Legend SVG sits below the radar
    const legendH = 22;
    const totalH  = VB + legendH + 8;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        ha-card {
          padding: 12px 12px 16px;
          box-sizing: border-box;
        }
        .card-header {
          font-size: 1.05rem;
          font-weight: 600;
          padding: 0 4px 10px;
          color: var(--primary-text-color);
          letter-spacing: 0.02em;
        }
        .radar-wrap {
          position: relative;
          width: 100%;
        }
        svg {
          display: block;
          width: 100%;
          height: auto;
        }
      </style>
      <ha-card>
        <div class="card-header">${escHtml(this._config.title)}</div>
        <div class="radar-wrap">
          <svg viewBox="0 0 ${VB} ${totalH}" xmlns="http://www.w3.org/2000/svg">
            <!-- Radar -->
            <g>
              ${wedges}
              ${rings}
              ${spokes}
              ${outerRing}
              ${labels}
              ${centre}
            </g>
            <!-- Legend -->
            <g transform="translate(0, ${VB + 6})">
              ${legend}
            </g>
          </svg>
        </div>
      </ha-card>
    `;
  }
}

// Register the custom element
if (!customElements.get('storm-tracker-card')) {
  customElements.define('storm-tracker-card', StormTrackerCard);
  console.info(
    '%c STORM-TRACKER-CARD %c loaded ',
    'color:#fff;background:#1565c0;padding:2px 4px;border-radius:3px 0 0 3px;font-weight:bold',
    'color:#1565c0;background:#e3f2fd;padding:2px 4px;border-radius:0 3px 3px 0'
  );
}
