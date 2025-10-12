import { useEffect, useRef, useState } from "react";
import { Wheel } from "react-custom-roulette-r19";
import "./WheelOfFortuneImpl.css";

// import { DisplaySpinResult } from "./displayWheelResult__";


import outlineSrc from "../../res/wofOuterRing.png";
import buttonSrc from "../../res/spinButton.png";


// import winImg from "../../res/win.png";
// import loseImg from "../../res/lose.png";
// import spinAgainImg from "../../res/spin_again.png";

// Fixed order: the wheel renders slices in THIS order clockwise.
const data = [
  { option: "LOSE",       style: { backgroundColor: "#f33739", textColor: "#111827" } }, // red
  { option: "LOSE",       style: { backgroundColor: "#27a664", textColor: "#111827" } }, // green
  { option: "SPIN AGAIN", style: { backgroundColor: "#C49DFF", textColor: "#111827" } }, // white
  { option: "LOSE",       style: { backgroundColor: "#ffc635", textColor: "#111827" } }, // white
  { option: "WIN",        style: { backgroundColor: "#EC4899", textColor: "#111827" } }, // gold
  { option: "LOSE",       style: { backgroundColor: "#0e89c1", textColor: "#111827" } }, // blue
  { option: "LOSE",       style: { backgroundColor: "#f33739", textColor: "#111827" } }, // amber
  { option: "SPIN AGAIN", style: { backgroundColor: "#27a664", textColor: "#111827" } }, // purple
  { option: "LOSE",       style: { backgroundColor: "#C49DFF", textColor: "#111827" } }, // white
  { option: "LOSE",       style: { backgroundColor: "#ffc635", textColor: "#111827" } }, // white
  { option: "SPIN AGAIN", style: { backgroundColor: "#0e89c1", textColor: "#111827" } }, // white
];


// const resultImages = {
//   "WIN": winImg,
//   "LOSE": loseImg,
//   "SPIN AGAIN": spinAgainImg,
// } as const;

// type ResultKey = keyof typeof resultImages;


// Super minimal: one button to spin to a random index (0..data.length-1)
export default function WheelOfFortune() {
  const [mustSpin, setMustSpin]   = useState(false);
  const [prizeNumber, setPrizeNumber] = useState(0);
  const [result, setResult] = useState<string | null>(null);

  const [showResultBanner, setShowResultBanner] = useState(false);

  // NEW: track previous result to detect changes
  const prevResultRef = useRef<string | null>(null);

  useEffect(() => {
    if (result !== null && result !== prevResultRef.current) {
      setShowResultBanner(true);

      // auto-hide after 1.5s (tweak as you like)
      const t = setTimeout(() => setShowResultBanner(false), 5000);
      return () => clearTimeout(t);
    }
    // update previous for next run
    prevResultRef.current = result;
  }, [result]);

  const spin = () => {
    const idx = Math.floor(Math.random() * data.length);
    setPrizeNumber(idx);
    setMustSpin(true);
    setResult(null);
  };

  return (
   
      <div className="roulette__card">
        <div className="wheel__stack">
          <div className="wheel__box">
            <Wheel
              mustStartSpinning={mustSpin}
              prizeNumber={prizeNumber}
              data={data}
              // Gold rim + separators
              outerBorderColor="#facc15"
              outerBorderWidth={0}
              radiusLineColor="#111827"
              radiusLineWidth={2}
              // Spin feel
              spinDuration={0.9}           // seconds
              onStopSpinning={() => {
                setMustSpin(false);
                setResult(data[prizeNumber].option);
              }}
            />
          </div>
          <img
            className="wof__outer"
            src={outlineSrc}/>
        </div>

        <div className="button">
          <img
            className="button__sprite"
            src={buttonSrc}
            alt="Spin"
            onClick={() => { if (!mustSpin) spin(); 
            }}
            />
            <div className="button__txt">Spin!</div>
        </div>

        {showResultBanner && (
        <div className="result__image">
          {result}
        </div>
      )}

          
        {/* <div className="readout">
          {result ? `Result: ${result}` : "\u00A0"}
        </div> */}
      </div>
  );
}
