import type { ReactNode } from "react";
import { outcomeColor } from "@/lib/format";

// Small shared building blocks so the three tabs look the same.

// Inline red message shown when a backend call fails, instead of crashing the page.
export function ErrorNote({ message }: { message: string }) {
  return <p className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">{message}</p>;
}

// Colored pill for a call outcome; a dash when there is none yet.
export function OutcomeBadge({ outcome }: { outcome: string | null }) {
  if (!outcome) return <span className="text-zinc-400">—</span>;
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${outcomeColor(outcome)}`}>{outcome}</span>;
}

// Plain bordered table with a header row; rows are passed as children.
export function Table({ headers, children }: { headers: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded border border-zinc-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-zinc-100 text-xs uppercase text-zinc-600">
          <tr>
            {headers.map((h) => (
              <th key={h} className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200">{children}</tbody>
      </table>
    </div>
  );
}

// Standard table cell padding.
export function Td({ children }: { children: ReactNode }) {
  return <td className="px-3 py-2 align-top">{children}</td>;
}

// Neutral button used across tabs; `primary` for the main action.
export function Button({
  children,
  onClick,
  disabled,
  primary,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  const color = primary ? "bg-zinc-900 text-white hover:bg-zinc-700" : "border border-zinc-300 bg-white hover:bg-zinc-100";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-40 ${color}`}
    >
      {children}
    </button>
  );
}
