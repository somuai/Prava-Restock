import React from 'react'
import { createRoute } from '@tanstack/react-router'
import { rootRoute } from './__root'
import { ArrowUpRight, Github, FileText, CheckCircle } from 'lucide-react'
import { AnimatedHeading, AnimatedText, MaskedImage } from '@/components/AnimatedHeading'
import { StepCarousel } from '@/components/StepCarousel'
import { InteractiveSimulator } from '@/components/InteractiveSimulator'

import heroShelf from '@/assets/hero-shelf.png'
import benefitStockouts from '@/assets/benefit-stockouts.png'
import benefitOverpaying from '@/assets/benefit-overpaying.png'
import benefitReactive from '@/assets/benefit-reactive.png'

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: IndexPage,
})

export const Route = indexRoute

function IndexPage() {
  return (
    <>
      {/* 1) HERO SECTION */}
      <section className="relative h-screen min-h-[780px] w-full overflow-hidden bg-black text-white">
        {/* Background Image */}
        <img
          src={heroShelf}
          alt="A watched-over pantry shelf"
          className="absolute inset-0 w-full h-full object-cover"
        />

        {/* Overlays */}
        <div className="absolute inset-0 bg-black/30" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/20 to-transparent" />

        {/* Content Wrapper */}
        <div className="absolute inset-0 flex flex-col justify-end pb-16 px-8 md:px-12 z-10">
          {/* Bottom Row */}
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
            {/* LEFT Column */}
            <div className="max-w-3xl">
              <AnimatedHeading
                as="h1"
                className="text-white font-medium leading-[1.05]"
              >
                <span
                  style={{
                    fontSize: '72.73px',
                    lineHeight: 1.05,
                    display: 'block',
                  }}
                >
                  The Agent That
                  <br />
                  Never Waits to Be Asked
                </span>
              </AnimatedHeading>

              <div className="mt-8 w-max">
                <AnimatedText className="text-white/85 max-w-xl leading-relaxed">
                  <span
                    style={{
                      fontSize: '20.99px',
                      lineHeight: '28.21px',
                      display: 'block',
                      width: '608px',
                    }}
                  >
                    Restock watches what you're about to run out of, and quietly
                    handles it before you notice — one passkey approval,
                    powered end-to-end by Prava.
                  </span>
                </AnimatedText>
              </div>
            </div>

            {/* RIGHT Column */}
            <div className="flex items-center gap-6 shrink-0 pb-1">
              <a
                href="#how-it-works"
                className="bg-white text-foreground rounded-full pl-6 pr-2 py-2 flex items-center gap-3 font-medium text-sm hover:bg-white/90 transition shadow-lg cursor-pointer"
              >
                <span>See How It Works</span>
                <span className="w-9 h-9 rounded-full bg-foreground text-white flex items-center justify-center">
                  <ArrowUpRight className="w-4 h-4" />
                </span>
              </a>

              <a
                href="https://github.com"
                target="_blank"
                rel="noopener noreferrer"
                className="text-white flex items-center gap-1 text-sm font-medium hover:text-white/80 transition"
              >
                <span>View the Build</span>
                <ArrowUpRight className="w-4 h-4" />
              </a>
            </div>
          </div>

          {/* Hero Footer Strip */}
          <div
            className="mt-12 pt-5 border-t border-white/20 flex items-center justify-between tracking-[0.2em] text-white/70 uppercase text-xs"
            style={{ fontSize: '12px' }}
          >
            <div>Autonomous Commerce, Built on Prava</div>
            <div className="flex items-center gap-6">
              <span>
                <span className="text-white font-semibold">01</span> / 03
              </span>
              <span>Next</span>
            </div>
            <div>Scroll to Explore</div>
          </div>
        </div>
      </section>

      {/* 2) HOW IT WORKS SECTION */}
      <section id="how-it-works" className="py-32 px-8 md:px-12 bg-background">
        {/* Heading Block */}
        <div style={{ paddingLeft: '335.26px' }}>
          <div
            className="flex gap-24 tracking-[0.2em] uppercase text-muted-foreground mb-16 font-medium"
            style={{ fontSize: '11.26px' }}
          >
            <span>Restock</span>
            <span>How It Works</span>
          </div>

          <AnimatedHeading className="font-medium leading-[1.05] text-foreground">
            <span
              style={{
                fontSize: '58.55px',
                lineHeight: 1.05,
                display: 'block',
              }}
            >
              Five Steps.
              <br />
              One Approval.
            </span>
          </AnimatedHeading>
        </div>

        {/* Carousel Wrapper */}
        <div className="mt-20">
          <StepCarousel
            intro={
              <AnimatedText className="text-muted-foreground leading-relaxed">
                <span
                  style={{
                    fontSize: '16.89px',
                    lineHeight: 1.5,
                    display: 'block',
                    width: '270px',
                  }}
                >
                  Every purchase starts the same way: a signal fires, you approve
                  once, and the agent takes it from there.
                </span>
              </AnimatedText>
            }
          />
        </div>
      </section>

      {/* 3) FOR TEAMS & INTERACTIVE SIMULATOR SECTION */}
      <section id="for-teams" className="py-24 px-8 md:px-12 bg-background border-t border-border/40">
        <div className="max-w-6xl mx-auto mb-16 text-center">
          <div
            className="tracking-[0.2em] uppercase text-muted-foreground mb-6 font-medium"
            style={{ fontSize: '11.26px' }}
          >
            Dual Track Commerce · Home & Teams
          </div>
          <AnimatedHeading
            as="h2"
            className="text-4xl md:text-5xl font-medium leading-[1.1] text-foreground max-w-3xl mx-auto"
          >
            From Pantry Consumables to Team SaaS Renewals
          </AnimatedHeading>
          <AnimatedText className="text-muted-foreground text-base max-w-2xl mx-auto mt-4 leading-relaxed">
            One engine, two trigger sources — predicted depletion dates for household consumables, and known renewal dates for team SaaS subscriptions.
          </AnimatedText>
        </div>

        {/* Live Simulator Component */}
        <InteractiveSimulator />
      </section>

      {/* 4) BENEFITS SECTION */}
      <section id="benefits" className="py-32 px-8 md:px-12 bg-surface">
        {/* Top Intro Grid */}
        <div className="mb-24 grid grid-cols-12 gap-12">
          <div className="col-span-12 md:col-span-7">
            <AnimatedHeading
              as="h2"
              className="text-5xl md:text-6xl font-medium leading-[1.05] text-foreground"
            >
              Why Not Just
              <br />
              Ask a Chatbot?
            </AnimatedHeading>
          </div>
          <div className="col-span-12 md:col-span-4 md:col-start-9 md:pt-4">
            <AnimatedText className="text-base text-muted-foreground leading-relaxed">
              Reactive shopping bots wait for you to ask — and that pattern
              already has a track record. Walmart's own ChatGPT checkout converted
              three times worse than its website. Restock doesn't wait.
            </AnimatedText>
          </div>
        </div>

        {/* 3-Card Grid */}
        <div
          className="relative grid grid-cols-1 md:grid-cols-3 gap-12 md:gap-0 py-8"
          style={{
            backgroundImage:
              'linear-gradient(to bottom, transparent, rgba(0,0,0,0.12) 15%, rgba(0,0,0,0.12) 85%, transparent), linear-gradient(to bottom, transparent, rgba(0,0,0,0.12) 15%, rgba(0,0,0,0.12) 85%, transparent)',
            backgroundSize: '1px 100%, 1px 100%',
            backgroundPosition: '33.333% 0, 66.666% 0',
            backgroundRepeat: 'no-repeat',
          }}
        >
          {/* Top Horizontal Border Line */}
          <span
            aria-hidden
            className="absolute top-0 left-0 right-0 h-[1px]"
            style={{
              background:
                'linear-gradient(to right, transparent, rgba(0,0,0,0.12) 10%, rgba(0,0,0,0.12) 90%, transparent)',
            }}
          />

          {/* Card 01: Stockouts */}
          <div className="flex flex-col justify-between px-0 md:px-10 min-h-[520px]">
            <div>
              <div className="flex items-start gap-3 mb-4">
                <span className="text-xs text-muted-foreground mt-2">
                  (01)
                </span>
                <AnimatedHeading
                  as="h3"
                  className="text-3xl font-medium text-foreground"
                  delay={0}
                >
                  Stockouts
                </AnimatedHeading>
              </div>
              <AnimatedText
                className="text-sm text-muted-foreground leading-relaxed max-w-sm"
                delay={0.2}
              >
                Recurring essentials run out at the worst moment — and same-day
                quick-commerce surcharges make it worse.
              </AnimatedText>
            </div>
            <div className="mt-auto aspect-square overflow-hidden rounded-2xl bg-muted/50 shadow-sm">
              <MaskedImage
                src={benefitStockouts}
                alt="Stockouts illustration"
                delay={0}
              />
            </div>
          </div>

          {/* Card 02: Overpaying (REVERSED: Image Top, Content Bottom) */}
          <div className="flex flex-col justify-between px-0 md:px-10 min-h-[520px]">
            <div className="aspect-square overflow-hidden rounded-2xl bg-muted/50 mb-8 shadow-sm">
              <MaskedImage
                src={benefitOverpaying}
                alt="Overpaying illustration"
                delay={0.12}
              />
            </div>
            <div className="mt-auto">
              <div className="flex items-start gap-3 mb-4">
                <span className="text-xs text-muted-foreground mt-2">
                  (02)
                </span>
                <AnimatedHeading
                  as="h3"
                  className="text-3xl font-medium text-foreground"
                  delay={0.1}
                >
                  Overpaying
                </AnimatedHeading>
              </div>
              <AnimatedText
                className="text-sm text-muted-foreground leading-relaxed max-w-sm"
                delay={0.3}
              >
                Small teams silently auto-renew SaaS subscriptions at prices
                nobody re-checked. Industry-wide, that's $18B wasted a year.
              </AnimatedText>
            </div>
          </div>

          {/* Card 03: Reactive Bots */}
          <div className="flex flex-col justify-between px-0 md:px-10 min-h-[520px]">
            <div>
              <div className="flex items-start gap-3 mb-4">
                <span className="text-xs text-muted-foreground mt-2">
                  (03)
                </span>
                <AnimatedHeading
                  as="h3"
                  className="text-3xl font-medium text-foreground"
                  delay={0.2}
                >
                  Reactive Bots
                </AnimatedHeading>
              </div>
              <AnimatedText
                className="text-sm text-muted-foreground leading-relaxed max-w-sm"
                delay={0.4}
              >
                Most agentic commerce today waits for you to ask first. Restock
                fires before you do.
              </AnimatedText>
            </div>
            <div className="mt-auto aspect-square overflow-hidden rounded-2xl bg-muted/50 shadow-sm">
              <MaskedImage
                src={benefitReactive}
                alt="Reactive Bots illustration"
                delay={0.24}
              />
            </div>
          </div>

          {/* Bottom Horizontal Border Line */}
          <span
            aria-hidden
            className="absolute bottom-0 left-0 right-0 h-[1px]"
            style={{
              background:
                'linear-gradient(to right, transparent, rgba(0,0,0,0.12) 10%, rgba(0,0,0,0.12) 90%, transparent)',
            }}
          />
        </div>
      </section>

      {/* 5) DOCS / FOOTER CTA SECTION */}
      <footer id="docs" className="py-24 px-8 md:px-12 bg-background border-t border-border/40">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-8">
          <div>
            <h3 className="text-3xl font-medium text-foreground">
              Ready to automate your recurring purchases?
            </h3>
            <p className="text-muted-foreground text-sm mt-2">
              Autonomous commerce powered end-to-end by Prava passkey mandates.
            </p>
          </div>

          <div className="flex items-center gap-4">
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-3 rounded-full bg-teal text-white font-medium text-sm hover:bg-teal/90 transition shadow-md flex items-center gap-2"
            >
              <Github className="w-4 h-4" />
              <span>Explore GitHub Repo</span>
            </a>

            <a
              href="#"
              className="px-6 py-3 rounded-full border border-border bg-surface text-foreground font-medium text-sm hover:bg-surface/80 transition flex items-center gap-2"
            >
              <FileText className="w-4 h-4 text-teal" />
              <span>Read Technical PRD</span>
            </a>
          </div>
        </div>

        <div className="max-w-6xl mx-auto mt-16 pt-8 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
          <p>© 2026 Restock Inc. Built for Prava Agentic Commerce Hackathon.</p>
          <p>Autonomous Commerce Protocol v2.0</p>
        </div>
      </footer>
    </>
  )
}
