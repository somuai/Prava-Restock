import React, { useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { MaskedImage } from './AnimatedHeading'

import blurDoctor from '@/assets/blur-doctor.png'
import happyDoctor from '@/assets/happy-doctor.png'
import youngDoctor from '@/assets/young-doctor.png'

interface TeamMember {
  img: string
  role: string
  name: string
}

const team: TeamMember[] = [
  { img: blurDoctor, role: 'SURGEON GENERAL', name: 'Dr. Helga Brooks' },
  { img: happyDoctor, role: 'PEDIATRICIAN', name: 'Dr. Kwame Mbeki' },
  { img: youngDoctor, role: 'THERAPIST', name: 'Dr. Matteo Dubois' },
  { img: happyDoctor, role: 'NEUROLOGIST', name: 'Dr. Hana Sato' },
  { img: blurDoctor, role: 'CARDIOLOGIST', name: 'Dr. Aria Vance' },
]

interface TeamCarouselProps {
  intro: React.ReactNode
}

export function TeamCarousel({ intro }: TeamCarouselProps) {
  const [index, setIndex] = useState(0)
  const [hovered, setHovered] = useState(false)

  const GAP = 11.26
  const visible = 3.25
  const maxIndex = Math.max(0, Math.ceil(team.length - visible))

  const fontTT = '"TT Hoves", "Helvetica Neue", Helvetica, Arial, sans-serif'

  return (
    <div
      className="relative w-full select-none cursor-default"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ fontFamily: fontTT }}
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
              width: `calc(${team.length} * ((100% - ${(visible - 1) * GAP}px) / ${visible}) + ${(team.length - 1) * GAP}px)`,
            }}
            animate={{
              x: `calc(${-index} * (100% + ${GAP}px) / ${team.length})`,
            }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          >
            {team.map((m, i) => (
              <div
                key={`${m.name}-${i}`}
                className="shrink-0"
                style={{
                  width: `calc((100% - ${(team.length - 1) * GAP}px) / ${team.length})`,
                  fontFamily: fontTT,
                }}
              >
                <div className="aspect-[3/4] overflow-hidden bg-muted rounded-2xl">
                  <MaskedImage
                    src={m.img}
                    alt={m.name}
                    className="w-full h-full"
                    delay={i * 0.08}
                  />
                </div>
                <div className="pt-6">
                  <p className="text-xs tracking-[0.2em] text-muted-foreground uppercase">
                    {m.role}
                  </p>
                  <p className="text-xl mt-2 font-medium text-foreground">
                    {m.name}
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
                background: 'rgba(72, 72, 72, 0.16)',
                backdropFilter: 'blur(84px)',
                WebkitBackdropFilter: 'blur(84px)',
              }}
            >
              <button
                type="button"
                onClick={() => setIndex((i) => Math.max(0, i - 1))}
                disabled={index === 0}
                aria-label="Previous team member"
                className="flex items-center justify-center text-white disabled:opacity-30 transition cursor-pointer p-2 rounded-full hover:bg-white/10"
              >
                <ArrowLeft className="w-7 h-7" />
              </button>
              <button
                type="button"
                onClick={() => setIndex((i) => Math.min(maxIndex, i + 1))}
                disabled={index >= maxIndex}
                aria-label="Next team member"
                className="flex items-center justify-center text-white disabled:opacity-30 transition cursor-pointer p-2 rounded-full hover:bg-white/10"
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
