// tomatoThrow.ts
import winImg from "../../res/win.png";
import loseImg from "../../res/lose.png";
import spinAgainImg from "../../res/spin_again.png";

export type ImageKey = "win" | "lose" | "spinAgain";

const IMAGES: Record<ImageKey, string> = {
  win: winImg,
  lose: loseImg,
  spinAgain: spinAgainImg,
};

/**
 * Displays an image, animates it in, holds, then fades it out.
 * If x/y are omitted, the image is centered on screen.
 */
export async function DisplaySpinResult(
  key: ImageKey,
  opts?: { x?: number; y?: number; sizePx?: number; holdMs?: number }
): Promise<void> {
  if (typeof window === "undefined" || typeof document === "undefined") return;

  const src = IMAGES[key];
  if (!src) return;

  const size = opts?.sizePx ?? 5000;
  const holdMs = opts?.holdMs ?? 5000;

  const img = document.createElement("img");
  img.src = src;
  img.alt = key;
  img.style.position = "fixed";
  img.style.left = "0";
  img.style.top = "0";
  // img.style.transform = "translate(-50%, -50%)";
  // img.style.position = "absolute";
  img.style.pointerEvents = "none";
  img.style.filter = "drop-shadow(0 8px 14px rgba(0,0,0,.25))";
  // img.style.transformOrigin = "50% 50%";
  img.style.width = `${size}px`;
  img.style.height = `${size}px`;

  // Position: either at (x,y) or centered
  // if (typeof opts?.x === "number" && typeof opts?.y === "number") {
  //   img.style.left = `${opts.x - size / 2}px`;
  //   img.style.top = `${opts.y - size / 2}px`;
  // } else {
  //   img.style.left = "50%";
  //   img.style.top = "50%";
  //   img.style.transform = "translate(-50%, -50%)";
  // }

  document.body.appendChild(img);

  try {
    await (img.decode?.() ?? Promise.resolve());
  } catch {
    // ignore decode errors
  }

  // Entry animation
  const throwAnim = img.animate(
    [
      { transform: `${img.style.transform} scale(0.6) rotate(-360deg)`, opacity: 0 },
      { transform: `${img.style.transform} scale(1) rotate(0deg)`, opacity: 1 },
    ],
    { duration: 2000, easing: "cubic-bezier(.22,1,.36,1)", fill: "forwards" }
  );
  try {
    await throwAnim.finished;
  } catch {
    img.remove();
    return;
  }

  // Hold, then fade
  await new Promise((r) => setTimeout(r, holdMs));

  const fadeAnim = img.animate(
    [
      { transform: `${img.style.transform} scale(1) rotate(0deg)`, opacity: 1 },
      { transform: `${img.style.transform} scale(0.9) rotate(6deg)`, opacity: 0 },
    ],
    { duration: 1000, easing: "ease", fill: "forwards" }
  );
  try {
    await fadeAnim.finished;
  } finally {
    img.remove();
  }
}
