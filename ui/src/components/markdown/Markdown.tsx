/** GFM markdown renderer used for workflow cards and chat messages. */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";

export function Markdown({ children, stripInlineCode = false }: { children: string; stripInlineCode?: boolean }) {
  const components = stripInlineCode
    ? {
        code: ({ inline, children, ...props }: { inline?: boolean; children?: React.ReactNode }) =>
          inline ? <span>{children}</span> : <code {...props}>{children}</code>,
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
