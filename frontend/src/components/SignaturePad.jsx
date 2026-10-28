/*
 * Kikan - suivi des actifs et remise de materiel signee
 * Copyright (C) 2026 Gabriel Chollet
 * Developpe avec l'assistance d'une IA (Claude, Anthropic).
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

import { forwardRef, useImperativeHandle, useRef, useState } from "react";

// Resolution interne fixe : l'image envoyee fait toujours 1000 x 400 pixels, quelle que soit la taille
// d'affichage. Les coordonnees du pointeur sont converties vers cette resolution.
const W = 1000;
const H = 400;

/**
 * Zone de signature manuscrite (doigt, stylet ou souris, via les evenements "pointer").
 * Methodes exposees : clear(), isEmpty(), toDataURL(), stats() -> { strokes, durationMs }.
 */
const SignaturePad = forwardRef(function SignaturePad({ onChange }, ref) {
  const canvasRef = useRef(null);
  const st = useRef({ drawing: false, strokes: 0, startedAt: 0, endedAt: 0, last: null, id: null });
  const [empty, setEmpty] = useState(true);

  const ctx = () => {
    const c = canvasRef.current.getContext("2d");
    c.lineWidth = 5;
    c.lineCap = "round";
    c.lineJoin = "round";
    c.strokeStyle = "#111111";
    return c;
  };

  const point = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    return { x: ((e.clientX - rect.left) * W) / rect.width, y: ((e.clientY - rect.top) * H) / rect.height };
  };

  const down = (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    e.preventDefault();
    canvasRef.current.setPointerCapture(e.pointerId);
    const p = point(e);
    const s = st.current;
    s.drawing = true;
    s.id = e.pointerId;
    s.last = p;
    if (s.strokes === 0) s.startedAt = performance.now();
    s.strokes += 1;
    // Un point au simple appui (le trait peut etre tres court).
    const c = ctx();
    c.beginPath();
    c.arc(p.x, p.y, 2.5, 0, Math.PI * 2);
    c.fillStyle = "#111111";
    c.fill();
  };

  const move = (e) => {
    const s = st.current;
    if (!s.drawing || e.pointerId !== s.id) return;
    e.preventDefault();
    const c = ctx();
    const events = e.nativeEvent.getCoalescedEvents ? e.nativeEvent.getCoalescedEvents() : [e];
    for (const ev of events.length ? events : [e]) {
      const p = point(ev);
      c.beginPath();
      c.moveTo(s.last.x, s.last.y);
      c.lineTo(p.x, p.y);
      c.stroke();
      s.last = p;
    }
    if (empty) { setEmpty(false); if (onChange) onChange(false); }
  };

  const up = (e) => {
    const s = st.current;
    if (!s.drawing || e.pointerId !== s.id) return;
    s.drawing = false;
    s.endedAt = performance.now();
    if (empty) { setEmpty(false); if (onChange) onChange(false); }
  };

  const clear = () => {
    const c = canvasRef.current.getContext("2d");
    c.clearRect(0, 0, W, H);
    st.current = { drawing: false, strokes: 0, startedAt: 0, endedAt: 0, last: null, id: null };
    setEmpty(true);
    if (onChange) onChange(true);
  };

  useImperativeHandle(ref, () => ({
    clear,
    isEmpty: () => empty,
    toDataURL: () => canvasRef.current.toDataURL("image/png"),
    stats: () => ({
      strokes: st.current.strokes,
      durationMs: Math.max(0, Math.round(st.current.endedAt - st.current.startedAt)),
    }),
  }));

  return (
    <div className="sigpad-wrap">
      <canvas
        ref={canvasRef}
        width={W}
        height={H}
        className="sigpad"
        data-testid="signature-canvas"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        onContextMenu={(e) => e.preventDefault()}
        aria-label="Zone de signature"
      />
      {empty && <div className="sigpad-hint">Signez ici</div>}
    </div>
  );
});

export default SignaturePad;
