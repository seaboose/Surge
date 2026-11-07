// Approved 1920 x 1080 canopy geometry. Colors and packet identities belong to sources.
const COLORS = ["#aa94c3", "#67b6b7", "#c8a371", "#8da6bf"];

function catmull(points) {
  const out = [];
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[Math.max(0, i - 1)],
      b = points[i],
      c = points[i + 1],
      d = points[Math.min(points.length - 1, i + 2)];
    for (let step = 0; step < 35; step++) {
      const t = step / 35,
        t2 = t * t,
        t3 = t2 * t;
      out.push({
        x:
          0.5 *
          (2 * b.x +
            (-a.x + c.x) * t +
            (2 * a.x - 5 * b.x + 4 * c.x - d.x) * t2 +
            (-a.x + 3 * b.x - 3 * c.x + d.x) * t3),
        y:
          0.5 *
          (2 * b.y +
            (-a.y + c.y) * t +
            (2 * a.y - 5 * b.y + 4 * c.y - d.y) * t2 +
            (-a.y + 3 * b.y - 3 * c.y + d.y) * t3),
      });
    }
  }
  out.push(points[points.length - 1]);
  let length = 0;
  out.forEach((p, i) => {
    if (i) length += Math.hypot(p.x - out[i - 1].x, p.y - out[i - 1].y);
    p.length = length;
  });
  return { points: out, length };
}
function cableWithEntry(points, destination) {
  const out = catmull(points).points;
  const a = out[out.length - 1],
    b = { x: a.x, y: a.y + 12 },
    c = { x: destination, y: 491 },
    d = { x: destination, y: 507 };
  for (let i = 1; i <= 32; i++) {
    const t = i / 32,
      u = 1 - t;
    out.push({
      x:
        u * u * u * a.x +
        3 * u * u * t * b.x +
        3 * u * t * t * c.x +
        t * t * t * d.x,
      y:
        u * u * u * a.y +
        3 * u * u * t * b.y +
        3 * u * t * t * c.y +
        t * t * t * d.y,
    });
  }
  for (let y = 509; y <= 532; y += 1) out.push({ x: destination, y });
  let length = 0;
  out.forEach((p, i) => {
    if (i) length += Math.hypot(p.x - out[i - 1].x, p.y - out[i - 1].y);
    p.length = length;
  });
  return { points: out, length };
}

export function createCanopyRoutes() {
  const colors = COLORS;
  let seed = 913753;
  const random = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  const between = (a, b) => a + (b - a) * random();
  const routes = [];
  const TOTAL = 32;
  for (let i = 0; i < TOTAL; i++) {
    const kind = i % 4;
    let origin;
    if (kind === 0) origin = { x: between(430, 1490), y: -35 };
    else if (kind === 1) origin = { x: -35, y: between(12, 240) };
    else if (kind === 2) origin = { x: 1955, y: between(15, 250) };
    else origin = { x: between(40, 1880), y: -35 };
    if (i === 0) origin = { x: 83, y: 36 };
    if (i === 1) origin = { x: 1810, y: 39 };
    const destination = 901 + i * 3.65 + Math.sin(i * 1.3) * 1.1;
    const titleX = 568 + i * 25;
    const bendY = between(230, 313);
    const shoulderY = between(451, 478);
    const sourceApproach =
      kind === 0
        ? [
            { x: origin.x + between(-95, 95), y: between(40, 108) },
            { x: origin.x + between(-130, 130), y: between(153, 230) },
          ]
        : kind === 1
          ? [
              { x: between(125, 380), y: origin.y + between(-50, 65) },
              { x: between(380, 765), y: between(110, 258) },
            ]
          : kind === 2
            ? [
                { x: between(1560, 1800), y: origin.y + between(-52, 55) },
                { x: between(1160, 1515), y: between(108, 256) },
              ]
            : [
                { x: origin.x + between(-230, 230), y: between(48, 155) },
                {
                  x: origin.x * 0.5 + 960 * 0.5 + between(-245, 245),
                  y: between(150, 252),
                },
              ];
    const points = [
      origin,
      ...sourceApproach,
      { x: titleX + between(-32, 32), y: bendY },
      {
        x: titleX * 0.78 + 960 * 0.22 + between(-12, 12),
        y: between(359, 405),
      },
      {
        x: 776 + i * 12.2 + Math.sin(i * 0.63) * 10 - (i > 18 ? 12 : 0),
        y: shoulderY,
      },
    ];
    const curve = cableWithEntry(points, destination),
      color = colors[Math.floor(random() * colors.length)];
    const foreground = [6, 16, 25].includes(i);
    const depth = foreground || i % 8 === 0 ? 2 : i % 3 === 0 ? 1 : 0;
    const route = {
      ...curve,
      id: i,
      kind,
      depth,
      destination,
      color,
      width: [0.6, 0.8, 1.15][depth],
      speed: between(24, 44),
      phase: random(),
      front: foreground,
      prominence: [0.39, 0.7, 1][depth],
      packets: [],
      depthY: between(366, 398),
    };
    const count = 5 + Math.floor(random() * 3);
    for (let n = 0; n < count; n++)
      route.packets.push({
        phase: (n + between(0.08, 0.9)) / count,
        label: Math.floor(random() * 256)
          .toString(16)
          .toUpperCase()
          .padStart(2, "0"),
        size: [11, 12.3, 14][depth],
      });
    routes.push(route);
  }
  routes.sort((a, b) => a.depth - b.depth || a.id - b.id);
  return routes;
}

