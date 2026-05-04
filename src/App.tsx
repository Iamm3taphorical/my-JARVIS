import { FormEvent, useEffect, useRef, useState } from "react"
import {
  Activity,
  Bot,
  CheckCircle2,
  Code2,
  ExternalLink,
  Mic,
  Play,
  Radio,
  Search,
  Send,
  Sparkles,
  Terminal,
  User,
  Volume2,
} from "lucide-react"

import { ShaderAnimation } from "@/components/ui/shader-animation"
import { cn } from "@/lib/utils"

type Message = {
  role: "user" | "assistant"
  text: string
}

type ServerEvent = {
  type: "snapshot" | "status" | "transcript" | "assistant"
  state?: string
  message?: string
  text?: string
  status?: string
  transcript?: string
  assistant?: string
  history?: Message[]
}

const quickActions = [
  { icon: Search, label: "Search web", command: "search the web for Bengali accent speech recognition" },
  { icon: Play, label: "Play music", command: "play lofi music on youtube" },
  { icon: Code2, label: "Open config", command: "open config json in vs code" },
  { icon: Terminal, label: "System stats", command: "system stats" },
]

function statusCopy(status: string) {
  if (status === "waiting") return "Wake word armed"
  if (status === "listening") return "Listening now"
  if (status === "thinking") return "Executing"
  if (status === "ready") return "Ready"
  if (status === "online") return "Online"
  if (status === "no_speech") return "No speech"
  if (status === "checking") return "Checking"
  return status || "Starting"
}

