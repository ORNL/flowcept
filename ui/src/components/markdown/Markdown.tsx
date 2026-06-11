/** GFM markdown renderer used for provenance cards and chat messages. */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";

export function Markdown({ children }: { children: string }) {
  return (
    <div className="prose-flowcept">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{children}</ReactMarkdown>
    </div>
  );
}
