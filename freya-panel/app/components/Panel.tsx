"use client";

import { useState } from "react";
import CallTestTab from "./CallTestTab";
import CustomersTab from "./CustomersTab";
import SimulationTab from "./SimulationTab";

const TABS = [
  { id: "customers", label: "Customers", Component: CustomersTab },
  { id: "call", label: "Call test", Component: CallTestTab },
  { id: "simulation", label: "Simulation", Component: SimulationTab },
] as const;

type TabId = (typeof TABS)[number]["id"];

// Tab switcher. Tabs stay mounted (only hidden) so a live call or a polling run survives switching.
export default function Panel() {
  const [active, setActive] = useState<TabId>("customers");

  return (
    <div className="flex flex-col gap-6">
      <nav className="flex gap-1 border-b border-zinc-200">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setActive(t.id)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
              active === t.id ? "border-zinc-900 text-zinc-900" : "border-transparent text-zinc-500 hover:text-zinc-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>
      {TABS.map(({ id, Component }) => (
        <div key={id} hidden={active !== id}>
          <Component />
        </div>
      ))}
    </div>
  );
}
