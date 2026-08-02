import * as React from 'react'
import { cn } from '@/lib/utils'

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'ghost' | 'secondary'
  size?: 'default' | 'sm' | 'lg' | 'icon'
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'default', ...props }, ref) => {
    return (
      <button
        className={cn(
          'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50',
          variant === 'default' && 'bg-white text-foreground hover:bg-white/90',
          variant === 'outline' && 'border border-white/20 bg-transparent hover:bg-white/10 text-white',
          variant === 'ghost' && 'hover:bg-white/10 text-white',
          variant === 'secondary' && 'bg-surface text-foreground hover:bg-surface/80',
          size === 'default' && 'h-10 px-5 py-2',
          size === 'sm' && 'h-8 px-3 text-xs',
          size === 'lg' && 'h-12 px-8 text-base',
          size === 'icon' && 'h-9 w-9 p-0',
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = 'Button'

export { Button }
