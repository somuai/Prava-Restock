import React, { useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { ShieldCheck, Fingerprint, CheckCircle2, RotateCcw, Zap, Sparkles, Building2, ShoppingBag } from 'lucide-react'

type TrackType = 'home' | 'teams'

export function InteractiveSimulator() {
  const [track, setTrack] = useState<TrackType>('home')
  const [simState, setSimState] = useState<'idle' | 'authenticating' | 'executing' | 'completed'>('idle')
  const [totalSaved, setTotalSaved] = useState(1280)

  const handleApprove = () => {
    setSimState('authenticating')
    setTimeout(() => {
      setSimState('executing')
      setTimeout(() => {
        setSimState('completed')
        if (track === 'home') {
          setTotalSaved((prev) => prev + 150)
        } else {
          setTotalSaved((prev) => prev + 4800)
        }
      }, 1400)
    }, 1200)
  }

  const handleReset = () => {
    setSimState('idle')
  }

  return (
    <div className="w-full max-w-5xl mx-auto rounded-3xl bg-surface border border-border/80 shadow-xl overflow-hidden p-8 md:p-12">
      {/* Header & Track Selector */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 pb-8 border-b border-border/60">
        <div>
          <div className="flex items-center gap-2 text-xs tracking-[0.2em] text-teal font-semibold uppercase mb-2">
            <Sparkles className="w-4 h-4 text-accent" />
            <span>Interactive Prava Simulator</span>
          </div>
          <h3 className="text-3xl font-medium text-foreground">
            Experience Auto-Buy in Real Time
          </h3>
        </div>

        {/* Tab Selector */}
        <div className="flex items-center gap-2 bg-muted p-1.5 rounded-full border border-border/40">
          <button
            type="button"
            onClick={() => {
              setTrack('home')
              setSimState('idle')
            }}
            className={`flex items-center gap-2 px-5 py-2 text-sm rounded-full font-medium transition cursor-pointer ${
              track === 'home'
                ? 'bg-teal text-white shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <ShoppingBag className="w-4 h-4" />
            <span>Restock Home</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setTrack('teams')
              setSimState('idle')
            }}
            className={`flex items-center gap-2 px-5 py-2 text-sm rounded-full font-medium transition cursor-pointer ${
              track === 'teams'
                ? 'bg-teal text-white shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Building2 className="w-4 h-4" />
            <span>Restock Teams</span>
          </button>
        </div>
      </div>

      {/* Simulator Display Area */}
      <div className="mt-8 grid grid-cols-1 md:grid-cols-12 gap-8 items-center">
        {/* Left Column: Signal & Proposal Details */}
        <div className="md:col-span-7 space-y-6">
          {track === 'home' ? (
            <div className="space-y-4">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/15 text-accent text-xs font-semibold">
                <Zap className="w-3.5 h-3.5" /> Predicted Signal Fired (92% Depleted)
              </div>
              <h4 className="text-2xl font-medium text-foreground">
                Blue Tokai Dark Roast Coffee Beans (250g)
              </h4>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Trigger cadence predicted depletion in <span className="font-semibold text-foreground">2 days</span>. Restock agent matched merchant availability on <span className="font-semibold text-foreground">Zepto Instamart</span> at regular price ₹450 with 10-minute dispatch.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/15 text-accent text-xs font-semibold">
                <Zap className="w-3.5 h-3.5" /> SaaS Renewal Watchdog Fired
              </div>
              <h4 className="text-2xl font-medium text-foreground">
                TeamTool Pro SaaS Subscription
              </h4>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Renewal due in <span className="font-semibold text-foreground">2 days</span> at $29/mo ($348/yr). Restock agent audited usage and proposes switching to the annual plan at $24/mo, saving <span className="font-semibold text-accent">₹4,800/yr ($58/yr)</span> instantly.
              </p>
            </div>
          )}

          {/* Telemetry Pill Grid */}
          <div className="grid grid-cols-3 gap-4 pt-2">
            <div className="p-4 rounded-2xl bg-muted/60 border border-border/40">
              <p className="text-xs text-muted-foreground">Spend Cap</p>
              <p className="text-lg font-semibold text-foreground mt-1">₹2,500/mo</p>
            </div>
            <div className="p-4 rounded-2xl bg-muted/60 border border-border/40">
              <p className="text-xs text-muted-foreground">Prava Mandate</p>
              <p className="text-lg font-semibold text-teal mt-1">Single-Use</p>
            </div>
            <div className="p-4 rounded-2xl bg-muted/60 border border-border/40">
              <p className="text-xs text-muted-foreground">Total Saved</p>
              <p className="text-lg font-semibold text-accent mt-1">₹{totalSaved.toLocaleString()}</p>
            </div>
          </div>
        </div>

        {/* Right Column: Interactive Passkey Modal */}
        <div className="md:col-span-5 flex flex-col items-center justify-center">
          <div className="w-full bg-background rounded-2xl p-6 border border-border shadow-lg relative min-h-[300px] flex flex-col justify-between">
            <AnimatePresence mode="wait">
              {simState === 'idle' && (
                <motion.div
                  key="idle"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="flex flex-col items-center text-center space-y-6 my-auto"
                >
                  <div className="w-16 h-16 rounded-full bg-teal/10 text-teal flex items-center justify-center shadow-inner">
                    <ShieldCheck className="w-8 h-8" />
                  </div>
                  <div>
                    <h5 className="text-lg font-medium text-foreground">
                      Approve Prava Mandate
                    </h5>
                    <p className="text-xs text-muted-foreground mt-1">
                      One passkey tap issuing a single-use merchant credential.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleApprove}
                    className="w-full py-3 px-6 rounded-full bg-accent text-white font-medium text-sm hover:bg-accent/90 transition shadow-md flex items-center justify-center gap-2 cursor-pointer"
                  >
                    <Fingerprint className="w-5 h-5" />
                    <span>Passkey Confirm</span>
                  </button>
                </motion.div>
              )}

              {simState === 'authenticating' && (
                <motion.div
                  key="authenticating"
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  className="flex flex-col items-center text-center space-y-6 my-auto"
                >
                  <motion.div
                    animate={{ scale: [1, 1.15, 1] }}
                    transition={{ repeat: Infinity, duration: 1 }}
                    className="w-20 h-20 rounded-full bg-accent/20 text-accent flex items-center justify-center border border-accent/40"
                  >
                    <Fingerprint className="w-10 h-10 animate-pulse" />
                  </motion.div>
                  <div>
                    <h5 className="text-lg font-medium text-foreground">
                      Verifying Passkey...
                    </h5>
                    <p className="text-xs text-muted-foreground mt-1">
                      Touch ID / Face ID challenge in progress
                    </p>
                  </div>
                </motion.div>
              )}

              {simState === 'executing' && (
                <motion.div
                  key="executing"
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  className="flex flex-col items-center text-center space-y-6 my-auto"
                >
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ repeat: Infinity, duration: 1.2, ease: 'linear' }}
                    className="w-16 h-16 rounded-full border-4 border-teal/20 border-t-teal flex items-center justify-center"
                  />
                  <div>
                    <h5 className="text-lg font-medium text-foreground">
                      Issuing Prava Mandate
                    </h5>
                    <p className="text-xs text-muted-foreground mt-1">
                      Executing merchant checkout via sandbox API
                    </p>
                  </div>
                </motion.div>
              )}

              {simState === 'completed' && (
                <motion.div
                  key="completed"
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  className="flex flex-col items-center text-center space-y-4 my-auto"
                >
                  <div className="w-16 h-16 rounded-full bg-teal text-white flex items-center justify-center shadow-lg">
                    <CheckCircle2 className="w-10 h-10" />
                  </div>
                  <div>
                    <h5 className="text-lg font-medium text-foreground">
                      Order Confirmed!
                    </h5>
                    <p className="text-xs text-muted-foreground mt-1">
                      {track === 'home'
                        ? 'Zepto order #PR-8821 dispatched. Delivery in 12 mins.'
                        : 'SaaS plan upgraded to annual. Saved ₹4,800/year.'}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleReset}
                    className="mt-2 text-xs text-muted-foreground hover:text-foreground flex items-center gap-1.5 cursor-pointer underline"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>Run Another Simulation</span>
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  )
}
