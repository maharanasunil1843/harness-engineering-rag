import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// The synthesizer returns Markdown (headings, lists, bold, code, tables).
// Tailwind v4 here has no typography plugin, so we map each element to dark-
// theme classes explicitly. Kept small and self-contained on purpose.
const components: Components = {
  h1: ({ children }) => (
    <h1 className="text-base font-semibold text-zinc-100 mt-4 mb-2 first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-sm font-semibold text-zinc-100 mt-4 mb-1.5 first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-semibold text-zinc-200 mt-3 mb-1 first:mt-0">
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p className="my-2 leading-relaxed first:mt-0 last:mb-0">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="my-2 ml-4 list-disc space-y-1 marker:text-zinc-600">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="my-2 ml-4 list-decimal space-y-1 marker:text-zinc-600">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="leading-relaxed pl-1">{children}</li>,
  strong: ({ children }) => (
    <strong className="font-semibold text-zinc-100">{children}</strong>
  ),
  em: ({ children }) => <em className="italic text-zinc-300">{children}</em>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-400 hover:text-blue-300 underline underline-offset-2"
    >
      {children}
    </a>
  ),
  code: ({ className, children }) => {
    // Block code carries a `language-*` class; inline code does not.
    const isBlock = (className ?? "").includes("language-");
    if (isBlock) {
      return (
        <code className="block font-mono text-[12px] leading-relaxed text-zinc-200">
          {children}
        </code>
      );
    }
    return (
      <code className="font-mono text-[12px] px-1 py-0.5 rounded bg-[#1E1E2E] text-zinc-200">
        {children}
      </code>
    );
  },
  pre: ({ children }) => (
    <pre className="my-2 p-3 rounded-lg bg-[#0D0D14] border border-[#1E1E2E] overflow-x-auto">
      {children}
    </pre>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 pl-3 border-l-2 border-[#1E1E2E] text-zinc-400">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-[#1E1E2E]" />,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="w-full text-xs border-collapse">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-[#1E1E2E] px-2 py-1 text-left font-medium text-zinc-300 bg-[#12121A]">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-[#1E1E2E] px-2 py-1 text-zinc-400">
      {children}
    </td>
  ),
};

export function Markdown({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {content}
    </ReactMarkdown>
  );
}
