import React, { useEffect, useId, useMemo, useRef } from "react";
import {
  createCanopyRoutes,
  drawCanopy,
  processingPositions,
} from "./canopy.mjs";
import "./optical.css";

const SIGNALS = ["#8b79b8", "#4fa9ab", "#c99b60"];
const PACKETS = ["7A", "C2", "01"];

export function Processor({ className = "", ...props }) {
  const id = useId().replaceAll(":", "");
  const pins = Array.from({ length: 13 }, (_, n) => 53 + n * 11);
  return (
    <svg
      className={`optical-crystal processor-core ${className}`}
      viewBox="0 0 240 240"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <defs>
        <linearGradient id={`${id}-case`} x2=".8" y2="1">
          <stop stopColor="#273139" />
          <stop offset=".35" stopColor="#151d22" />
          <stop offset="1" stopColor="#080d11" />
        </linearGradient>
        <linearGradient id={`${id}-die`} x2="1" y2="1">
          <stop stopColor="#26343b" />
          <stop offset=".48" stopColor="#182329" />
          <stop offset="1" stopColor="#0b1217" />
        </linearGradient>
        <linearGradient id={`${id}-pins`} x2="1" y2="1">
          <stop stopColor="#b7945d" />
          <stop offset=".4" stopColor="#725b39" />
          <stop offset=".65" stopColor="#d1b77b" />
          <stop offset="1" stopColor="#56462f" />
        </linearGradient>
        <clipPath id={`${id}-channel`}>
          <path d="M155 78H106L82 128H128L116 143H81L69 163H126L152 114H106L118 98H144Z" />
        </clipPath>
      </defs>
      <g fill={`url(#${id}-pins)`}>
        {pins.map((p) => (
          <g key={p}>
            <rect x={p} y="14" width="3" height="13" />
            <rect x={p} y="213" width="3" height="13" />
            <rect x="14" y={p} width="13" height="3" />
            <rect x="213" y={p} width="13" height="3" />
          </g>
        ))}
      </g>
      <path
        d="M41 24H199L216 41V199L199 216H41L24 199V41Z"
        fill="#0a1014"
        stroke="#56616a"
        strokeWidth="1"
      />
      <path
        d="M43 29H197L211 43V197L197 211H43L29 197V43Z"
        fill={`url(#${id}-case)`}
        stroke="#303c43"
        strokeWidth="1"
      />
      <path
        d="M43 31H196L208 43M31 44V193"
        fill="none"
        stroke="#87939a"
        strokeOpacity=".3"
      />
      <g fill="none" stroke="#66747e" strokeOpacity=".2" strokeWidth=".7">
        <path d="M50 50H77L94 67M46 62H67L81 76M164 47V65L179 80H196M192 163H179L160 182V197M47 173H62L82 193" />
        <path d="M45 91V111M195 95V124M97 196H120" />
      </g>
      <path d="M120 47L198 125L120 203L42 125Z" fill="#050a0e" />
      <path
        d="M120 42L198 120L120 198L42 120Z"
        fill={`url(#${id}-die)`}
        stroke="#53616c"
        strokeWidth=".7"
      />
      <path d="M120 42L42 120L49 120L120 49Z" fill="#3a464f" fillOpacity=".5" />
      <path
        d="M198 120L120 198L120 190L190 120Z"
        fill="#050a0f"
        fillOpacity=".8"
      />
      <g transform="translate(120 120) scale(.86) skewX(-10) translate(-120 -120)">
        <path
          className="processor-stamp"
          d="M155 78H106L82 128H128L116 143H81L69 163H126L152 114H106L118 98H144Z"
          fill="#050a0e"
          stroke="#53616b"
          strokeWidth=".8"
        />
        <path
          d="M106 80H151M83 124H126M81 165H126"
          stroke="#65727b"
          strokeOpacity=".2"
          fill="none"
        />
        <g clipPath={`url(#${id}-channel)`}>
          <path
            className="processor-highlight"
            d="M140 88H114L100 120H140L121 153H84"
            fill="none"
            stroke="#a9c8ce"
            strokeWidth="1.1"
            strokeDasharray="14 220"
            opacity=".22"
          />
          {[0, 1, 2].map((packet) => (
            <g
              className="processor-packet"
              key={packet}
              style={{
                offsetPath: "path('M140 88H114L100 120H140L121 153H84')",
                offsetDistance: `${(packet * 100) / 3}%`,
                offsetAnchor: "0 0",
                offsetRotate: "0deg",
              }}
            >
              <text
                fill={SIGNALS[packet]}
                textAnchor="middle"
                dominantBaseline="middle"
              >
                {PACKETS[packet]}
              </text>
            </g>
          ))}
        </g>
      </g>
      {[
        [43, 43],
        [197, 43],
        [43, 197],
        [197, 197],
      ].map(([x, y]) => (
        <g key={`${x}-${y}`}>
          <circle cx={x} cy={y} r="4.5" fill="#080d11" stroke="#35434b" />
          <path
            d={`M${x - 2} ${y + 1}h4`}
            stroke="#58636b"
            strokeOpacity=".5"
          />
        </g>
      ))}
    </svg>
  );
}

