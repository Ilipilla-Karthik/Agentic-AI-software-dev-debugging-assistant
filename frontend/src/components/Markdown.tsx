import React from "react";

function inline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) parts.push(<strong key={k++}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) parts.push(<code key={k++}>{tok.slice(1, -1)}</code>);
    else parts.push(<em key={k++}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function renderLine(line: string, key: React.Key): React.ReactNode {
  const trimmed = line.trim();
  if (trimmed === "---" || trimmed === "***") return <hr key={key} />;
  if (trimmed.startsWith("### ")) return <h3 key={key}>{inline(trimmed.slice(4))}</h3>;
  if (trimmed.startsWith("## ")) return <h2 key={key}>{inline(trimmed.slice(3))}</h2>;
  if (trimmed.startsWith("# ")) return <h1 key={key}>{inline(trimmed.slice(2))}</h1>;
  if (trimmed.startsWith("- ") || trimmed.startsWith("* "))
    return <li key={key}>{inline(trimmed.slice(2))}</li>;
  if (/^\d+\.\s/.test(trimmed))
    return <li key={key}>{inline(trimmed.replace(/^\d+\.\s/, ""))}</li>;
  return <p key={key}>{inline(line)}</p>;
}

const LIST_RE = /^(- |\* |\d+\.\s)/;

export default function Markdown({ markdown }: { markdown: string }) {
  const lines = markdown.split("\n");
  const nodes: React.ReactNode[] = [];
  let listItems: React.ReactNode[] = [];

  const flush = (key: React.Key) => {
    if (listItems.length) {
      nodes.push(<ul key={key}>{listItems.map((li, i) => <li key={i}>{li}</li>)}</ul>);
      listItems = [];
    }
  };

  lines.forEach((raw, i) => {
    const trimmed = raw.trim();
    if (LIST_RE.test(trimmed)) {
      listItems.push(<div key={`m-${i}`}>{inline(trimmed.replace(LIST_RE, ""))}</div>);
    } else {
      flush(`ul-${i}`);
      nodes.push(renderLine(raw, i));
    }
  });
  flush("ul-end");
  return <div className="prose-sm">{nodes}</div>;
}