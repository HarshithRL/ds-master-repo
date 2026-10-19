import { describe, it, expect } from "vitest";
import { sanitizeRichText } from "../sanitize-html";

describe("sanitizeRichText", () => {
  it("returns empty for null/undefined/empty", () => {
    expect(sanitizeRichText(null)).toBe("");
    expect(sanitizeRichText(undefined)).toBe("");
    expect(sanitizeRichText("")).toBe("");
  });

  it("preserves allowed formatting tags", () => {
    expect(sanitizeRichText("<b>x</b>")).toBe("<b>x</b>");
    expect(sanitizeRichText("<strong>x</strong>")).toBe("<strong>x</strong>");
    expect(sanitizeRichText("<i>x</i>")).toBe("<i>x</i>");
    expect(sanitizeRichText("<em>x</em>")).toBe("<em>x</em>");
    expect(sanitizeRichText("<u>x</u>")).toBe("<u>x</u>");
    expect(sanitizeRichText("a<br>b")).toBe("a<br>b");
    expect(sanitizeRichText("<ul><li>a</li><li>b</li></ul>")).toBe(
      "<ul><li>a</li><li>b</li></ul>",
    );
  });

  it("strips <script> tags and keeps inner text as inert", () => {
    expect(sanitizeRichText("<script>alert(1)</script>")).toBe("alert(1)");
    expect(sanitizeRichText("hi<script>alert(1)</script>bye")).toBe(
      "hialert(1)bye",
    );
  });

  it("strips <img onerror=...> entirely", () => {
    expect(sanitizeRichText("<img src=x onerror=alert(1)>")).toBe("");
  });

  it("strips event handlers from allowed tags", () => {
    expect(sanitizeRichText('<b onclick="alert(1)">x</b>')).toBe("<b>x</b>");
    expect(sanitizeRichText('<span onmouseover="alert(1)">x</span>')).toBe(
      "<span>x</span>",
    );
  });

  it("keeps style only when it is exactly a color declaration", () => {
    expect(sanitizeRichText('<span style="color: red">x</span>')).toBe(
      '<span style="color: red">x</span>',
    );
    expect(sanitizeRichText('<span style="color:#ff0000">x</span>')).toBe(
      '<span style="color:#ff0000">x</span>',
    );
  });

  it("drops style with non-color declarations", () => {
    expect(
      sanitizeRichText(
        '<span style="background:url(javascript:alert(1))">x</span>',
      ),
    ).toBe("<span>x</span>");
    expect(sanitizeRichText('<span style="color:expression(alert(1))">x</span>')).toBe(
      "<span>x</span>",
    );
    expect(
      sanitizeRichText('<span style="color:red;background:url(x)">x</span>'),
    ).toBe("<span>x</span>");
  });

  it("drops javascript: hrefs (anchors aren't allowed anyway)", () => {
    expect(sanitizeRichText('<a href="javascript:alert(1)">x</a>')).toBe("x");
  });

  it("drops <iframe>, <object>, <embed>, <svg>, <math>", () => {
    expect(sanitizeRichText('<iframe src="x"></iframe>')).toBe("");
    expect(sanitizeRichText("<object data=x></object>")).toBe("");
    expect(sanitizeRichText("<embed src=x>")).toBe("");
    expect(sanitizeRichText("<svg onload=alert(1)>")).toBe("");
    expect(sanitizeRichText("<math href=javascript:alert(1)>x</math>")).toBe("x");
  });

  it("strips HTML comments", () => {
    expect(sanitizeRichText("a<!-- evil -->b")).toBe("ab");
  });

  it("drops unterminated tags rather than leaking partial markup", () => {
    expect(sanitizeRichText("<b>x")).toBe("<b>x");
    expect(sanitizeRichText("<b unterminated")).toBe("");
  });

  it("normalises malformed nested-script tricks to text", () => {
    expect(
      sanitizeRichText("<<script>aaa</script>script>alert(1)</script>"),
    ).toBe("aaascript>alert(1)");
  });

  it("does not let attribute-injection sneak in a second tag", () => {
    expect(
      sanitizeRichText('<b "><img src=x onerror=alert(1)>">x</b>'),
    ).toBe('<b>">x</b>');
  });
});
