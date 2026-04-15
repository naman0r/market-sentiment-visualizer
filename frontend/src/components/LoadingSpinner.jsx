import React from 'react'

export default function LoadingSpinner({ message = 'Loading market data...' }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-slate-900">
      <div className="flex flex-col items-center gap-5">
        {/* Outer ring */}
        <div className="relative flex items-center justify-center w-20 h-20">
          <div
            className="absolute inset-0 rounded-full border-4 border-slate-700"
          />
          <div
            className="absolute inset-0 rounded-full border-4 border-transparent border-t-blue-500"
            style={{ animation: 'spin 0.8s linear infinite' }}
          />
          {/* Inner pulse */}
          <div
            className="w-8 h-8 rounded-full bg-blue-500 opacity-20"
            style={{ animation: 'pulse-glow 1.6s ease-in-out infinite' }}
          />
        </div>

        <div className="text-center">
          <p className="text-slate-300 text-base font-medium tracking-wide">
            {message}
          </p>
          <p className="text-slate-500 text-sm mt-1">
            Connecting to market data feed
          </p>
        </div>

        {/* Animated dots */}
        <div className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-blue-500"
              style={{
                animation: `pulse-glow 1.2s ease-in-out infinite`,
                animationDelay: `${i * 0.2}s`,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
