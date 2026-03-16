import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/shared/lib/utils";

interface MarkdownMessageProps {
  content: string;
  className?: string;
}

export function MarkdownMessage({ content, className }: MarkdownMessageProps) {
  return (
    <div className={cn("prose prose-sm dark:prose-invert max-w-none break-words", className)}>
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-1.5 last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="mb-1.5 ml-4 list-disc space-y-0.5">{children}</ul>,
        ol: ({ children }) => <ol className="mb-1.5 ml-4 list-decimal space-y-0.5">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        h1: ({ children }) => <h1 className="mb-1 text-base font-bold">{children}</h1>,
        h2: ({ children }) => <h2 className="mb-1 text-sm font-bold">{children}</h2>,
        h3: ({ children }) => <h3 className="mb-1 text-sm font-semibold">{children}</h3>,
        code: ({ children }) => (
          <code className="rounded bg-black/10 px-1 py-0.5 text-xs dark:bg-white/10">
            {children}
          </code>
        ),
        pre: ({ children }) => (
          <pre className="mb-1.5 overflow-x-auto rounded bg-black/10 p-2 text-xs dark:bg-white/10">
            {children}
          </pre>
        ),
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" className="underline opacity-80 hover:opacity-100">
            {children}
          </a>
        ),
        // ── Table components for GFM pipe-syntax tables ──
        table: ({ children }) => (
          <div className="my-2 overflow-x-auto rounded border border-border">
            <table className="min-w-full text-xs">
              {children}
            </table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-muted/50 border-b border-border">
            {children}
          </thead>
        ),
        tbody: ({ children }) => <tbody className="divide-y divide-border">{children}</tbody>,
        tr: ({ children }) => <tr className="hover:bg-muted/30 transition-colors">{children}</tr>,
        th: ({ children }) => (
          <th className="px-3 py-1.5 text-left text-xs font-semibold text-foreground">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-1.5 text-xs text-muted-foreground">
            {children}
          </td>
        ),
        // ── Horizontal rules (used as section dividers in reports) ──
        hr: () => <hr className="my-2 border-border" />,
      }}
    >
      {content}
    </ReactMarkdown>
    </div>
  );
}
