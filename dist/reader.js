/* Sanitized rich statement rendering. Libraries and math fonts are bundled offline. */
window.readerHTML = function (text, html = false) {
  if (!text) return "";
  const math = [];
  let content = String(text);
  if (!html) {
    content = content.replace(
      /(\$\$\$[\s\S]+?\$\$\$|\$\$[\s\S]+?\$\$|\$[^\n$]+?\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\])/g,
      (match) => `CPBENCHMATHPLACEHOLDER${math.push(match) - 1}END`,
    );
    content = marked.parse(content, { breaks: true });
    content = content.replace(/CPBENCHMATHPLACEHOLDER(\d+)END/g, (_, i) =>
      String(math[i] || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;"),
    );
  }
  return DOMPurify.sanitize(content, {
    ALLOWED_TAGS: [
      "p",
      "br",
      "div",
      "span",
      "h1",
      "h2",
      "h3",
      "h4",
      "strong",
      "b",
      "em",
      "i",
      "u",
      "s",
      "sub",
      "sup",
      "pre",
      "code",
      "ul",
      "ol",
      "li",
      "table",
      "thead",
      "tbody",
      "tr",
      "th",
      "td",
      "blockquote",
      "hr",
      "a",
      "img",
    ],
    ALLOWED_ATTR: [
      "class",
      "href",
      "src",
      "alt",
      "title",
      "colspan",
      "rowspan",
    ],
    FORBID_TAGS: ["style", "script", "form", "input", "iframe", "object"],
    ALLOW_DATA_ATTR: false,
  });
};
window.enhanceReader = function (root = document) {
  root
    .querySelectorAll(".statement-text,.rich-statement,.editorial-rich")
    .forEach((el) => {
      el.classList.add("rich-prose");
      el.querySelectorAll("a").forEach((a) => {
        if (!/^https?:\/\//.test(a.href)) a.removeAttribute("href");
        a.target = "_blank";
        a.rel = "noopener noreferrer";
      });
      el.querySelectorAll("img").forEach((img) => {
        if (
          !/^https:\/\/(?:[a-z0-9-]+\.)?codeforces\.(?:com|org)\//i.test(
            img.src,
          )
        ) {
          img.replaceWith(
            document.createTextNode(img.alt || "[Hình ảnh: xem nguồn gốc]"),
          );
        } else {
          img.loading = "lazy";
          img.referrerPolicy = "no-referrer";
        }
      });
      renderMathInElement(el, {
        delimiters: [
          { left: "$$$", right: "$$$", display: false },
          { left: "$$", right: "$$", display: true },
          { left: "\\[", right: "\\]", display: true },
          { left: "\\(", right: "\\)", display: false },
          { left: "$", right: "$", display: false },
        ],
        throwOnError: false,
        trust: false,
        maxExpand: 1000,
        maxSize: 20,
        strict: "ignore",
      });
    });
};
