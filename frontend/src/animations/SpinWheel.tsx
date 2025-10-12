import React from "react";
import "./SpinWheel.css";

import frameSrc from "../../res/wheelExterior2.png";
import innerSrc from "../../res/wheelInterior3.png";
import textSrc from "../../res/wheelText.png"

export type SpinWheelProps = {
  size?: number | string;
  // spinning?: boolean;
  speedSec?: number;
  timing?: React.CSSProperties["animationTimingFunction"];
  frameAlt?: string;
  innerAlt?: string;
  textAlt?:  string;
  className?: string;
};

export default function SpinWheel({
  size = 512,
  // spinning = true,
  speedSec = 6,
  timing = "linear",
  frameAlt = "Wheel frame",
  innerAlt = "Wheel inner",
  textAlt  = "Wheel text",
  className = "",
}: SpinWheelProps) {
  const dim = typeof size === "number" ? `${size}px` : size;

  return (
    <a href={"/wheeloffortune"} className="wof-wrapper">
    <div
      className={`wheel wheel--fixed ${className}`}
      style={
        {
          "--wheel-size": dim,
          "--wheel-duration": `${speedSec}s`,
          "--wheel-timing": timing,
        } as React.CSSProperties
      }
      role="group"
      aria-label="Spin wheel"
    >
      
      <div className="spin__boost">
      <img
        className="wheel__inner"
        src={innerSrc}
        alt={innerAlt}
        draggable={false}
      />
      </div>
      <img
        className="wheel__frame"
        src={frameSrc}
        alt={frameAlt}
        draggable={false}
      />

      <img
        className="wheel__text"
        src={textSrc}
        alt={textAlt}
        draggable={false}
      />
    </div>
    </a>
  );
}
