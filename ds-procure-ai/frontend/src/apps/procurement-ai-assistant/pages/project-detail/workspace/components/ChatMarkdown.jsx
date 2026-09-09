import { useDeferredValue } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

function splitCells(line) {
  let value = String(line || "").trim();
  if (value.startsWith("|")) value = value.slice(1);
  if (value.endsWith("|")) value = value.slice(0, -1);
  return value.split("|").map((cell) => cell.trim());
}

function isPipeRow(line) {
  const trimmed = String(line || "").trim();
  return trimmed.includes("|") && splitCells(trimmed).length >= 2;
}

function isSeparatorRow(line) {
  const cells = splitCells(line);
  return cells.length >= 2 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function isNumberCell(cell) {
  return /^\d+$/.test(String(cell || "").trim());
}

// Model often emits "|---|------|| 1 | file || 2 | file" on one line.
// Do not turn a pipe separator into a horizontal rule. Split row boundaries only.
function unglueTableRows(text) {
  return String(text || "")
    .split("\n")
    .map((line) => {
      if (!line.includes("|")) return line;
      let value = line;
      value = value.replace(
        /(\|\s*:?-{3,}:?(?:\s*\|\s*:?-{3,}:?)*\s*\|)\s*(?=\|)/g,
        "$1\n",
      );
      value = value.replace(/\|\s*\|(?=\s*\S)/g, "|\n|");
      return value;
    })
    .join("\n");
}

function tableLine(cells) {
  return `| ${cells.join(" | ")} |`;
}

function normalizeTableBlock(rows) {
  const body = rows.filter((row) => isPipeRow(row) && !isSeparatorRow(row));
  if (body.length < 2) return rows.join("\n");
  const header = splitCells(body[0]);
  const data = body.slice(1).map(splitCells).filter((row) => row.some(Boolean));
  if (!data.length) return rows.join("\n");
  const cols = Math.max(header.length, ...data.map((row) => row.length));
  let headerCells = header.slice(0, cols);
  if (
    headerCells.length < cols &&
    data.every((row) => isNumberCell(row[0]))
  ) {
    headerCells = ["#", ...headerCells];
  }
  while (headerCells.length < cols) headerCells.push("");
  const lines = [
    tableLine(headerCells.slice(0, cols)),
    tableLine(Array.from({ length: cols }, () => "---")),
    ...data.map((row) => {
      const cells = row.slice(0, cols);
      while (cells.length < cols) cells.push("");
      return tableLine(cells);
    }),
  ];
  return lines.join("\n");
}

function repairTables(text) {
  const lines = unglueTableRows(text).split("\n");
  const out = [];
  let index = 0;
  while (index < lines.length) {
    if (!isPipeRow(lines[index])) {
      out.push(lines[index]);
      index += 1;
      continue;
    }
    const block = [];
    while (index < lines.length && (isPipeRow(lines[index]) || lines[index].trim() === "")) {
      if (lines[index].trim() !== "") block.push(lines[index]);
      if (lines[index].trim() === "" && block.length) break;
      index += 1;
    }
    out.push(normalizeTableBlock(block));
  }
  return out.join("\n");
}

function cleanReply(text) {
  let value = String(text || "");
  if (!value.trim()) return "";
  value = value.replace(/\(no matching chunks\)/g, "");
  value = value.replace(/(^|\n)\s*\[\{[\s\S]*?\}\]\s*/m, "$1");
  value = value.replace(/([^\n])\s*(#{1,4}\s)/g, "$1\n\n$2");
  value = value.replace(/([a-z0-9])\.([A-Z])/g, "$1. $2");
  // Whole-line dashes only. A "| --- |" separator must stay a table separator.
  value = value.replace(/(^|\n)[ \t]*-{3,}[ \t]*(?=\n|$)/g, "$1\n\n---\n\n");
  value = repairTables(value);
  return value.trim();
}

function TableBlock({ children }) {
  return (
    <div className="ws-md-table">
      <table>{children}</table>
    </div>
  );
}

function ChatMarkdown({ text, streaming = false }) {
  const deferred = useDeferredValue(text ?? "");
  const source = cleanReply(streaming ? deferred : text);

  if (!source) {
    return null;
  }

  return (
    <div className="ws-md">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: TableBlock,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {source}
      </Markdown>
      {streaming ? <span className="ws-stream-caret" aria-hidden="true" /> : null}
    </div>
  );
}

export default ChatMarkdown;
