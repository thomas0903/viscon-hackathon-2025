// tomatoThrow.ts (WAAPI + precise landing)
type Options = {
  imageUrl: string;
  size?: number;
  throwDurationMs?: number;
  holdMs?: number;
  fadeOutMs?: number;
  cursorOffset?: { x: number; y: number };  // where the throw starts (relative to landing)
  landingOffset?: { x: number; y: number }; // final nudge in px
  anchor?: { x: number; y: number };        // 0..1 hotspot in the image box
};

const DEFAULTS: Required<Omit<Options, "imageUrl">> = {
  size: 400,
  throwDurationMs: 6000,
  holdMs: 600,
  fadeOutMs: 280,
  cursorOffset: { x: -180, y: -180},
  landingOffset: { x: 0, y: 0 },
  anchor: { x: 0.5, y: 0.6 },
};

export function armNextTomatoThrow(opts: Options) {
  const o = { ...DEFAULTS, ...opts };

  const prevCursor = document.body.style.cursor;
  document.body.style.cursor = "crosshair";

  const onClick = async (e: MouseEvent) => {
    window.removeEventListener("click", onClick, true);
    document.body.style.cursor = prevCursor;

    const prefersReduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;

    // --- Create fresh-playing GIF URL (optional; remove if you don't need restart) ---
    let tempUrl: string | null = null;
    const src = opts.imageUrl;
    // quick restart fallback:
    const freshSrc = `${src}${src.includes("?") ? "&" : "?"}t=${Date.now()}`;

    // --- Build element ---
    const img = document.createElement("img");
    img.src = freshSrc; // or use the blob/objectURL approach from earlier
    img.alt = "tomato";
    img.style.position = "absolute";       // 👉 absolute to use page coords
    img.style.pointerEvents = "none";
    img.style.filter = "drop-shadow(0 8px 14px rgba(0,0,0,.25))";
    img.style.transformOrigin = "50% 50%";
    img.style.width = `${o.size}px`;
    img.style.height = `${o.size}px`;

    // Compute landing position in page coordinates
    const left = e.pageX - o.size * o.anchor.x + o.landingOffset.x;
    const top  = e.pageY - o.size * o.anchor.y + o.landingOffset.y;

    img.style.left = `${left}px`;
    img.style.top  = `${top}px`;

    document.body.appendChild(img);

    try { await (img.decode?.() ?? Promise.resolve()); } catch {}

    if (prefersReduced) {
      setTimeout(() => img.remove(), o.holdMs);
      return;
    }

    // 1) Throw to landing (transform animates from offset -> 0)
    const throwAnim = img.animate(
      [
        {
          transform: `translate(${o.cursorOffset.x}px, ${o.cursorOffset.y}px) scale(0.6) rotate(-25deg)`,
          opacity: 1,
        },
        {
          transform: "translate(0, 0) scale(1) rotate(0deg)",
          opacity: 1,
        },
      ],
      { duration: o.throwDurationMs, easing: "cubic-bezier(.22,1,.36,1)", fill: "forwards" }
    );
    try { await throwAnim.finished; } catch { img.remove(); return; }

    // 2) Hold
    await new Promise(r => setTimeout(r, o.holdMs));

    // 3) Fade out
    const fadeAnim = img.animate(
      [
        { transform: "translate(0, 0) scale(1) rotate(0deg)", opacity: 1 },
        { transform: "translate(10px, 40px) scale(0.9) rotate(6deg)", opacity: 0 },
      ],
      { duration: o.fadeOutMs, easing: "ease", fill: "forwards" }
    );
    try { await fadeAnim.finished; } finally { img.remove(); if (tempUrl) URL.revokeObjectURL(tempUrl); }
  };

  // capture so it beats other handlers
  window.addEventListener("click", onClick, true);
}
