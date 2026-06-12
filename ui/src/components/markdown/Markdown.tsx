/** GFM markdown renderer used for workflow cards and chat messages. */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";

export function Markdown({ children, stripInlineCode = false }: { children: string; stripInlineCode?: boolean }) {
  const components = stripInlineCode
    ? {
        code: ({ className, children, ...props }: { className?: string; children?: React.ReactNode }) =>
          className ? <code className={className} {...props}>{children}</code> : <span>{children}</span>,
      }
    : undefined;

  return (
    <div className="prose-flowcept">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
