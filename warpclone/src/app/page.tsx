"use client";

import { useState } from "react";

function MontyLogo({ className }: { className?: string }) {
  return (
    <a href="#" className={`inline-flex items-center ${className ?? ""}`}>
      <img src="/monty-logo.png" alt="Monty" className="w-8 h-8 object-cover" style={{ transform: "scale(1.6)" }} />
    </a>
  );
}

function ChevronIcon() {
  return (
    <svg className="w-4 h-4 opacity-50 mt-0.5" viewBox="0 0 16 16" fill="currentColor">
      <path fillRule="evenodd" d="M4.22 6.22a.75.75 0 0 1 1.06 0L8 8.94l2.72-2.72a.75.75 0 1 1 1.06 1.06l-3.25 3.25a.75.75 0 0 1-1.06 0L4.22 7.28a.75.75 0 0 1 0-1.06Z" clipRule="evenodd" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="currentColor">
      <path fillRule="evenodd" d="M2 8a.75.75 0 0 1 .75-.75h8.69L8.22 4.03a.75.75 0 0 1 1.06-1.06l4.5 4.5a.75.75 0 0 1 0 1.06l-4.5 4.5a.75.75 0 0 1-1.06-1.06l3.22-3.22H2.75A.75.75 0 0 1 2 8Z" clipRule="evenodd" />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
      <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 256 256" fill="currentColor">
      <path d="M184,64H40a8,8,0,0,0-8,8V216a8,8,0,0,0,8,8H184a8,8,0,0,0,8-8V72A8,8,0,0,0,184,64Zm-8,144H48V80H176ZM224,40V184a8,8,0,0,1-16,0V48H72a8,8,0,0,1,0-16H216A8,8,0,0,1,224,40Z" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg className="w-6 h-6 translate-x-[1px]" viewBox="0 0 256 256" fill="currentColor">
      <path d="M240,128a15.74,15.74,0,0,1-7.6,13.51L88.32,229.65a16,16,0,0,1-16.2.3A15.86,15.86,0,0,1,64,216.13V39.87a15.86,15.86,0,0,1,8.12-13.82,16,16,0,0,1,16.2.3L232.4,114.49A15.74,15.74,0,0,1,240,128Z" />
    </svg>
  );
}

function ChartIcon() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 256 256" fill="currentColor">
      <path d="M232,208a8,8,0,0,1-8,8H32a8,8,0,0,1-8-8V48a8,8,0,0,1,16,0v94.37L90.73,98a8,8,0,0,1,10.07-.38l58.81,44.11L218.73,90a8,8,0,1,1,10.54,12l-64,56a8,8,0,0,1-10.07.38L96.39,114.29,40,163.63V200H224A8,8,0,0,1,232,208Z" />
    </svg>
  );
}

function DollarIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 256 256" fill="currentColor">
      <path d="M152,120H136V56h8a32,32,0,0,1,32,32,8,8,0,0,0,16,0,48.05,48.05,0,0,0-48-48h-8V24a8,8,0,0,0-16,0V40H112a48,48,0,0,0,0,96h8v64H104a32,32,0,0,1-32-32,8,8,0,0,0-16,0,48.05,48.05,0,0,0,48,48h16v16a8,8,0,0,0,16,0V216h16a48,48,0,0,0,0-96Zm-40,0a32,32,0,0,1,0-64h8v64Zm40,80H136V136h16a32,32,0,0,1,0,64Z" />
    </svg>
  );
}

function TerminalIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 256 256" fill="currentColor">
      <path d="M117.31,134l-72,64a8,8,0,1,1-10.63-12L100,128,34.69,70A8,8,0,1,1,45.32,58l72,64A8,8,0,0,1,117.31,134ZM216,184H120a8,8,0,0,0,0,16h96a8,8,0,0,0,0-16Z" />
    </svg>
  );
}

function CodeIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 256 256" fill="currentColor">
      <path d="M69.12,94.15,28.5,128l40.62,33.85a8,8,0,1,1-10.24,12.29l-48-40a8,8,0,0,1,0-12.29l48-40a8,8,0,0,1,10.24,12.3Zm176,27.7-48-40a8,8,0,1,0-10.24,12.3L227.5,128l-40.62,33.85a8,8,0,1,0,10.24,12.29l48-40a8,8,0,0,0,0-12.29ZM162.73,32.48a8,8,0,0,0-10.25,4.79l-64,176a8,8,0,0,0,4.79,10.26A8.14,8.14,0,0,0,96,224a8,8,0,0,0,7.52-5.27l64-176A8,8,0,0,0,162.73,32.48Z" />
    </svg>
  );
}

