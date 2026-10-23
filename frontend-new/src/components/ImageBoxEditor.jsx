import { useRef, useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { detectImageElements } from "../api/render.js";

/**
 * Upload a screenshot or mock-up and draw a box around each element on it.
 *
 * An image has no page code to read element positions from, so they are
 * found from the pixels: on upload the server reads the text (OCR) and finds
 * the shapes (OpenCV), and suggests a box for each button, field, menu,
 * image and block of text, already named and typed
 * (backend/render/image_detect.py). The tester checks them: rename, retype,
 * delete, or drag on the image to add one that was missed. The result goes to
 * POST /api/sessions with mode="image" (backend/api/uploads.py).
 *
 * value: null | { fileName, dataUrl, width, height, title, boxes: [
 *   { id, label, type, importance, bbox: [x, y, w, h] } ] }   (bbox = 0-1 of the image)
 */

// Mirrors backend/api/uploads.py.
export const UPLOAD_LIMITS = { maxBytes: 10 * 1024 * 1024, minWidth: 320, maxWidth: 4000, maxHeight: 20000 };
const MIN_BOX_PX = 12;
const ACCEPT = ["image/png", "image/jpeg", "image/webp"];

// The agents' element vocabulary (backend/attribution/elements.py), in words.
export const BOX_TYPES = [
  ["CTA", "Button or link"],
  ["text", "Text or form field"],
  ["image", "Image"],
  ["nav", "Navigation / menu"],
  ["non-interactive", "Decoration (not clickable)"],
];
export const BOX_IMPORTANCE = [
  ["high", "High: users must find it"],
  ["medium", "Medium"],
  ["low", "Low"],
];
const TYPE_COLOR = {
  CTA: "rgb(var(--color-accent))",
  text: "rgb(var(--color-cool))",
  image: "rgb(var(--color-amber))",
  nav: "rgb(var(--color-text-secondary))",
  "non-interactive": "rgb(var(--color-coral))",
};

/** Ready to start a test with? Returns a reason when not. */
export function uploadProblem(value) {
  if (!value) return "Upload an image first.";
  if (!value.title.trim()) return "Give the screenshot a name.";
  if (!value.boxes.length) return "Draw at least one box on the image.";
  const unnamed = value.boxes.findIndex((b) => !b.label.trim());
  if (unnamed >= 0) return `Name box ${unnamed + 1}.`;
  return null;
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("The file couldn't be read."));
    reader.readAsDataURL(file);
  });
}

function imageSize(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = () => reject(new Error("That file isn't a readable image."));
    img.src = src;
  });
}

const clamp01 = (v) => Math.min(1, Math.max(0, v));

