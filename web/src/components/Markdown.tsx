import type { ReactNode } from "react";

/** 极简 Markdown 渲染：只支持后端报告用到的语法（# 标题、> 引用、- / 1. 列表、**粗体**、[链接](url)）。不用 innerHTML。 */
export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = blocks.length;
    if (!line.trim()) { i++; continue; }
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) {
      const cls = h[1].length === 1 ? "text-xl font-bold" : h[1].length === 2 ? "mt-6 border-b pb-1 text-base font-semibold" : "mt-4 text-sm font-semibold text-indigo-700";
      blocks.push(<div key={key} className={cls}>{inline(h[2])}</div>);
      i++;
      continue;
    }
    if (/^(- |\d+\. )/.test(line)) {
      const ordered = /^\d+\. /.test(line);
      const items: string[] = [];
      while (i < lines.length && (ordered ? /^\d+\. /.test(lines[i]) : lines[i].startsWith("- "))) {
        items.push(lines[i].replace(/^(- |\d+\. )/, ""));
        i++;
      }
      const Tag = ordered ? "ol" : "ul";
      blocks.push(<Tag key={key} className={ordered ? "list-decimal space-y-1 pl-5" : "list-disc space-y-1 pl-5"}>{items.map((x, j) => <li key={j}>{inline(x)}</li>)}</Tag>);
      continue;
    }
    if (line.startsWith("> ")) {
      blocks.push(<p key={key} className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-muted-foreground">{inline(line.slice(2))}</p>);
      i++;
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,3}\s|- |\d+\. |> )/.test(lines[i])) {
      para.push(lines[i]);
      i++;
    }
    blocks.push(<p key={key} className="whitespace-pre-wrap">{inline(para.join("\n"))}</p>);
  }
  return <div className="space-y-2 text-sm leading-relaxed">{blocks}</div>;
}

function inline(s: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g;
  let last = 0;
  for (let m = re.exec(s); m; m = re.exec(s)) {
    if (m.index > last) out.push(s.slice(last, m.index));
    out.push(m[1] != null
      ? <b key={m.index} className="font-medium">{m[1]}</b>
      : <a key={m.index} href={m[3]} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{m[2]}</a>);
    last = m.index + m[0].length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out;
}
