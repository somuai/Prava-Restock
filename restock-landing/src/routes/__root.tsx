import React, { useEffect } from 'react'
import { createRootRoute, Outlet } from '@tanstack/react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Header } from '@/components/Header'

const queryClient = new QueryClient()

export const rootRoute = createRootRoute({
  component: RootComponent,
})

export const Route = rootRoute

function RootComponent() {
  useEffect(() => {
    function u() {
      var w = document.documentElement.clientWidth
      var z = w < 1728 ? w / 1728 : 1
      document.documentElement.style.zoom = String(z)
    }
    u()
    window.addEventListener('resize', u)
    return () => window.removeEventListener('resize', u)
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-background text-foreground selection:bg-accent selection:text-white">
        <Header />
        <main>
          <Outlet />
        </main>
      </div>
    </QueryClientProvider>
  )
}
