import React, { useEffect, useState } from 'react'
import { Menu } from 'lucide-react'
import logoWhite from '@/assets/logo.svg'
import logoDark from '@/assets/logo-dark.svg'

export function Header() {
  const [isScrolled, setIsScrolled] = useState(false)

  useEffect(() => {
    const handleScroll = () => {
      if (window.scrollY > window.innerHeight - 80) {
        setIsScrolled(true)
      } else {
        setIsScrolled(false)
      }
    }

    handleScroll()
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const navItems = [
    { label: 'Home', href: '#' },
    { label: 'How it Works', href: '#how-it-works' },
    { label: 'For Teams', href: '#for-teams' },
    { label: 'Benefits', href: '#benefits' },
    { label: 'Docs', href: '#docs' },
  ]

  return (
    <header className="fixed top-6 left-0 right-0 z-50 px-8 flex items-center justify-between">
      <a href="#" className="flex items-center">
        <img
          src={isScrolled ? logoDark : logoWhite}
          alt="Restock logo"
          className="h-8 w-auto transition-opacity"
        />
      </a>

      <nav
        className="flex items-center gap-1 backdrop-blur-md text-white rounded-full pl-2 pr-2 py-2"
        style={{ backgroundColor: 'var(--header-bg)' }}
      >
        {navItems.map((item, index) => (
          <a
            key={item.label}
            href={item.href}
            className={`px-5 py-2 text-sm rounded-full transition ${
              index === 0
                ? 'bg-white/10 font-medium'
                : 'opacity-80 hover:opacity-100'
            }`}
          >
            {item.label}
          </a>
        ))}

        <button
          type="button"
          className="ml-2 flex items-center gap-2 px-4 py-2 text-sm rounded-full hover:bg-white/10 transition cursor-pointer"
        >
          <Menu className="w-4 h-4" />
          <span>Menu</span>
        </button>
      </nav>
    </header>
  )
}
