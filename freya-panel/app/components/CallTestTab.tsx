"use client";

import { useEffect, useRef, useState } from "react";
import type { BotOutputData, PipecatClient, TransportState, UserInputData } from "@pipecat-ai/client-js";
import { errorText, fetchJson } from "@/lib/api";
import type { Customer } from "@/lib/types";
import { Button, ErrorNote } from "./ui";

const BOT_URL = process.env.NEXT_PUBLIC_BOT_URL ?? "http://localhost:7860";

interface Line {
  key: string;
  role: "customer" | "agent";
  text: string;
}

// Place a live WebRTC call to the voice bot for one customer and show the conversation.
export default function CallTestTab() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerId, setCustomerId] = useState<number | null>(null);
  const [state, setState] = useState<TransportState>("disconnected");
  const [lines, setLines] = useState<Line[]>([]);
  const [error, setError] = useState<string | null>(null);
  const clientRef = useRef<PipecatClient | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  // Fill the customer dropdown from the slot service; preselect the first customer.
  useEffect(() => {
    fetchJson<Customer[]>("/api/slot/customers")
      .then((list) => {
        setCustomers(list);
        setCustomerId((current) => current ?? list[0]?.id ?? null);
      })
      .catch((err) => setError(errorText(err)));
  }, []);

  // Hang up if the user leaves the tab mid-call, so the mic and peer connection are released.
  useEffect(() => () => void clientRef.current?.disconnect(), []);

  // Customer speech: keep only final transcriptions, one line each.
  function onUserInput(data: UserInputData) {
    if (!data.final || data.input_type !== "transcription") return;
    setLines((prev) => [...prev, { key: `u-${prev.length}-${data.timestamp}`, role: "customer", text: data.text }]);
  }

  // Bot speech: skip word-level updates; a later update of the same segment replaces its line.
  function onBotOutput(data: BotOutputData) {
    if (data.output_type === "word") return;
    const key = data.segment_id !== undefined ? `b-${data.segment_id}` : `b-${Date.now()}`;
    setLines((prev) =>
      prev.some((l) => l.key === key)
        ? prev.map((l) => (l.key === key ? { ...l, text: data.text } : l))
        : [...prev, { key, role: "agent", text: data.text }],
    );
  }

  // Start the bot via the runner's /start (transport + customer_id) and connect over SmallWebRTC.
  // The SDK is imported on demand because it needs browser APIs (WebRTC, mic).
  async function startCall() {
    if (customerId === null) return;
    setError(null);
    setLines([]);
    const [{ PipecatClient }, { SmallWebRTCTransport }] = await Promise.all([
      import("@pipecat-ai/client-js"),
      import("@pipecat-ai/small-webrtc-transport"),
    ]);
    const client = new PipecatClient({
      transport: new SmallWebRTCTransport(),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTransportStateChanged: setState,
        // Route the bot's remote audio track into the hidden <audio> element.
        onTrackStarted: (track, participant) => {
          if (participant?.local || track.kind !== "audio" || !audioRef.current) return;
          audioRef.current.srcObject = new MediaStream([track]);
        },
        onUserInput,
        onBotOutput,
        onError: (message) => setError(`Bot error: ${JSON.stringify(message.data)}`),
        onDisconnected: () => {
          clientRef.current = null;
        },
      },
    });
    clientRef.current = client;
    try {
      await client.startBotAndConnect({
        endpoint: `${BOT_URL}/start`,
        requestData: { transport: "webrtc", body: { customer_id: customerId } },
      });
    } catch (err) {
      setError(`Could not connect to bot at ${BOT_URL}: ${errorText(err)}`);
      await client.disconnect().catch(() => undefined);
      clientRef.current = null;
    }
  }

  async function hangUp() {
    await clientRef.current?.disconnect();
    clientRef.current = null;
  }

  const inCall = state !== "disconnected" && state !== "error";

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <select
          className="rounded border border-zinc-300 px-2 py-1.5 text-sm"
          value={customerId ?? ""}
          onChange={(e) => setCustomerId(Number(e.target.value))}
          disabled={inCall}
        >
          {customers.map((c) => (
            <option key={c.id} value={c.id}>
              #{c.id} {c.full_name} ({c.district})
            </option>
          ))}
        </select>
        <Button primary onClick={() => void startCall()} disabled={inCall || customerId === null}>
          Call
        </Button>
        <Button onClick={() => void hangUp()} disabled={!inCall}>
          Hang up
        </Button>
        <span className="text-sm text-zinc-600">
          Status: <strong>{state}</strong>
        </span>
      </div>
      <p className="text-xs text-zinc-500">Bot: {BOT_URL} — allow microphone access when asked; the bot speaks first.</p>
      {error && <ErrorNote message={error} />}
      <audio ref={audioRef} autoPlay />
      <section className="flex flex-col gap-2">
        <h2 className="font-semibold">Transcript</h2>
        {lines.length === 0 && <p className="text-sm text-zinc-500">Nothing yet.</p>}
        {lines.map((l) => (
          <p key={l.key} className="text-sm">
            <span className={l.role === "agent" ? "font-medium text-blue-700" : "font-medium text-zinc-700"}>
              {l.role === "agent" ? "Agent" : "Customer"}:
            </span>{" "}
            {l.text}
          </p>
        ))}
      </section>
    </div>
  );
}
