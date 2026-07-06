/** Ambient, slowly-drifting colored blobs behind the whole app — the source of
 *  the "colorful" light mode. Purely decorative, so aria-hidden and pointer
 *  transparent; the blur + low opacity keep foreground text readable. */
export function GradientMesh() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div
        className="absolute -left-[10%] -top-[15%] size-[46rem] animate-float rounded-full opacity-60 blur-3xl"
        style={{ background: 'radial-gradient(circle, rgb(var(--blob-1)/0.55), transparent 60%)' }}
      />
      <div
        className="absolute -right-[12%] top-[8%] size-[40rem] animate-float-slow rounded-full opacity-50 blur-3xl"
        style={{ background: 'radial-gradient(circle, rgb(var(--blob-2)/0.5), transparent 60%)' }}
      />
      <div
        className="absolute bottom-[-18%] left-[25%] size-[44rem] animate-float rounded-full opacity-40 blur-3xl"
        style={{ background: 'radial-gradient(circle, rgb(var(--blob-3)/0.45), transparent 60%)' }}
      />
    </div>
  )
}