export function processingProgress(phase) {
  if (phase < 0.2) return (0.22 * phase) / 0.2;
  if (phase < 0.32) return 0.22;
  if (phase < 0.58) return 0.22 + (0.36 * (phase - 0.32)) / 0.26;
  if (phase < 0.72) return 0.58;
  return 0.58 + (0.42 * (phase - 0.72)) / 0.28;
}

export function processingPositions(time) {
  const progress = processingProgress((time / 6.4) % 1);
  return [0, 1, 2].map((index) => (progress + index / 3) % 1);
}

export function drawCanopy(
  rearContext,
  frontContext,
  routes,
  time,
  hover = null,
  options = {},
) {
  const rear = rearContext,
    front = frontContext;
  const frame = { time, hover };
  const state = { density: 1, brightness: 1 };
  function pointAt(route, distance) {
    const pts = route.points;
    let lo = 0,
      hi = pts.length - 1;
    while (lo + 1 < hi) {
      const mid = (lo + hi) >> 1;
      if (pts[mid].length < distance) lo = mid;
      else hi = mid;
    }
    const a = pts[lo],
      b = pts[hi],
      t = (distance - a.length) / (b.length - a.length || 1);
    return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
  }
  function pathStroke(ctx, points, color, width, alpha, halo = false) {
    if (points.length < 2) return;
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let j = 1; j < points.length; j++)
      ctx.lineTo(points[j].x, points[j].y);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    if (halo) {
      ctx.strokeStyle = "#050607";
      ctx.lineWidth = width + 1.65;
      ctx.globalAlpha = 0.94;
      ctx.stroke();
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.globalAlpha = alpha * state.brightness;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
  function isFront(route, p) {
    return route.front && p.y > 309 && p.y < 454;
  }
  function paintPackets(route, foreground) {
    for (const packet of route.packets) {
      const dist =
        (packet.phase * route.length + frame.time * route.speed) % route.length;
      const p = pointAt(route, dist);
      if (isFront(route, p) !== foreground) continue;
      const ctx = foreground ? front : rear;
      const fade = Math.min(1, dist / 65, (route.length - dist) / 30);
      ctx.font = `${packet.size}px ui-monospace,Consolas,monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      if (!foreground) {
        const metrics = ctx.measureText(packet.label);
        ctx.fillStyle = "#050607";
        ctx.globalAlpha = 0.9 * fade;
        ctx.fillRect(
          p.x - metrics.width / 2 - 2,
          p.y - packet.size / 2 - 1,
          metrics.width + 4,
          packet.size + 2,
        );
      }
      ctx.globalAlpha =
        (foreground ? 1 : 0.94 * route.prominence) * fade * state.brightness;
      ctx.fillStyle = route.color;
      ctx.fillText(packet.label, p.x, p.y);
      ctx.globalAlpha = 1;
    }
  }
  function drawRoutes() {
    for (const route of routes) {
      pathStroke(
        rear,
        route.points,
        route.color,
        route.width,
        0.34 * route.prominence,
        true,
      );
      paintPackets(route, false);
    }
    for (const route of routes) {
      if (route.front) {
        let segment = [];
        for (const p of route.points) {
          if (isFront(route, p)) segment.push(p);
          else if (segment.length) {
            pathStroke(front, segment, route.color, route.width, 0.9, false);
            segment = [];
          }
        }
        pathStroke(front, segment, route.color, route.width, 0.9, false);
      }
      paintPackets(route, true);
    }
  }
  function circuit(side) {
    const dir = side === "open" ? -1 : 1,
      color = side === "open" ? "#ad96ca" : "#64b9ba";
    const x = 960 + dir * 95,
      end = 960 + dir * 310,
      lit = frame.hover === side;
    for (let i = 0; i < 3; i++) {
      const points = [
        { x, y: 630 + i * 4 },
        { x: 960 + dir * (157 + i * 4), y: 630 + i * 4 },
        { x: end + dir * i * 4, y: 754 + i * 4 },
        { x: end + dir * i * 4, y: 814 },
      ];
      pathStroke(rear, points, color, lit ? 1.1 : 0.8, lit ? 0.95 : 0.58);
      const offset = (frame.time * 28 + i * 46) % 225;
      const a = { x: x + dir * Math.min(offset, 62), y: 630 + i * 4 };
      if (offset < 62)
        pathStroke(rear, [a, { x: a.x + dir * 8, y: a.y }], color, 1.5, 0.9);
    }
    pathStroke(
      rear,
      [
        { x: 960 + dir * 243, y: 710 },
        { x: 960 + dir * 270, y: 710 },
        { x: 960 + dir * 288, y: 728 },
        { x: 960 + dir * 325, y: 728 },
      ],
      color,
      0.8,
      0.46,
    );
    rear.beginPath();
    rear.arc(960 + dir * 329, 728, 3.1, 0, Math.PI * 2);
    rear.strokeStyle = color;
    rear.globalAlpha = 0.6;
    rear.lineWidth = 0.8;
    rear.stroke();
    rear.globalAlpha = 1;
  }
  drawRoutes();
  if (!options.skipCircuits) {
    circuit("open");
    circuit("capture");
  }
}
