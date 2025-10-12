// frontend/src/components/RadialEgoGraph.tsx
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import ForceGraph2D from "react-force-graph-2d";
import type { ForceGraphMethods, NodeObject} from "react-force-graph-2d";
import { forceRadial, forceCollide, forceX, forceY } from "d3-force";
import { useThemeColors } from "./useThemeColors";

/* ---------------- Types from backend contract ---------------- */

type GraphNode = {
  id: string;                 // "event:123"
  type: "event" | "person" | "topic" | "venue" | "cohort";
  label: string;
  ring: number;               // 0 today, 1 next7d, 2 later, -1 NA
  topic?: string | null;
  starts_at?: string | null;
  score: number;              // PPR relevance
  social_count?: number;      // consented friends interested
  poster_url?: string | null; // optional poster
  event_id?: string | number; // convenience for navigation
};

type GraphEdge = { source: string; target: string; type: string; weight: number };
type Explanation = { reasons: string[] };
type GraphResponse = {
  nodes: GraphNode[];
  edges: GraphEdge[]; // not shown by default (clean view)
  scores: Record<string, number>;
  explanations: Record<string, Explanation>;
};

/* ---------------- Layout constants ---------------- */

// Continuous time bands; nodes get a specific radius within each band
const RING_BANDS = [
  { min: 130, max: 190, spanSec: 24 * 3600 },      // Today
  { min: 210, max: 290, spanSec: 7 * 24 * 3600 },  // Next 7 days
  { min: 310, max: 390, spanSec: 0 }               // Later (scaled to horizon)
];
const CENTER = { x: 0, y: 0 };

// ColorBrewer-like qualitative palette (colorblind-friendly)
const TOPIC_COLORS = [
  "#1b9e77", "#d95f02", "#7570b3", "#e7298a",
  "#66a61e", "#e6ab02", "#a6761d", "#666666"
];
// Dedicated, pleasant non-red color for uncategorized ("Other") events
const OTHER_TOPIC_COLOR = "#93c5fd"; // pastel blue (blue-300)

/* ---------------- Utilities ---------------- */

function hashStr(s: string) { let h = 0; for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0; return h; } // [web:13]
function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)); } // [web:13]
function topicColor(topic?: string | null) {
  if (!topic) return OTHER_TOPIC_COLOR;
  const t = String(topic).trim();
  if (t.length === 0) return OTHER_TOPIC_COLOR;
  if (t.toLowerCase() === "other") return OTHER_TOPIC_COLOR;
  const idx = Math.abs(hashStr(t)) % TOPIC_COLORS.length;
  return TOPIC_COLORS[idx];
} // [web:71]
function hexToRgb(hex: string) { const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex); if (!m) return null; return { r: parseInt(m[1],16), g: parseInt(m[2],16), b: parseInt(m[3],16) }; } // [web:71]
function rgbToHsl(r:number,g:number,b:number){ r/=255; g/=255; b/=255; const max=Math.max(r,g,b),min=Math.min(r,g,b); let h=0,s=0; const l=(max+min)/2; if(max!==min){const d=max-min; s=l>0.5?d/(2-max-min):d/(max+min); switch(max){case r:h=(g-b)/d+(g<b?6:0);break;case g:h=(b-r)/d+2;break;case b:h=(r-g)/d+4;break} h/=6;} return {h:h*360,s,l}; } // [web:71]
function hslToCss(h:number,s:number,l:number){const ss=clamp(s,0,1)*100; const ll=clamp(l,0,1)*100; return `hsl(${Math.round(h)}, ${Math.round(ss)}%, ${Math.round(ll)}%)`; } // [web:71]
function applySaturation(hex:string,sat:number){const rgb=hexToRgb(hex); if(!rgb) return {color:hex,alpha:1}; const hsl=rgbToHsl(rgb.r,rgb.g,rgb.b); const color=hslToCss(hsl.h,clamp(sat,0.4,1.0),hsl.l); return {color,alpha:1}; } // [web:71]

/* ---------------- Component ---------------- */

interface Props {
  userId: string | number;
  onEventClick?: (eventId: string | number) => void;
}