export default function App() {
  const [status, setStatus] = useState("starting")
  const [message, setMessage] = useState("Connecting to JARVIS")
  const [transcript, setTranscript] = useState("")
  const [assistantText, setAssistantText] = useState("")
  const [history, setHistory] = useState<Message[]>([])
  const [command, setCommand] = useState("")
  const [connected, setConnected] = useState(false)
  const [busy, setBusy] = useState(false)
  const [voiceLoopEnabled, setVoiceLoopEnabled] = useState(true)
  const historyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch("/api/status")
      .then((response) => response.json())
      .then((data) => {
        setStatus(data.status ?? "ready")
        setMessage(data.message ?? "JARVIS is ready")
        setTranscript(data.transcript ?? "")
        setAssistantText(data.assistant ?? "")
        setHistory(data.history ?? [])
        setVoiceLoopEnabled(Boolean(data.voiceLoopEnabled))
      })
      .catch(() => setMessage("Start the Python GUI server on port 8765"))

    const source = new EventSource("/api/events")
    source.onopen = () => setConnected(true)
    source.onerror = () => setConnected(false)
    source.onmessage = (event) => {
      const payload = JSON.parse(event.data) as ServerEvent
      if (payload.type === "snapshot") {
        setStatus(payload.status ?? "ready")
        setMessage(payload.message ?? "JARVIS is ready")
        setTranscript(payload.transcript ?? "")
        setAssistantText(payload.assistant ?? "")
        setHistory(payload.history ?? [])
        return
      }
      if (payload.type === "status") {
        setStatus(payload.state ?? "ready")
        setMessage(payload.message ?? "")
      }
      if (payload.type === "transcript" && payload.text) {
        setTranscript(payload.text)
        setHistory((items) => [...items.slice(-29), { role: "user", text: payload.text! }])
      }
      if (payload.type === "assistant" && payload.text) {
        setAssistantText(payload.text)
        setHistory((items) => [...items.slice(-29), { role: "assistant", text: payload.text! }])
      }
    }
    return () => source.close()
  }, [])

  useEffect(() => {
    historyRef.current?.scrollTo({ top: historyRef.current.scrollHeight, behavior: "smooth" })
  }, [history])

  async function sendCommand(text: string) {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    setBusy(true)
    setCommand("")
    try {
      await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: trimmed }),
      })
    } finally {
      setBusy(false)
    }
  }

  async function captureVoice() {
    if (busy) return
    setBusy(true)
    try {
      await fetch("/api/listen-once", { method: "POST" })
    } finally {
      setBusy(false)
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void sendCommand(command)
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#04080d] text-white">
      <div className="fixed inset-0 opacity-70">
        <ShaderAnimation />
      </div>
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_20%_10%,rgba(65,173,255,0.22),transparent_34%),linear-gradient(135deg,rgba(0,0,0,0.25),rgba(0,0,0,0.86))]" />
      <div className="fixed left-0 right-0 top-0 h-px overflow-hidden bg-white/10">
        <div className="h-px w-1/2 animate-scan bg-gradient-to-r from-transparent via-cyan-300 to-transparent" />
      </div>

      <section className="relative z-10 mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 rounded-[2rem] border border-white/10 bg-black/35 p-4 shadow-glass backdrop-blur-xl sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <div className="grid size-14 place-items-center rounded-2xl border border-cyan-200/30 bg-cyan-300/10 shadow-signal">
              <Bot className="size-7 text-cyan-100" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.42em] text-cyan-100/70">Local Voice Console</p>
              <h1 className="mt-1 text-3xl font-black tracking-[-0.06em] sm:text-5xl">JARVIS</h1>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill active={connected} label={connected ? "GUI linked" : "Disconnected"} />
            <StatusPill active={voiceLoopEnabled} label={voiceLoopEnabled ? "Wake loop active" : "Manual mode"} />
            <StatusPill active={status === "listening"} label={statusCopy(status)} />
          </div>
        </header>

        <div className="grid flex-1 gap-5 lg:grid-cols-[1.05fr_0.95fr]">
          <section className="flex min-h-[520px] flex-col justify-between overflow-hidden rounded-[2rem] border border-white/10 bg-slate-950/55 p-5 shadow-glass backdrop-blur-xl sm:p-7">
            <div className="space-y-8">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.32em] text-cyan-100/70">
                    <Radio className="size-4" />
                    {statusCopy(status)}
                  </p>
                  <p className="mt-2 max-w-xl text-sm text-slate-300">{message}</p>
                </div>
                <div className={cn("size-4 rounded-full", status === "listening" ? "animate-pulse bg-emerald-300" : "bg-cyan-200/70")} />
              </div>

              <div className="rounded-[1.75rem] border border-white/10 bg-black/35 p-5">
                <p className="mb-3 flex items-center gap-2 text-sm uppercase tracking-[0.28em] text-slate-400">
                  <User className="size-4" />
                  What I heard
                </p>
                <p className="min-h-24 text-3xl font-black leading-tight tracking-[-0.06em] text-white sm:text-5xl">
                  {transcript || "Say “Hey Jarvis” and speak your command."}
                </p>
              </div>

              <div className="rounded-[1.75rem] border border-cyan-200/15 bg-cyan-200/10 p-5">
                <p className="mb-3 flex items-center gap-2 text-sm uppercase tracking-[0.28em] text-cyan-100/70">
                  <Volume2 className="size-4" />
                  Response
                </p>
                <p className="min-h-20 text-xl font-semibold leading-relaxed text-cyan-50 sm:text-2xl">
                  {assistantText || "Responses and task completion prompts will appear here."}
                </p>
              </div>
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-[auto_1fr]">
              <button
                type="button"
                onClick={captureVoice}
                disabled={busy}
                className="group inline-flex items-center justify-center gap-3 rounded-2xl border border-emerald-200/30 bg-emerald-300 px-6 py-4 text-base font-black tracking-[-0.03em] text-slate-950 transition hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Mic className="size-5 transition group-hover:scale-110" />
                Capture once
              </button>
              <form onSubmit={onSubmit} className="flex gap-2 rounded-2xl border border-white/10 bg-black/40 p-2">
                <input
                  value={command}
                  onChange={(event) => setCommand(event.target.value)}
                  placeholder="Type a command: search web for ..., open config json in vs code"
                  className="min-w-0 flex-1 bg-transparent px-3 text-sm font-semibold text-white outline-none placeholder:text-slate-500"
                />
                <button
                  type="submit"
                  disabled={busy || !command.trim()}
                  className="grid size-11 place-items-center rounded-xl bg-cyan-300 text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Send className="size-5" />
                </button>
              </form>
            </div>
          </section>

          <aside className="grid gap-5">
            <div className="rounded-[2rem] border border-white/10 bg-black/40 p-5 shadow-glass backdrop-blur-xl">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-lg font-black tracking-[-0.04em]">
                  <Sparkles className="size-5 text-amber-200" />
                  Quick Actions
                </h2>
                <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">voice or click</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
                {quickActions.map((action) => (
                  <button
                    key={action.label}
                    type="button"
                    onClick={() => sendCommand(action.command)}
                    className="group rounded-2xl border border-white/10 bg-white/[0.06] p-4 text-left transition hover:-translate-y-0.5 hover:border-cyan-200/40 hover:bg-cyan-200/10"
                  >
                    <action.icon className="mb-4 size-5 text-cyan-100" />
                    <p className="font-black tracking-[-0.04em]">{action.label}</p>
                    <p className="mt-2 text-xs leading-relaxed text-slate-400">{action.command}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="min-h-[320px] rounded-[2rem] border border-white/10 bg-slate-950/60 p-5 shadow-glass backdrop-blur-xl">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-lg font-black tracking-[-0.04em]">
                  <Activity className="size-5 text-emerald-200" />
                  Session
                </h2>
                <CheckCircle2 className="size-5 text-emerald-200" />
              </div>
              <div ref={historyRef} className="max-h-[430px] space-y-3 overflow-y-auto pr-1">
                {history.length === 0 ? (
                  <p className="rounded-2xl border border-dashed border-white/10 p-4 text-sm text-slate-400">
                    Live transcripts and assistant responses will stream here.
                  </p>
                ) : (
                  history.map((item, index) => (
                    <div
                      key={`${item.role}-${index}-${item.text}`}
                      className={cn(
                        "animate-rise rounded-2xl border p-4",
                        item.role === "user"
                          ? "ml-8 border-cyan-200/20 bg-cyan-200/10"
                          : "mr-8 border-emerald-200/20 bg-emerald-200/10",
                      )}
                    >
                      <p className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.24em] text-slate-400">
                        {item.role === "user" ? <User className="size-3" /> : <Bot className="size-3" />}
                        {item.role === "user" ? "You" : "JARVIS"}
                      </p>
                      <p className="text-sm leading-relaxed text-slate-100">{item.text}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </aside>
        </div>

        <footer className="flex flex-col gap-2 rounded-[1.5rem] border border-white/10 bg-black/30 p-4 text-xs text-slate-400 backdrop-blur-xl sm:flex-row sm:items-center sm:justify-between">
          <span>Try: “open word editor and write buy milk”, “search web for fastest whisper model”, “play lofi music on youtube”.</span>
          <a className="inline-flex items-center gap-1 text-cyan-100 hover:text-white" href="/api/status" target="_blank" rel="noreferrer">
            API status <ExternalLink className="size-3" />
          </a>
        </footer>
      </section>
    </main>
  )
}

function StatusPill({ active, label }: { active: boolean; label: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-bold uppercase tracking-[0.18em]",
        active ? "border-cyan-200/30 bg-cyan-200/10 text-cyan-50" : "border-white/10 bg-white/5 text-slate-400",
      )}
    >
      <span className={cn("size-2 rounded-full", active ? "bg-cyan-200" : "bg-slate-500")} />
      {label}
    </span>
  )
}