const testimonials = [
  {
    company: "Anthropic",
    quote: "Monty has turned idle terminal cycles into real revenue for developers. It's the monetization layer AI coding tools have been missing.",
    name: "Alex Chen",
    title: "Engineering Lead at Anthropic",
  },
  {
    company: "Vercel",
    quote: "We love how Monty lets developers earn passively while they code. It's non-intrusive, developer-first, and just works.",
    name: "Sarah Kim",
    title: "Head of Developer Experience at Vercel",
  },
  {
    company: "Stripe",
    quote: "Monty's approach to developer monetization is brilliant. A single sponsor line during AI thinking time, and developers keep 90%. It's a no-brainer.",
    name: "Jordan Liu",
    title: "Product at Stripe",
  },
];

export default function Home() {
  const [activeTestimonial, setActiveTestimonial] = useState(0);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText("pip install monty-ads");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <>
      {/* ═══════════ NAVBAR ═══════════ */}
      <header className="sticky top-0 z-50 bg-white/70 backdrop-blur-xl border-b border-black/[0.06]">
        <nav className="mx-auto flex h-[5.25rem] max-w-[1280px] items-center gap-4 px-6 lg:px-10">
          <div className="flex flex-1 items-center gap-12">
            <MontyLogo />
            <div className="hidden items-center gap-1 lg:flex">
              {["Products", "Solutions", "Resources", "Enterprise"].map((item) => (
                <button
                  key={item}
                  className="inline-flex cursor-default items-center gap-1 rounded-lg px-2.5 py-1 text-sm font-medium text-[#111] hover:bg-black/5"
                >
                  {item}
                  <ChevronIcon />
                </button>
              ))}
              <a href="#" className="rounded-lg px-2.5 py-1 text-sm font-medium text-[#111] hover:bg-black/5">
                Pricing
              </a>
            </div>
          </div>
          <div className="flex flex-1 items-center justify-end gap-5">
            <a href="#" className="hidden items-center gap-2 rounded-lg px-3 text-sm font-medium text-[#111] hover:bg-black/5 lg:inline-flex h-[35px]">
              <GitHubIcon />
              <span className="tabular-nums">2.4k</span>
            </a>
            <a href="#" className="hidden text-sm font-medium text-[#111] hover:bg-black/5 rounded-lg px-3 h-9 items-center lg:inline-flex">
              Contact sales
            </a>
            <a
              href="#"
              className="inline-flex shrink-0 items-center gap-1.5 text-sm font-medium hover:opacity-85 transition-opacity h-[35px] bg-[#111] text-white rounded-[10px] px-3"
            >
              Install
              <TerminalIcon />
            </a>
          </div>
        </nav>
      </header>

      <main>
        {/* ═══════════ HERO ═══════════ */}
        <section className="py-16">
          <div className="mx-auto w-full max-w-[1280px] px-6 lg:px-10 flex flex-col gap-16">
            <div className="flex flex-col items-center gap-6 text-center">
              <h1
                className="text-[#111] max-w-5xl hero-reveal"
                style={{
                  fontSize: "clamp(3rem, 6vw, 5.5rem)",
                  lineHeight: 1.1,
                  fontWeight: 500,
                  letterSpacing: "-0.02em",
                  textWrap: "balance",
                }}
              >
                Get paid to code with AI
              </h1>
              <p className="text-[#666] max-w-md text-lg leading-relaxed hero-reveal-delay-1">
                One install. Zero disruption. Earn while your AI thinks.
              </p>
              <div className="flex w-full flex-col items-center gap-4 sm:w-auto sm:flex-row hero-reveal-delay-2">
                <div className="flex items-center rounded-[10px] bg-[#f5f5f5] px-4 py-2 w-full sm:w-auto">
                  <div className="flex items-center gap-2 font-mono text-sm text-[#666]">
                    <span className="opacity-50 select-none">$</span>
                    <span>pip install monty-ads</span>
                    <button
                      onClick={handleCopy}
                      className="group relative flex size-9 items-center justify-center rounded-full hover:bg-black/10"
                    >
                      {copied ? (
                        <svg className="w-4 h-4" viewBox="0 0 256 256" fill="currentColor">
                          <path d="M229.66,77.66l-128,128a8,8,0,0,1-11.32,0l-56-56a8,8,0,0,1,11.32-11.32L96,188.69,218.34,66.34a8,8,0,0,1,11.32,11.32Z" />
                        </svg>
                      ) : (
                        <CopyIcon />
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Hero Screenshot with background image */}
            <div className="relative rounded-2xl overflow-hidden">
              <img src="/hero-bg.png" alt="" className="absolute inset-0 w-full h-full object-cover" />
              <div className="relative z-10 flex items-center justify-center p-6 sm:p-12 lg:p-16">
                <div className="flex w-full max-w-4xl rounded-xl overflow-hidden shadow-2xl" style={{ aspectRatio: "16/10" }}>
                  <div className="w-[30%] bg-[#111] p-3 sm:p-4 flex flex-col gap-1.5 border-r border-[#222]">
                    <div className="flex gap-1.5 mb-2">
                      <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f56]" />
                      <div className="w-2.5 h-2.5 rounded-full bg-[#ffbd2e]" />
                      <div className="w-2.5 h-2.5 rounded-full bg-[#27c93f]" />
                    </div>
                    <div className="bg-[#1a1a1a] rounded px-2.5 py-2 text-[10px] sm:text-xs text-[#ccc] font-mono">monty serve</div>
                    <div className="px-2.5 py-2 text-[10px] sm:text-xs text-[#666] font-mono">Ad dashboard</div>
                    <div className="px-2.5 py-2 text-[10px] sm:text-xs text-[#666] font-mono">earnings.py</div>
                    <div className="px-2.5 py-2 text-[10px] sm:text-xs text-[#666] font-mono">Configure sponsors</div>
                    <div className="px-2.5 py-2 text-[10px] sm:text-xs text-[#666] font-mono hidden sm:block">feed.py</div>
                    <div className="px-2.5 py-2 text-[10px] sm:text-xs text-[#666] font-mono hidden sm:block">Settings</div>
                  </div>
                  <div className="w-[40%] bg-[#0d1117] p-3 sm:p-4 font-mono text-[8px] sm:text-[11px] text-[#8b949e] overflow-hidden">
                    <div className="text-[#58a6ff] mb-1.5">~/Projects/myapp/</div>
                    <div className="text-[#c9d1d9] font-bold">claude &quot;add auth flow&quot;</div>
                    <div className="mt-1 text-[#8b949e]">Thinking...</div>
                    <div className="mt-2 px-2 py-1 bg-[#f5731a]/10 border-l-2 border-[#f5731a] text-[#ff9a3c] text-[8px] sm:text-[10px]">
                      Sponsored: Try Vercel — deploy in seconds →
                    </div>
                    <div className="mt-2 text-[#3fb950]">✓ Created src/auth/login.tsx</div>
                    <div className="text-[#3fb950]">✓ Created src/auth/signup.tsx</div>
                    <div className="text-[#3fb950]">✓ Updated src/app/layout.tsx</div>
                    <div className="mt-2 text-[#8b949e]">You earned <span className="text-[#f5731a] font-bold">$0.12</span> from this session</div>
                  </div>
                  <div className="w-[30%] bg-[#0d1117] p-3 sm:p-4 font-mono text-[8px] sm:text-[10px] text-[#8b949e] border-l border-[#21262d] overflow-hidden">
                    <div className="text-[9px] text-[#58a6ff] mb-2 font-semibold">Earnings Dashboard</div>
                    <div className="flex justify-between"><span>Today</span><span className="text-[#f5731a]">$4.82</span></div>
                    <div className="flex justify-between mt-1"><span>This week</span><span className="text-[#f5731a]">$28.50</span></div>
                    <div className="flex justify-between mt-1"><span>This month</span><span className="text-[#f5731a]">$142.30</span></div>
                    <div className="mt-3 border-t border-[#21262d] pt-2">
                      <div className="text-[#3fb950] text-[8px]">● Active</div>
                      <div className="text-[#8b949e] mt-0.5">3 sponsors</div>
                      <div className="text-[#8b949e] mt-0.5">90% rev share</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ═══════════ PARTNERS ═══════════ */}
        <section className="py-20">
          <div className="mx-auto w-full max-w-[1280px] px-6 lg:px-10">
            <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-[2fr_3fr] lg:gap-16">
              <div className="flex min-w-0 flex-col gap-6">
                <h2 className="text-[#111]" style={{ fontSize: "clamp(1.75rem, 3.5vw, 2.25rem)", lineHeight: 1.15, fontWeight: 600, letterSpacing: "-0.01em" }}>
                  Trusted by developers everywhere
                </h2>
                <p className="text-[#666] text-base leading-relaxed">
                  Thousands of developers earn passive income with Monty while coding with their favorite AI tools
                </p>
                <div className="pt-4">
                  <div className="relative overflow-hidden pb-10" style={{ maskImage: "linear-gradient(to right, transparent, black 10%, black 90%, transparent)", WebkitMaskImage: "linear-gradient(to right, transparent, black 10%, black 90%, transparent)" }}>
                    <div className="flex w-max" style={{ animation: "scroll-left 40s linear infinite" }}>
                      {[0, 1, 2].map((set) => (
                        <div key={set} className="flex shrink-0 items-center gap-12 pr-12" aria-hidden={set > 0}>
                          {["Claude Code", "Cursor", "Copilot", "Windsurf"].map((name) => (
                            <span key={name} className="text-lg font-semibold text-[#111] opacity-30 grayscale whitespace-nowrap hover:opacity-60 transition-opacity">
                              {name}
                            </span>
                          ))}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex flex-col gap-2">
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {[
                    { badge: "Integration", name: "Claude Code", bg: "linear-gradient(135deg, #e8eaf6, #c5cae9)" },
                    { badge: "Integration", name: "Cursor", bg: "linear-gradient(135deg, #e3f2fd, #bbdefb)" },
                    { badge: "Integration", name: "Copilot", bg: "linear-gradient(135deg, #e0f2f1, #b2dfdb)" },
                  ].map((card) => (
                    <div key={card.name} className="relative flex h-full min-h-[140px] flex-col items-center justify-center gap-4 overflow-hidden rounded-2xl p-6">
                      <div className="absolute inset-0" style={{ background: card.bg }} />
                      <span className="absolute top-3 left-3 z-10 rounded-full px-2.5 py-1 text-[10px] font-medium tracking-wide bg-black/10 text-[#333] backdrop-blur-sm">
                        {card.badge}
                      </span>
                      <span className="relative z-10 text-lg font-semibold text-[#111]">{card.name}</span>
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { badge: "Integration", name: "Windsurf", bg: "linear-gradient(135deg, #fce4ec, #f8bbd0)" },
                    { badge: "Coming Soon", name: "VS Code", bg: "linear-gradient(135deg, #fff3e0, #ffe0b2)" },
                  ].map((card) => (
                    <div key={card.name} className="relative flex h-full min-h-[140px] flex-col items-center justify-center gap-4 overflow-hidden rounded-2xl p-6">
                      <div className="absolute inset-0" style={{ background: card.bg }} />
                      <span className="absolute top-3 left-3 z-10 rounded-full px-2.5 py-1 text-[10px] font-medium tracking-wide bg-black/10 text-[#333] backdrop-blur-sm">
                        {card.badge}
                      </span>
                      <span className="relative z-10 text-lg font-semibold text-[#111]">{card.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ═══════════ WHY MONTY ═══════════ */}
        <section className="py-20" id="why-monty">
          <div className="mx-auto w-full max-w-[1280px] px-6 lg:px-10 flex flex-col gap-14">
            <div className="max-w-3xl">
              <div className="mb-5 text-xs font-medium tracking-[0.28em] text-[#999] uppercase">Why Monty</div>
              <h2 className="text-[#111]" style={{ fontSize: "clamp(1.75rem, 3.5vw, 2.25rem)", lineHeight: 1.15, fontWeight: 600, letterSpacing: "-0.01em" }}>
                Earn more. Code the same.
              </h2>
            </div>

            <div className="grid grid-cols-1 gap-10 lg:grid-cols-[320px_minmax(0,1fr)] lg:gap-12">
              <nav className="hidden lg:sticky lg:top-24 lg:block lg:self-start">
                <div className="flex flex-col">
                  {[
                    { id: "passive-income", icon: <DollarIcon />, iconClass: "bg-[#f5731a] text-white", label: "Passive Income" },
                    { id: "sponsor-line", icon: <CodeIcon />, iconClass: "bg-[#e8eaf6] text-[#f5731a] shadow-[inset_0_0_0_1px_#c5cae9]", label: "One Sponsor Line" },
                    { id: "any-terminal", icon: <TerminalIcon />, iconClass: "bg-[#111] text-white", label: "Any AI Terminal" },
                    { id: "advertiser-tools", icon: <ChartIcon />, iconClass: "bg-[#f5f5f5] text-[#666]", label: "Advertiser Dashboard" },
                  ].map((item, i) => (
                    <a
                      key={item.id}
                      href={`#${item.id}`}
                      className={`group flex items-center gap-3 border-b border-black/[0.06] py-4 text-left transition-colors text-[10px] font-medium tracking-[0.28em] uppercase ${i === 0 ? "text-[#111]" : "text-[#999] hover:text-[#111]"}`}
                    >
                      <span className={`inline-flex shrink-0 items-center justify-center w-6 h-6 rounded-md transition-opacity ${i === 0 ? "opacity-100" : "opacity-45 group-hover:opacity-100"} ${item.iconClass}`}>
                        {item.icon}
                      </span>
                      {item.label}
                    </a>
                  ))}
                </div>
              </nav>

              <div className="flex flex-col gap-20">
                <article id="passive-income" className="scroll-mt-28">
                  <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
                    <div className="flex max-w-3xl flex-col gap-5">
                      <div className="flex items-center gap-3">
                        <span className="inline-flex shrink-0 items-center justify-center w-6 h-6 rounded-md bg-[#f5731a] text-white">
                          <DollarIcon />
                        </span>
                        <span className="text-xs font-medium tracking-[0.22em] text-[#999] uppercase">Passive Income</span>
                      </div>
                      <h3 className="max-w-2xl text-3xl sm:text-4xl text-[#111]" style={{ fontWeight: 600, lineHeight: 1.2, letterSpacing: "-0.01em", textWrap: "balance" }}>
                        Earn while your AI thinks
                      </h3>
                      <p className="text-[#666] text-base leading-relaxed max-w-3xl">
                        Your AI coding terminal already shows a spinner while it works. Monty turns that idle time into revenue with a single, tasteful sponsor line. Keep 90% of every dollar.
                      </p>
                    </div>
                    <a href="#" className="inline-flex shrink-0 items-center gap-1.5 h-9 px-3 bg-[#111] text-white text-sm font-medium rounded-[10px] hover:opacity-85 transition-opacity">
                      Get Started <ArrowIcon />
                    </a>
                  </div>
                  <div className="overflow-hidden rounded-2xl bg-[#f5f5f5]">
                    <div className="aspect-[1840/1174] bg-gradient-to-br from-[#fff3e0] via-[#e8eaf6] to-[#e3f2fd] flex items-center justify-center text-[#999] text-sm">
                      Passive income earnings dashboard
                    </div>
                  </div>
                </article>

                <article id="sponsor-line" className="scroll-mt-28">
                  <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
                    <div className="flex max-w-3xl flex-col gap-5">
                      <div className="flex items-center gap-3">
                        <span className="inline-flex shrink-0 items-center justify-center w-6 h-6 rounded-md bg-[#e8eaf6] text-[#f5731a] shadow-[inset_0_0_0_1px_#c5cae9]">
                          <CodeIcon />
                        </span>
                        <span className="text-xs font-medium tracking-[0.22em] text-[#999] uppercase">One Sponsor Line</span>
                      </div>
                      <h3 className="max-w-2xl text-3xl sm:text-4xl text-[#111]" style={{ fontWeight: 600, lineHeight: 1.2, letterSpacing: "-0.01em", textWrap: "balance" }}>
                        Zero disruption to your flow
                      </h3>
                      <p className="text-[#666] text-base leading-relaxed max-w-3xl">
                        Just one line. Shown only while AI is thinking. No popups, no banners, no tracking. Developers stay focused, sponsors reach the right audience, everyone wins.
                      </p>
                    </div>
                    <a href="#" className="inline-flex shrink-0 items-center gap-1.5 h-9 px-3 bg-[#111] text-white text-sm font-medium rounded-[10px] hover:opacity-85 transition-opacity">
                      See How It Works <ArrowIcon />
                    </a>
                  </div>
                  <div className="overflow-hidden rounded-2xl bg-[#f5f5f5]">
                    <div className="aspect-[1840/1174] bg-gradient-to-br from-[#e3f2fd] via-[#e8eaf6] to-[#ede7f6] flex items-center justify-center text-[#999] text-sm">
                      Sponsor line preview in terminal
                    </div>
                  </div>
                </article>

                <article id="any-terminal" className="scroll-mt-28">
                  <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
                    <div className="flex max-w-3xl flex-col gap-5">
                      <div className="flex items-center gap-3">
                        <span className="inline-flex shrink-0 items-center justify-center w-6 h-6 rounded-md bg-[#111] text-white">
                          <TerminalIcon />
                        </span>
                        <span className="text-xs font-medium tracking-[0.22em] text-[#999] uppercase">Any AI Terminal</span>
                      </div>
                      <h3 className="max-w-2xl text-3xl sm:text-4xl text-[#111]" style={{ fontWeight: 600, lineHeight: 1.2, letterSpacing: "-0.01em", textWrap: "balance" }}>
                        Works with every AI coding tool
                      </h3>
                      <p className="text-[#666] text-base leading-relaxed max-w-3xl">
                        Claude Code, GitHub Copilot, Cursor, Windsurf — Monty hooks into the spinner your terminal already shows. Install once, earn everywhere.
                      </p>
                    </div>
                    <a href="#" className="inline-flex shrink-0 items-center gap-1.5 h-9 px-3 bg-[#111] text-white text-sm font-medium rounded-[10px] hover:opacity-85 transition-opacity">
                      Install Now <ArrowIcon />
                    </a>
                  </div>
                  <div className="overflow-hidden rounded-2xl bg-[#f5f5f5]">
                    <div className="aspect-[1840/1174] bg-gradient-to-br from-[#ede7f6] via-[#e8eaf6] to-[#e3f2fd] flex items-center justify-center text-[#999] text-sm">
                      Multi-terminal integration view
                    </div>
                  </div>
                </article>

                <article id="advertiser-tools" className="scroll-mt-28">
                  <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
                    <div className="flex max-w-3xl flex-col gap-5">
                      <div className="flex items-center gap-3">
                        <span className="inline-flex shrink-0 items-center justify-center w-6 h-6 rounded-md bg-[#f5731a] text-white">
                          <ChartIcon />
                        </span>
                        <span className="text-xs font-medium tracking-[0.22em] text-[#999] uppercase">Advertiser Dashboard</span>
                      </div>
                      <h3 className="max-w-2xl text-3xl sm:text-4xl text-[#111]" style={{ fontWeight: 600, lineHeight: 1.2, letterSpacing: "-0.01em", textWrap: "balance" }}>
                        Reach developers where they build
                      </h3>
                      <p className="text-[#666] text-base leading-relaxed max-w-3xl">
                        Sponsors get premium developer attention during active coding sessions. Real-time analytics, contextual targeting, and a developer-approved format.
                      </p>
                    </div>
                    <a href="#" className="inline-flex shrink-0 items-center gap-1.5 h-9 px-3 bg-[#111] text-white text-sm font-medium rounded-[10px] hover:opacity-85 transition-opacity">
                      Advertise With Us <ArrowIcon />
                    </a>
                  </div>
                  <div className="overflow-hidden rounded-2xl bg-[#f5f5f5]">
                    <div className="aspect-[1840/1174] bg-gradient-to-br from-[#fff3e0] via-[#ffe0b2] to-[#fff8e1] flex items-center justify-center text-[#999] text-sm">
                      Advertiser campaign dashboard
                    </div>
                  </div>
                </article>
              </div>
            </div>
          </div>
        </section>

        {/* ═══════════ HOW IT WORKS ═══════════ */}
        <section className="py-20" id="how-it-works">
          <div className="mx-auto w-full max-w-[1280px] px-6 lg:px-10 flex flex-col gap-10 sm:gap-16">
            <div className="flex max-w-2xl flex-col gap-6">
              <div className="flex flex-col gap-2">
                <div className="font-mono text-xs font-medium uppercase tracking-widest text-[#999]">How it works</div>
                <h2 className="text-[#111]" style={{ fontSize: "clamp(1.75rem, 3.5vw, 2.25rem)", lineHeight: 1.15, fontWeight: 600, letterSpacing: "-0.01em" }}>
                  Install in 30 seconds, earn forever
                </h2>
              </div>
              <p className="text-[#666] text-base leading-relaxed">
                One pip install. Monty hooks into your AI terminal&apos;s thinking spinner and shows a single sponsor line. You earn 90% of every impression. That&apos;s it.
              </p>
              <a href="#" className="inline-flex self-start shrink-0 items-center gap-1.5 h-11 px-4 bg-[#111] text-white text-sm font-medium rounded-[10px] hover:opacity-85 transition-opacity">
                Get started <ArrowIcon />
              </a>
            </div>

            <div className="relative w-full aspect-video rounded-2xl overflow-hidden bg-[#f5f5f5] cursor-pointer group shadow-lg shadow-black/5">
              <div className="absolute inset-0 bg-gradient-to-br from-[#e8eaf6] to-[#e3f2fd]" />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="flex size-16 items-center justify-center rounded-full bg-[#111] text-white shadow-xl transition-transform group-hover:scale-110">
                  <PlayIcon />
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ═══════════ TESTIMONIALS ═══════════ */}
        <section className="relative overflow-hidden py-20 sm:py-28" style={{ background: "#f5731a", color: "#fff" }}>
          <div className="mx-auto w-full max-w-[1280px] px-6 lg:px-10 relative">
            <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-center gap-x-6 gap-y-8 sm:gap-x-10">
              {testimonials.map((t, i) => (
                <button
                  key={t.company}
                  onClick={() => setActiveTestimonial(i)}
                  className="flex min-h-12 cursor-pointer items-center justify-center rounded-full px-1"
                >
                  <span className={`text-xl font-semibold text-white transition-opacity duration-200 ${i === activeTestimonial ? "opacity-100" : "opacity-40 hover:opacity-70"}`}>
                    {t.company}
                  </span>
                </button>
              ))}
            </div>

            <figure className="relative mx-auto mt-16 min-h-[24rem] max-w-5xl text-center sm:mt-20 sm:min-h-[28rem] lg:min-h-[32rem]">
              {testimonials.map((t, i) => (
                <div
                  key={t.company}
                  className={`absolute inset-0 flex flex-col items-center justify-start transition-opacity duration-500 ${i === activeTestimonial ? "opacity-100" : "pointer-events-none opacity-0"}`}
                >
                  <blockquote
                    className="mx-auto max-w-5xl text-white"
                    style={{
                      fontSize: "clamp(2rem, 4vw, 4.5rem)",
                      fontWeight: 400,
                      lineHeight: 1.1,
                      letterSpacing: "-0.02em",
                      textWrap: "balance",
                    }}
                  >
                    &ldquo;{t.quote}&rdquo;
                  </blockquote>
                  <figcaption className="mt-16 text-base sm:text-lg" style={{ color: "rgba(255,255,255,0.7)" }}>
                    <span className="font-semibold text-white">{t.name}</span>
                    <span>, {t.title}</span>
                  </figcaption>
                </div>
              ))}
            </figure>
          </div>
        </section>

        {/* ═══════════ CTA BANNER ═══════════ */}
        <section className="relative min-h-[480px] flex items-center justify-center overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-[#fff3e0] via-[#ffe8cc] to-white" />
          <div className="relative z-10 flex flex-col items-center gap-8 px-6 py-20 text-center">
            <h2 className="text-[#111] max-w-4xl" style={{ fontSize: "clamp(1.75rem, 3.5vw, 2.25rem)", lineHeight: 1.15, fontWeight: 600 }}>
              Start earning while you code.
            </h2>
            <a href="#" className="inline-flex shrink-0 items-center gap-1.5 text-sm font-medium hover:opacity-85 transition-opacity h-11 bg-[#111] text-white rounded-[10px] px-4">
              Install Monty
              <TerminalIcon />
            </a>
          </div>
        </section>
      </main>
    </>
  );
}