export function PacketScene() {
  const host = useRef(null);
  const rear = useRef(null);
  const front = useRef(null);
  const core = useRef(null);
  const routes = useMemo(createCanopyRoutes, []);
  useEffect(() => {
    const element = host.current;
    const hero = element.parentElement;
    const app = element.closest(".app");
    const back = rear.current.getContext("2d");
    const fore = front.current.getContext("2d");
    const packets = [...core.current.querySelectorAll(".processor-packet")];
    const highlight = core.current.querySelector(".processor-highlight");
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0,
      time = 4.2,
      previous = null,
      hover = null,
      intersecting = true;
    let metrics,
      drawCount = 0,
      disposed = false;
    function reduced() {
      const explicit = document.documentElement.dataset.reducedMotion;
      return explicit === "true" || (explicit !== "false" && media.matches);
    }
    function running() {
      return !disposed && !document.hidden && intersecting && !reduced();
    }
    function resize() {
      if (disposed || !rear.current || !front.current) return;
      const { width: w, height: h } = app.getBoundingClientRect();
      const portrait = w / h < 1.2;
      const scale =
        w < 640
          ? Math.min(w / 1000, (h - 180) / 1000)
          : portrait
            ? Math.min(w / 1350, (h - 170) / 1080)
            : Math.min(w / 1920, (h - 150) / 900);
      const s = Math.max(0.2, scale);
      const x = (w - 1920 * s) / 2;
      const y = Math.max(
        w < 640 ? 58 : 0,
        (h - 1080 * s) * (portrait ? 0.32 : 0.22),
      );
      const stacked = w < 500;
      const buttonWidth = Math.min(250, stacked ? w - 48 : (w - 72) / 2);
      let left = stacked ? w / 2 : Math.max(buttonWidth / 2 + 24, x + 650 * s);
      let right = stacked
        ? w / 2
        : Math.min(w - buttonWidth / 2 - 24, x + 1270 * s);
      const spread = !stacked && right - left < buttonWidth + 24;
      if (spread) {
        const center = (left + right) / 2;
        left = center - (buttonWidth + 24) / 2;
        right = center + (buttonWidth + 24) / 2;
      }
      const actionY = y + 814 * s;
      metrics = {
        w,
        h,
        s,
        x,
        y,
        left,
        right,
        buttonWidth,
        actionY,
        stacked,
        custom: w < 1100 || portrait || spread,
      };
      const vars = {
        "--canopy-scale": s,
        "--canopy-x": `${x}px`,
        "--canopy-y": `${y}px`,
        "--action-left": `${left}px`,
        "--action-right": `${right}px`,
        "--action-top": `${actionY}px`,
        "--action-second-top": `${actionY + (stacked ? 81 : 0)}px`,
        "--action-width": `${buttonWidth}px`,
      };
      for (const [key, value] of Object.entries(vars))
        hero.style.setProperty(key, value);
      const ratio = Math.min(devicePixelRatio || 1, 2);
      for (const canvas of [rear.current, front.current]) {
        canvas.width = Math.max(1, Math.round(w * ratio));
        canvas.height = Math.max(1, Math.round(h * ratio));
      }
      metrics.ratio = ratio;
      metrics.routes = routes;
      if (y > 20) {
        metrics.routes = routes.map((route) => {
          const start = route.points[0];
          if (x + start.x * s < 0 || x + start.x * s > w) return route;
          const points = [
            { x: start.x, y: -y / s - 35 },
            ...route.points.map((p) => ({ ...p })),
          ];
          let length = 0;
          points.forEach((point, index) => {
            if (index)
              length += Math.hypot(
                point.x - points[index - 1].x,
                point.y - points[index - 1].y,
              );
            point.length = length;
          });
          return { ...route, points, length };
        });
      }
      paint();
    }
    function adaptiveCircuits() {
      const { x, y, s, left, right, actionY, stacked, w } = metrics;
      for (const [side, target] of [
        [-1, left],
        [1, right],
      ]) {
        const color = side < 0 ? "#ad96ca" : "#64b9ba";
        const startX = x + (960 + side * 95) * s,
          startY = y + 630 * s;
        const endY = actionY + (stacked && side > 0 ? 81 : 0);
        for (let track = 0; track < 3; track++) {
          const shift = track * 3 * s;
          const elbow = stacked
            ? side < 0
              ? 16
              : w - 16
            : startX + side * 44 * s;
          back.beginPath();
          back.moveTo(startX, startY + shift);
          back.lineTo(elbow, startY + shift);
          if (stacked) {
            back.lineTo(elbow, endY - 20 - shift);
            back.lineTo(target, endY - 10 - shift);
          } else {
            back.lineTo(target + side * shift, endY - 48 - shift);
          }
          back.lineTo(target, endY);
          back.strokeStyle = color;
          back.lineWidth = 0.8;
          back.globalAlpha =
            hover === (side < 0 ? "open" : "capture") ? 0.9 : 0.5;
          back.stroke();
        }
      }
      back.globalAlpha = 1;
    }
    function paint() {
      if (!metrics || disposed) return;
      const { w, h, s, x, y, ratio, custom } = metrics;
      for (const ctx of [back, fore]) {
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
        ctx.setTransform(ratio * s, 0, 0, ratio * s, ratio * x, ratio * y);
      }
      drawCanopy(back, fore, metrics.routes, time, hover, {
        skipCircuits: custom,
      });
      if (custom) {
        back.setTransform(ratio, 0, 0, ratio, 0, 0);
        adaptiveCircuits();
      }
      const positions = processingPositions(time);
      packets.forEach((packet, index) => {
        const position = positions[index];
        packet.style.offsetDistance = `${position * 100}%`;
        packet.style.opacity = String(
          Math.min(1, position / 0.055, (1 - position) / 0.055),
        );
      });
      const phase = (time / 6.4) % 1;
      const moving = !(
        (phase >= 0.2 && phase < 0.32) ||
        (phase >= 0.58 && phase < 0.72)
      );
      highlight.setAttribute("stroke-dashoffset", String(-positions[0] * 214));
      highlight.setAttribute(
        "opacity",
        String(moving ? 0.28 + 0.04 * Math.sin(phase * Math.PI * 2) : 0.07),
      );
      element.dataset.draw = String(++drawCount);
      element.dataset.processing = positions.join(",");
    }
    function tick(now) {
      frame = 0;
      if (!running()) {
        previous = null;
        return;
      }
      if (previous !== null) time += Math.min((now - previous) / 1000, 0.05);
      previous = now;
      paint();
      frame = requestAnimationFrame(tick);
    }
    function synchronize() {
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      previous = null;
      element.dataset.motion =
        document.hidden || !intersecting
          ? "hidden"
          : reduced()
            ? "reduced"
            : "running";
      element.dataset.animationPaused = String(!running());
      if (!document.hidden) paint();
      if (running()) frame = requestAnimationFrame(tick);
    }
    function focusRoute(event) {
      const action = event.target.closest?.(".packet-action");
      hover = action?.classList.contains("landing-open")
        ? "open"
        : action
          ? "capture"
          : null;
      if (!running()) paint();
    }
    function clearRoute(event) {
      const current = event.target.closest?.(".packet-action");
      const next = event.relatedTarget?.closest?.(".packet-action");
      if (current && current === next) return;
      hover = null;
      if (!running()) paint();
    }
    const observer = new ResizeObserver(resize);
    observer.observe(app);
    const preferenceObserver = new MutationObserver(synchronize);
    preferenceObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-reduced-motion"],
    });
    const intersection = new IntersectionObserver((entries) => {
      intersecting = entries[0].isIntersecting;
      synchronize();
    });
    intersection.observe(element);
    document.addEventListener("visibilitychange", synchronize);
    media.addEventListener("change", synchronize);
    hero.addEventListener("pointerover", focusRoute);
    hero.addEventListener("focusin", focusRoute);
    hero.addEventListener("pointerout", clearRoute);
    hero.addEventListener("focusout", clearRoute);
    resize();
    synchronize();
    return () => {
      disposed = true;
      if (frame) cancelAnimationFrame(frame);
      observer.disconnect();
      preferenceObserver.disconnect();
      intersection.disconnect();
      document.removeEventListener("visibilitychange", synchronize);
      media.removeEventListener("change", synchronize);
      hero.removeEventListener("pointerover", focusRoute);
      hero.removeEventListener("focusin", focusRoute);
      hero.removeEventListener("pointerout", clearRoute);
      hero.removeEventListener("focusout", clearRoute);
    };
  }, [routes]);
  return (
    <div ref={host} className="packet-scene" data-route-count={routes.length}>
      <canvas
        ref={rear}
        className="canopy-canvas canopy-rear"
        aria-hidden="true"
      />
      <div className="canopy-brand">
        <h1 className="surge-wordmark" tabIndex={-1}>
          SURGE
        </h1>
        <p className="canopy-subtitle">
          <span>Capture telemetry.</span> <span>Investigate behavior.</span>
        </p>
      </div>
      <canvas
        ref={front}
        className="canopy-canvas canopy-front"
        aria-hidden="true"
      />
      <div ref={core} className="canopy-core">
        <Processor />
      </div>
    </div>
  );
}

export const Octahedron = Processor;
export function OpticalMark({ className = "" }) {
  return (
    <span className={`optical-mark ${className}`} aria-hidden="true">
      <Processor />
    </span>
  );
}
