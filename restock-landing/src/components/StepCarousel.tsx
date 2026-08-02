import React, { useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { MaskedImage } from './AnimatedHeading'

import stepTracker from '@/assets/step-tracker.png'
import stepOrchestrator from '@/assets/step-orchestrator.png'
import stepMandate from '@/assets/step-mandate.png'
import stepCheckout from '@/assets/step-checkout.png'
import stepConfirmation from '@/assets/step-confirmation.png'

interface StepItem {
  img: string
  role: string
  name: string
}

const stepsData: StepItem[] = [
  { img: stepTracker, role: 'STEP 01', name: 'Consumption Tracker' },
  { img: stepOrchestrator, role: 'STEP 02', name: 'Orchestrator Agent' },
  { img: stepMandate, role: 'STEP 03', name: 'Prava Mandate' },
  { img: stepCheckout, role: 'STEP 04', name: 'Merchant Checkout' },
  { img: stepConfirmation, role: 'STEP 05', name: 'Confirmation & Savings Log' },
]

interface StepCarouselProps {
  intro: React.ReactNode
}

export function StepCarousel({ intro }: StepCarouselProps) {
  const [index, setIndex] = useState(0)
  const [hovered, setHovered] = useState(false)

  const GAP = 11.26
  const visible = 3.25
  const maxIndex = Math.max(0, Math.ceil(stepsData.length - visible))

  return (
    <div
      className="relative w-full select-none cursor-default"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Inner Row */}
      <div className="flex" style={{ gap: `${GAP}px` }}>
        {/* Intro Column */}
        <div className="shrink-0 pt-2" style={{ width: '324px' }}>
          {intro}
        </div>

        {/* Viewport */}
        <div className="relative overflow-hidden flex-1 min-w-0">
          <motion.div
            className="flex"
            style={{
              gap: `${GAP}px`,
              width: `calc(${stepsData.length} * ((100% - ${(visible - 1) * GAP}px) / ${visible}) + ${(stepsData.length - 1) * GAP}px)`,
            }}
            animate={{
              x: `calc(${-index} * (100% + ${GAP}px) / ${stepsData.length})`,
            }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          >
            {stepsData.map((step, i) => (
              <div
                key={step.role}
                className="shrink-0"
                style={{
                  width: `calc((100% - ${(stepsData.length - 1) * GAP}px) / ${stepsData.length})`,
                }}
              >
                <div className="aspect-[3/4] overflow-hidden rounded-2xl bg-muted shadow-sm">
                  <MaskedImage
                    src={step.img}
                    alt={step.name}
                    className="w-full h-full"
                    delay={i * 0.08}
                  />
                </div>
                <div className="pt-6">
                  <p className="text-xs tracking-[0.2em] text-muted-foreground uppercase font-semibold">
                    {step.role}
                  </p>
                  <p className="text-xl mt-2 font-medium text-foreground">
                    {step.name}
                  </p>
                </div>
              </div>
            ))}
          </motion.div>
        </div>
      </div>

      {/* Hover Control Puck */}
      <AnimatePresence>
        {hovered && (
          <motion.div
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.85 }}
            transition={{ duration: 0.25 }}
            className="absolute top-[35%] left-1/2 -translate-x-1/2 -translate-y-1/2 z-10 pointer-events-auto"
          >
            <div
              className="flex items-center justify-center gap-4 rounded-full cursor-pointer shadow-2xl"
              style={{
                width: 126,
                height: 126,
                background: 'rgba(14, 92, 86, 0.25)',
                backdropFilter: 'blur(84px)',
                WebkitBackdropFilter: 'blur(84px)',
              }}
            >
              <button
                type="button"
                onClick={() => setIndex((i) => Math.max(0, i - 1))}
                disabled={index === 0}
                aria-label="Previous step"
                className="flex items-center justify-center text-white disabled:opacity-30 transition cursor-pointer p-2 rounded-full hover:bg-white/20"
              >
                <ArrowLeft className="w-7 h-7" />
              </button>
              <button
                type="button"
                onClick={() => setIndex((i) => Math.min(maxIndex, i + 1))}
                disabled={index >= maxIndex}
                aria-label="Next step"
                className="flex items-center justify-center text-white disabled:opacity-30 transition cursor-pointer p-2 rounded-full hover:bg-white/20"
              >
                <ArrowRight className="w-7 h-7" />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
