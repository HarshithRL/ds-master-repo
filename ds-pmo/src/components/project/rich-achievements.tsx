"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import DOMPurify from "dompurify";
import { useReadOnly } from "@/components/ui/read-only-context";

const COLORS = [
  { label: "Default", value: "" },
  { label: "Red", value: "#DC2626" },
  { label: "Orange", value: "#F97316" },
  { label: "Green", value: "#16A34A" },
  { label: "Blue", value: "#2563EB" },
  { label: "Purple", value: "#7C3AED" },
  { label: "Gray", value: "#6B7280" },
];

function ToolBtn({
  active,
  onClick,
  title,
  children,
}: {
  active?: boolean;
  onClick: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onMouseDown={(e) => { e.preventDefault(); onClick(); }}
      title={title}
      className={`w-6 h-6 flex items-center justify-center rounded text-[11px] transition-colors ${
        active
          ? "bg-gray-200 text-gray-800 dark:bg-[#3D4350] dark:text-gray-200"
          : "text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:text-gray-500 dark:hover:bg-[#333842] dark:hover:text-gray-300"
      }`}
    >
      {children}
    </button>
  );
}

export function RichTextEditor({
  value,
  onSave,
  placeholder = "Type here…",
}: {
  value: string;
  onSave: (v: string) => void;
  placeholder?: string;
}) {
  const readOnly = useReadOnly();
  const editorRef = useRef<HTMLDivElement>(null);
  const lastSaved = useRef(value);
  const [showColorPicker, setShowColorPicker] = useState(false);
  const colorRef = useRef<HTMLDivElement>(null);

  // Sync external value on mount / when value changes from outside
  useEffect(() => {
    if (!editorRef.current) return;
    if (value !== lastSaved.current) {
      editorRef.current.innerHTML = DOMPurify.sanitize(value);
      lastSaved.current = value;
    }
  }, [value]);

  // Init on mount
  useEffect(() => {
    if (editorRef.current && !editorRef.current.innerHTML && value) {
      editorRef.current.innerHTML = DOMPurify.sanitize(value);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Close color picker on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (colorRef.current && !colorRef.current.contains(e.target as Node)) {
        setShowColorPicker(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const flush = useCallback(() => {
    if (!editorRef.current) return;
    const html = DOMPurify.sanitize(editorRef.current.innerHTML);
    // Treat empty / whitespace-only / <br> as empty
    const isEmpty = !html || html === "<br>" || html.replace(/<[^>]*>/g, "").trim() === "";
    const v = isEmpty ? "" : html;
    if (v !== lastSaved.current) {
      lastSaved.current = v;
      onSave(v);
    }
  }, [onSave]);

  const handleInput = () => {
    flush();
  };

  const exec = (cmd: string, arg?: string) => {
    document.execCommand(cmd, false, arg);
    editorRef.current?.focus();
  };

  if (readOnly) {
    const sanitized = DOMPurify.sanitize(value);
    const isEmpty = !sanitized || sanitized === "<br>" || sanitized.replace(/<[^>]*>/g, "").trim() === "";
    return (
      <div className="border rounded border-(--border) bg-(--background)">
        {isEmpty ? (
          <div className="px-3 py-2 text-sm text-muted-foreground leading-relaxed min-h-18">—</div>
        ) : (
          <div
            className="rich-achievements-editor px-3 py-2 text-sm text-(--foreground) leading-relaxed min-h-18"
            dangerouslySetInnerHTML={{ __html: sanitized }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="border rounded overflow-hidden transition-colors border-(--border) bg-(--background) focus-within:border-etex-orange focus-within:shadow-[0_0_0_3px_rgba(232,113,58,0.08)]">
      {/* Toolbar */}
      <div className="flex items-center gap-0.5 px-2 py-1 border-b border-(--border) bg-(--muted)">
        <ToolBtn onClick={() => exec("bold")} title="Bold">
          <span className="font-bold">B</span>
        </ToolBtn>
        <ToolBtn onClick={() => exec("italic")} title="Italic">
          <span className="italic">I</span>
        </ToolBtn>
        <ToolBtn onClick={() => exec("underline")} title="Underline">
          <span className="underline">U</span>
        </ToolBtn>
        <div className="w-px h-4 bg-(--border) mx-1" />
        <ToolBtn onClick={() => exec("insertUnorderedList")} title="Bullet list">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <circle cx="3" cy="4" r="1.2" fill="currentColor" stroke="none" />
            <circle cx="3" cy="8" r="1.2" fill="currentColor" stroke="none" />
            <circle cx="3" cy="12" r="1.2" fill="currentColor" stroke="none" />
            <line x1="6.5" y1="4" x2="14" y2="4" />
            <line x1="6.5" y1="8" x2="14" y2="8" />
            <line x1="6.5" y1="12" x2="14" y2="12" />
          </svg>
        </ToolBtn>
        <div className="w-px h-4 bg-(--border) mx-1" />
        {/* Color picker */}
        <div className="relative" ref={colorRef}>
          <ToolBtn
            onClick={() => setShowColorPicker((p) => !p)}
            title="Text color"
          >
            <span className="flex flex-col items-center leading-none">
              <span className="text-[11px] font-semibold">A</span>
              <span
                className="w-3.5 h-[2px] rounded-full mt-px"
                style={{ background: "linear-gradient(90deg, #DC2626, #F97316, #16A34A, #2563EB, #7C3AED)" }}
              />
            </span>
          </ToolBtn>
          {showColorPicker && (
            <div className="absolute top-full left-0 mt-1 z-20 bg-(--card) border border-(--border) rounded-md shadow-lg dark:shadow-[0_4px_12px_rgba(0,0,0,0.4)] p-1.5 flex gap-1">
              {COLORS.map((c) => (
                <button
                  key={c.value || "default"}
                  type="button"
                  title={c.label}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    if (c.value) {
                      exec("foreColor", c.value);
                    } else {
                      exec("removeFormat");
                    }
                    setShowColorPicker(false);
                  }}
                  className="w-5 h-5 rounded-full border border-(--border) hover:scale-125 transition-transform"
                  style={{ backgroundColor: c.value || "#374151" }}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Editable area */}
      <div
        ref={editorRef}
        contentEditable
        suppressContentEditableWarning
        onInput={handleInput}
        onBlur={() => flush()}
        data-placeholder={placeholder}
        className="rich-achievements-editor px-3 py-2 text-sm text-(--foreground) leading-relaxed min-h-18 max-h-40 overflow-y-auto outline-none empty:before:content-[attr(data-placeholder)] empty:before:text-(--muted-foreground) empty:before:pointer-events-none"
      />
    </div>
  );
}