export default function ImageBoxEditor({ value, onChange }) {
  const { token } = useAuth();
  const [error, setError] = useState(null);
  const [detecting, setDetecting] = useState(false);
  const [detected, setDetected] = useState(null); // { count, seconds } after a run
  const [selected, setSelected] = useState(null);
  const [draft, setDraft] = useState(null); // box being drawn, in 0-1 units
  const [dragOver, setDragOver] = useState(false);
  const surfaceRef = useRef(null);
  const startRef = useRef(null);
  const nextId = useRef(1);

  async function loadFile(file) {
    setError(null);
    if (!file) return;
    if (!ACCEPT.includes(file.type)) return setError("Upload a PNG, JPEG or WebP image.");
    if (file.size > UPLOAD_LIMITS.maxBytes) return setError("The image is larger than 10 MB.");
    try {
      const dataUrl = await readFile(file);
      const { width, height } = await imageSize(dataUrl);
      if (width < UPLOAD_LIMITS.minWidth) return setError(`The image must be at least ${UPLOAD_LIMITS.minWidth} px wide.`);
      if (width > UPLOAD_LIMITS.maxWidth || height > UPLOAD_LIMITS.maxHeight) {
        return setError(`The image must be at most ${UPLOAD_LIMITS.maxWidth} px wide and ${UPLOAD_LIMITS.maxHeight} px tall.`);
      }
      setSelected(null);
      const base = {
        fileName: file.name, dataUrl, width, height,
        title: file.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ").slice(0, 80),
        boxes: [],
      };
      onChange(base);
      detect(base);
    } catch (err) {
      setError(err.message);
    }
  }

  // Ask the server to find the elements, then show them as editable boxes.
  async function detect(base) {
    setDetecting(true);
    setError(null);
    setDetected(null);
    try {
      const res = await detectImageElements(token, base.dataUrl);
      const boxes = res.elements.map((el) => ({
        id: nextId.current++, label: el.label, type: el.type, importance: el.importance,
        bbox: el.bbox, why: el.why, auto: true,
      }));
      setSelected(null);
      onChange({ ...base, boxes });
      setDetected({ count: boxes.length, seconds: res.seconds });
    } catch (err) {
      setError(`Couldn't find elements automatically (${err.message}). You can still draw boxes yourself.`);
    } finally {
      setDetecting(false);
    }
  }

  const update = (patch) => onChange({ ...value, ...patch });
  const updateBox = (id, patch) => update({ boxes: value.boxes.map((b) => (b.id === id ? { ...b, ...patch } : b)) });
  const removeBox = (id) => {
    update({ boxes: value.boxes.filter((b) => b.id !== id) });
    if (selected === id) setSelected(null);
  };

  function pointAt(e) {
    const r = surfaceRef.current.getBoundingClientRect();
    return { x: clamp01((e.clientX - r.left) / r.width), y: clamp01((e.clientY - r.top) / r.height) };
  }

  function onPointerDown(e) {
    if (e.button !== 0 || e.target !== surfaceRef.current) return;
    e.preventDefault();
    surfaceRef.current.setPointerCapture(e.pointerId);
    startRef.current = pointAt(e);
    setDraft({ x: startRef.current.x, y: startRef.current.y, w: 0, h: 0 });
  }

  function onPointerMove(e) {
    if (!startRef.current) return;
    const p = pointAt(e);
    const s = startRef.current;
    setDraft({ x: Math.min(s.x, p.x), y: Math.min(s.y, p.y), w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y) });
  }

  function onPointerUp() {
    if (!startRef.current || !draft) return;
    startRef.current = null;
    const big = draft.w * value.width >= MIN_BOX_PX && draft.h * value.height >= MIN_BOX_PX;
    setDraft(null);
    if (!big) return;
    const id = nextId.current++;
    update({ boxes: [...value.boxes, { id, label: "", type: "CTA", importance: "medium", bbox: [draft.x, draft.y, draft.w, draft.h] }] });
    setSelected(id);
  }

  if (!value) {
    return (
      <div className="mt-8">
        <label
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); loadFile(e.dataTransfer.files?.[0]); }}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-[22px] border-2 border-dashed px-6 py-16 text-center transition-colors ${dragOver ? "border-accent bg-accent/10" : "border-white/15 bg-surface/50 hover:border-accent/60"}`}
        >
          <span className="text-[18px] font-semibold text-text-primary">Upload a screenshot or design</span>
          <span className="mt-2 max-w-md text-[15px] text-text-secondary">
            Drop an image here or click to choose one. PNG, JPEG or WebP, up to 10 MB. GazeLens finds the buttons, fields, images and text on it for you to check.
          </span>
          <input type="file" accept={ACCEPT.join(",")} className="sr-only" onChange={(e) => loadFile(e.target.files?.[0])} />
        </label>
        {error && <p className="mt-3 text-[14px] text-coral" role="alert">{error}</p>}
      </div>
    );
  }

  const box = value.boxes.find((b) => b.id === selected);
  const field = "h-10 w-full rounded-[12px] border border-white/10 bg-bg/60 px-3 text-[14px] text-text-primary outline-none focus:border-accent/70 focus:ring-4 focus:ring-accent/15";

  return (
    <div className="mt-8 grid gap-5 lg:grid-cols-[1fr_320px]">
      <div>
        {detecting ? (
          <p className="mb-3 flex items-center gap-2 text-[14px] text-text-primary" role="status">
            <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
            Finding buttons, fields, images and text on your screenshot…
          </p>
        ) : (
          <p className="mb-3 text-[14px] text-text-secondary" role="status">
            {detected
              ? <>Found <span className="font-semibold text-accent">{detected.count}</span> elements automatically. Check their names and types, delete any that are wrong, and drag on the image to add anything that was missed.</>
              : "Drag on the image to draw a box around each button, link, image or block of text. Click a box to edit it."}
          </p>
        )}
        {error && <p className="mb-3 text-[14px] text-coral" role="alert">{error}</p>}
        <div className="max-h-[560px] overflow-y-auto rounded-[18px] border border-white/10 bg-bg">
          <div className="relative select-none">
            <img src={value.dataUrl} alt={value.title || "Uploaded screenshot"} className="block w-full" draggable={false} />
            <div
              ref={surfaceRef}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={() => { startRef.current = null; setDraft(null); }}
              className="absolute inset-0 cursor-crosshair touch-none"
              aria-label="Drawing area: drag to draw a box"
            >
              {value.boxes.map((b, i) => (
                <button
                  key={b.id}
                  type="button"
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={() => setSelected(b.id)}
                  title={b.label || `Box ${i + 1}`}
                  className={`absolute rounded-[4px] border-2 text-left ${selected === b.id ? "bg-white/15 ring-2 ring-white/70" : "bg-white/5 hover:bg-white/10"}`}
                  style={{
                    left: `${b.bbox[0] * 100}%`, top: `${b.bbox[1] * 100}%`,
                    width: `${b.bbox[2] * 100}%`, height: `${b.bbox[3] * 100}%`,
                    borderColor: TYPE_COLOR[b.type],
                  }}
                >
                  {/* above the box, or inside it when the box touches the top edge */}
                  <span className={`absolute -left-0.5 whitespace-nowrap rounded-[6px] bg-bg/90 px-1.5 py-0.5 text-[11px] font-semibold text-text-primary ${b.bbox[1] * value.height < 26 * value.width / 700 ? "top-0.5" : "-top-6"}`}>
                    {i + 1}{b.label ? ` · ${b.label}` : ""}
                  </span>
                </button>
              ))}
              {draft && (
                <div className="pointer-events-none absolute rounded-[4px] border-2 border-dashed border-accent bg-accent/10"
                  style={{ left: `${draft.x * 100}%`, top: `${draft.y * 100}%`, width: `${draft.w * 100}%`, height: `${draft.h * 100}%` }} />
              )}
            </div>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-[13px] text-text-secondary">
          <span>{value.fileName} · {value.width}×{value.height}px</span>
          <button type="button" disabled={detecting} onClick={() => detect(value)} className="font-medium text-accent hover:opacity-80 disabled:opacity-50">
            Detect again
          </button>
          {value.boxes.length > 0 && (
            <button type="button" disabled={detecting} onClick={() => { setSelected(null); update({ boxes: [] }); }} className="font-medium text-text-secondary hover:text-text-primary disabled:opacity-50">
              Clear all boxes
            </button>
          )}
          <button type="button" onClick={() => { setSelected(null); onChange(null); }} className="font-medium text-accent hover:opacity-80">
            Use a different image
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-[14px] font-medium text-text-primary">Name of this screenshot</span>
          <input className={field} value={value.title} maxLength={80} onChange={(e) => update({ title: e.target.value })} placeholder="e.g. Checkout page v2" />
        </label>

        {box ? (
          <div className="rounded-[18px] border border-accent/40 bg-surface/70 p-4">
            <div className="flex items-center justify-between">
              <span className="text-[15px] font-semibold text-text-primary">Box {value.boxes.indexOf(box) + 1}</span>
              <button type="button" onClick={() => removeBox(box.id)} className="text-[13px] font-medium text-coral hover:opacity-80">Delete box</button>
            </div>
            {box.auto && box.why && (
              <p className="mt-1 text-[12px] text-text-secondary">Found automatically: {box.why}.</p>
            )}
            <label className="mt-3 flex flex-col gap-1.5">
              <span className="text-[13px] text-text-secondary">What is it called?</span>
              <input autoFocus className={field} value={box.label} maxLength={60} onChange={(e) => updateBox(box.id, { label: e.target.value })} placeholder="e.g. Add to cart button" />
            </label>
            <label className="mt-3 flex flex-col gap-1.5">
              <span className="text-[13px] text-text-secondary">What kind of thing is it?</span>
              <select className={field} value={box.type} onChange={(e) => updateBox(box.id, { type: e.target.value })}>
                {BOX_TYPES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
            </label>
            <label className="mt-3 flex flex-col gap-1.5">
              <span className="text-[13px] text-text-secondary">How important is it?</span>
              <select className={field} value={box.importance} onChange={(e) => updateBox(box.id, { importance: e.target.value })}>
                {BOX_IMPORTANCE.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
            </label>
          </div>
        ) : (
          <p className="rounded-[18px] border border-white/10 bg-surface/50 p-4 text-[14px] text-text-secondary">
            {value.boxes.length ? "Click a box to name it or change its type." : "No boxes yet. Drag on the image to draw the first one."}
          </p>
        )}

        {value.boxes.length > 0 && (
          <ul className="flex flex-col gap-1.5">
            {value.boxes.map((b, i) => (
              <li key={b.id}>
                <button type="button" onClick={() => setSelected(b.id)}
                  className={`flex w-full items-center gap-2 rounded-[10px] px-3 py-2 text-left text-[14px] ${selected === b.id ? "bg-white/10" : "hover:bg-white/[0.05]"}`}>
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: TYPE_COLOR[b.type] }} />
                  <span className={b.label ? "truncate text-text-primary" : "italic text-coral"}>{i + 1}. {b.label || "needs a name"}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
