// Server-side HTML allowlist sanitizer for rich-text fields (keyAchievements).
// DOMPurify requires a DOM, which isn't available in Node — and we don't want
// to pull in jsdom. The RichTextEditor only produces a small, known set of
// tags, so a strict allowlist + attribute filter is sufficient here. Output is
// safe to pass to dangerouslySetInnerHTML.

const ALLOWED_TAGS = new Set([
  "b", "strong", "i", "em", "u",
  "br",
  "p", "div", "span",
  "ul", "ol", "li",
]);

const TAGS_ALLOWING_STYLE = new Set(["span", "div", "p"]);

// Only `color: <named>` or `color: #hex`. No url(), no expression(), no other
// properties — we don't merge multiple declarations.
const COLOR_STYLE_RE = /^\s*color\s*:\s*(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)\s*;?\s*$/;

const ATTR_RE =
  /([a-zA-Z_:][a-zA-Z0-9_:.-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/g;

type Token =
  | { type: "text"; value: string }
  | { type: "tag"; value: string };

function* tokenize(html: string): Generator<Token> {
  let i = 0;
  while (i < html.length) {
    const lt = html.indexOf("<", i);
    if (lt === -1) {
      yield { type: "text", value: html.slice(i) };
      return;
    }
    if (lt > i) yield { type: "text", value: html.slice(i, lt) };

    // Comments: <!-- ... -->
    if (html.startsWith("<!--", lt)) {
      const end = html.indexOf("-->", lt + 4);
      if (end === -1) return;
      i = end + 3;
      continue;
    }
    // Doctype / CDATA: <!...> — drop
    if (html[lt + 1] === "!") {
      const end = html.indexOf(">", lt);
      if (end === -1) return;
      i = end + 1;
      continue;
    }

    const gt = html.indexOf(">", lt);
    if (gt === -1) return;
    yield { type: "tag", value: html.slice(lt, gt + 1) };
    i = gt + 1;
  }
}

function escapeAttr(v: string): string {
  return v.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function sanitizeTag(raw: string): string | null {
  const closing = raw.startsWith("</");
  const inner = raw.slice(closing ? 2 : 1, -1).trim();
  const nameMatch = inner.match(/^([a-zA-Z][a-zA-Z0-9]*)/);
  if (!nameMatch) return null;
  const name = nameMatch[1].toLowerCase();
  if (!ALLOWED_TAGS.has(name)) return null;
  if (closing) return `</${name}>`;

  let kept = "";
  if (TAGS_ALLOWING_STYLE.has(name)) {
    const attrsPart = inner.slice(nameMatch[0].length);
    ATTR_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = ATTR_RE.exec(attrsPart)) !== null) {
      const attrName = m[1].toLowerCase();
      const attrValue = m[2] ?? m[3] ?? m[4] ?? "";
      if (attrName === "style" && COLOR_STYLE_RE.test(attrValue)) {
        kept += ` style="${escapeAttr(attrValue)}"`;
      }
    }
  }
  return `<${name}${kept}>`;
}

export function sanitizeRichText(input: string | null | undefined): string {
  if (!input) return "";
  let out = "";
  for (const tok of tokenize(input)) {
    if (tok.type === "text") {
      out += tok.value;
    } else {
      const safe = sanitizeTag(tok.value);
      if (safe) out += safe;
    }
  }
  return out;
}
