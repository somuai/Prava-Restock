import React from 'react'
import { motion } from 'motion/react'

interface AnimatedHeadingProps {
  children: React.ReactNode
  className?: string
  as?: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6'
  delay?: number
  style?: React.CSSProperties
}

export function AnimatedHeading({
  children,
  className,
  as: As = 'h2',
  delay = 0,
  style,
}: AnimatedHeadingProps) {
  const MotionTag = motion[As]
  return (
    <MotionTag
      className={className}
      style={style}
      initial={{ opacity: 0, y: 30, filter: 'blur(12px)' }}
      whileInView={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.9, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </MotionTag>
  )
}

interface AnimatedTextProps {
  children: React.ReactNode
  className?: string
  delay?: number
  style?: React.CSSProperties
}

export function AnimatedText({
  children,
  className,
  delay = 0.15,
  style,
}: AnimatedTextProps) {
  return (
    <motion.p
      className={className}
      style={style}
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.7, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.p>
  )
}

interface MaskedImageProps {
  src: string
  alt: string
  className?: string
  delay?: number
}

export function MaskedImage({
  src,
  alt,
  className = '',
  delay = 0,
}: MaskedImageProps) {
  return (
    <motion.div
      className={`relative w-full h-full overflow-hidden ${className}`}
      initial={{ clipPath: 'inset(100% 0 0 0)' }}
      whileInView={{ clipPath: 'inset(0% 0 0 0)' }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 1.1, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      <img src={src} alt={alt} className="w-full h-full object-cover" />
    </motion.div>
  )
}