export default function RadialEgoGraph({ userId, onEventClick }: Props) {
  const fgRef = useRef<ForceGraphMethods | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [data, setData] = useState<{ nodes: GraphNode[]; links: GraphEdge[]; explanations: Record<string, Explanation> }>({ nodes: [], links: [], explanations: {} });
  const themeColors = useThemeColors(containerRef);
  const isDark = window.localStorage.getItem("vis-theme")

  // Fetch graph payload
  useEffect(() => {
    fetch(`/api/graph/recommendations?user_id=${userId}`)
      .then(res => res.json())
      .then((resp: GraphResponse) => {
        const enriched = resp.nodes.map(n => {
          let event_id: string | undefined = undefined;
          if (n.type === "event") {
            const idStr = String(n.id);
            event_id = idStr.startsWith("event:") ? idStr.slice(6) : idStr; // use full backend Event.id
          }
          return {
            ...n,
            event_id,
            poster_url: (n as any).poster_url ?? null,
          } as any;
        });
        setData({ nodes: enriched, links: resp.edges, explanations: resp.explanations });
      })
      .catch(console.error);
  }, [userId]); // [web:117]

  // Top 10 recommendations by PPR score
  const eventNodes = useMemo(() => {
    const evs = data.nodes.filter(n => n.type === "event");
    evs.sort((a, b) => b.score - a.score);
    return evs.slice(0, 10);
  }, [data.nodes]); // [web:96]

  // Continuous time → radius
  const horizonSec = useMemo(() => {
    const now = Date.now();
    const fut = eventNodes.map(n => Date.parse(n.starts_at || "")).filter(ts => !Number.isNaN(ts) && ts > now).map(ts => (ts - now) / 1000);
    return Math.max(24 * 3600, ...fut, 24 * 3600);
  }, [eventNodes]); // [web:101]

  function radiusForTime(n: GraphNode) {
    const now = Date.now();
    const ts = Date.parse(n.starts_at || "");
    if (Number.isNaN(ts)) return RING_BANDS[2].max;
    const dt = Math.max(0, (ts - now) / 1000);
    if (dt <= 24 * 3600) { const b = RING_BANDS[0]; const t = dt / b.spanSec; return b.min + t * (b.max - b.min); }
    if (dt <= 7 * 24 * 3600) { const b = RING_BANDS[1]; const t = (dt - 24 * 3600) / (b.spanSec - 24 * 3600); return b.min + t * (b.max - b.min); }
    const b = RING_BANDS[2]; const span = horizonSec; const t = span > 0 ? Math.min(1, dt / span) : 0.5; return b.min + t * (b.max - b.min);
  } // [web:101]

  // Angle: stable, no topic wedges—just a deterministic “golden-angle” style placement per id
  const angleForEvent = (n: GraphNode) => {
    const h = Math.abs(hashStr(n.id));           // stable seed
    const phi = 0.61803398875;                   // golden ratio fraction
    const a = ((h * phi) % 1) * Math.PI * 2;     // 0..2π
    return a;
  }; // [web:13]

  // Size scale (larger for fewer nodes)
  const nodeValScale = useMemo(() => {
    const scores = eventNodes.map(n => n.score);
    return (s: number) => 60*(0.4+(s-Math.min(...scores))/(Math.max(...scores)-Math.min(...scores)));
  }, [eventNodes]); // [web:13]

  // Forces: gentle radial + target point on circle + collision; no link rendering by default
  useEffect(() => {
    if (!fgRef.current) return;
    const fg = fgRef.current as any;
    const engine = fg.d3Force as (name: string, force?: any) => any;

    const tx = (n: any) => { if (n.type !== "event") return 0; const a = angleForEvent(n); const r = radiusForTime(n); return Math.cos(a) * r; };
    const ty = (n: any) => { if (n.type !== "event") return 0; const a = angleForEvent(n); const r = radiusForTime(n); return Math.sin(a) * r; };

    engine("radial", forceRadial((n: any) => radiusForTime(n), CENTER.x, CENTER.y).strength(0.22));
    engine("x", forceX(tx).strength(0.36));
    engine("y", forceY(ty).strength(0.36));
    engine("charge")?.strength(-90);
    engine("collide", forceCollide((n: any) => {
      const g = eventNodes.find(e => e.id === n.id);
      const r = g ? nodeValScale(g.score) : 10;
      return r + 8;
    }).strength(0.95).iterations(2));
  }, [eventNodes, nodeValScale, horizonSec]); // [web:112]

  // Click navigation
  const handleNodeClick = useCallback((node: NodeObject) => {
    const n = node as unknown as GraphNode;
    if (n.type === "event" && n.event_id) {
      if (onEventClick) onEventClick(n.event_id);
      else window.location.href = `/events/eventpage/${encodeURIComponent(String(n.event_id))}`;
    }
  }, [onEventClick]); // [web:117]

  // Rendering
  const tooltip = (node: NodeObject) => {
    const n = node as unknown as GraphNode;
    if (n.type !== "event") return n.label;
    const parts = [`${n.label}`, `Click to open details`];
    return parts.join("\n");
  }; // [web:13]

  const drawNode = useCallback((node: NodeObject, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const n = node as unknown as GraphNode;
    const size = nodeValScale(n.score);
    const baseColor = topicColor(n.topic);
    const sat = clamp((n.social_count || 0) / 5, 0.4, 1.0);
    const { color } = applySaturation(baseColor, sat);

    ctx.save();

    // main disk
    ctx.beginPath();
    ctx.arc((node as any).x || 0, (node as any).y || 0, size, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();

    // outline: thicker if poster exists, otherwise thin white
    const hasPoster = n.poster_url && n.poster_url.trim() !== "";
    ctx.lineWidth = hasPoster ? 3 : 1.5;
    ctx.strokeStyle = hasPoster ? (themeColors?.["--color-graph-node-poster-outline"] ?? "#1a1a1a") : (themeColors?.["--color-graph-node-outline"] ?? "#ffffff");
    ctx.stroke();

    // label
    if (n.type === "event") {
      ctx.fillStyle = themeColors?.["--color-graph-node-label"] ?? "#222";
      ctx.font = `${Math.max(11, 14 / globalScale)}px Inter, ui-sans-serif, system-ui`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(n.label, (node as any).x || 0, ((node as any).y || 0) + size + 6);
    }

    ctx.restore();
  }, [nodeValScale, themeColors]);

  // Minimal guides: only rings + labels (no angular dividers)
  const drawGuides = useCallback((ctx: CanvasRenderingContext2D, globalScale: number) => {
    ctx.save();
    const ringMids = [
      (RING_BANDS[0].min + RING_BANDS[0].max) / 2,
      (RING_BANDS[1].min + RING_BANDS[1].max) / 2,
      (RING_BANDS[2].min + RING_BANDS[2].max) / 2
    ];
    ctx.lineWidth = Math.max(1, 2 / globalScale);
    ctx.strokeStyle = isDark ? "#374151" : "#eceef2";
    ringMids.forEach(r => { ctx.beginPath(); ctx.arc(CENTER.x, CENTER.y, r, 0, 2 * Math.PI); ctx.stroke(); });

    // labels
    const labels = ["Today", "Next 7 days", "Later"];
    ctx.fillStyle = !isDark ? themeColors?.["--color-graph-label"] ?? "#80859a": "#80859a";
    ctx.font = `${Math.max(10, 12 / globalScale)}px Inter, ui-sans-serif`;
    labels.forEach((lab, i) => {
      const r = ringMids[i];
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(lab, CENTER.x + r + 10, CENTER.y);
    });
    ctx.restore();
  }, [themeColors]);

  // Legend data
  const topicList = useMemo(() => {
    const set = new Set(eventNodes.map(n => (n.topic || "Other").trim()));
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [eventNodes]); // [web:71]

  const moreCount = Math.max(0, topicList.length - 5); // show up to 5 topic chips [web:71]

  return (
    <div
      ref={containerRef}
      style={{ position: "relative", width: "100%", height: "100%", background: themeColors?.["--color-graph-bg"] ?? "transparent", transition: "background 0.3s" }}
    >
      {/* Only render graph when theme is resolved to avoid color flashing */}
      {themeColors && (
      <ForceGraph2D
        ref={fgRef as any}
        graphData={{ nodes: eventNodes as any, links: [] as any }} // no links for a clean rec view
        nodeVal={(n: any) => nodeValScale(n.score)}
        nodeCanvasObject={drawNode}
        nodeLabel={tooltip}
        onNodeClick={handleNodeClick}
        enableZoomPanInteraction={true}
        cooldownTime={1600}
        autoPauseRedraw={false}
        d3VelocityDecay={0.3}
        onRenderFramePre={drawGuides as any}
      />
      )}

      {/* Minimal, pretty legend (glass card) */}
      <div style={{
        position: "absolute", right: 16, top: 16, padding: 14,
        background: themeColors?.["--color-graph-legend-bg"], backdropFilter: "saturate(120%) blur(6px)",
        border: `1px solid ${themeColors?.["--color-graph-legend-border"]}`, borderRadius: 12, boxShadow: `0 4px 16px ${themeColors?.["--color-graph-legend-shadow"]}`,
        fontFamily: "Inter, ui-sans-serif", maxWidth: 320
      }}>
        <div style={{ fontSize: 14, color: themeColors?.["--color-graph-legend-header"], fontWeight: 700, marginBottom: 6 }}>
          Top 10 recommendations
        </div>
        <div style={{ fontSize: 12, color: themeColors?.["--color-graph-legend-body"], marginBottom: 10, lineHeight: 1.4 }}>
          Size = relevance, distance = how soon, color = topic, outline = poster. Click a node to open details.
        </div>

        {/* Encodings row */}
        <div style={{ display: "flex", gap: 12, marginBottom: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 14, height: 14, borderRadius: 8, background: "#6ee7b7", display: "inline-block" }} />
            <span style={{ fontSize: 12, color: themeColors?.["--color-graph-legend-body"] }}>Size → relevance</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 14, height: 14, borderRadius: 8, background: "#a5b4fc", display: "inline-block" }} />
            <span style={{ fontSize: 12, color: themeColors?.["--color-graph-legend-body"] }}>Distance → time</span>
          </div>
        </div>

        {/* Topic chips (up to 5) */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {topicList.slice(0, 5).map(t => (
            <span key={t} style={{
              display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 8px",
              borderRadius: 999, border: `1px solid ${themeColors?.["--color-graph-legend-chip-border"]}`, background: themeColors?.["--color-graph-legend-chip-bg"]
            }}>
              <span style={{ width: 10, height: 10, borderRadius: 999, background: topicColor(t), display: "inline-block" }} />
              <span style={{ fontSize: 12, color: themeColors?.["--color-graph-legend-body"], maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t}</span>
            </span>
          ))}
          {moreCount > 0 && (
            <span style={{
              display: "inline-flex", alignItems: "center", padding: "4px 10px", color: themeColors?.["--color-graph-legend-body"],
              borderRadius: 999, background: "#f3f4f6", fontSize: 12
            }}>
              +{moreCount} more
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
