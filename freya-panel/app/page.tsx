import Panel from "./components/Panel";

// Single-page operations panel for the VARDAR Bank courier-rebooking voice agent.
export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-8">
      <header>
        <h1 className="text-2xl font-semibold">VARDAR Bank — Courier Rebooking Panel</h1>
        <p className="text-sm text-zinc-500">Customers and slots, live call test, and simulation runs.</p>
      </header>
      <Panel />
    </main>
  );
}
