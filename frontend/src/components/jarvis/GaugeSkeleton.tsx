export function GaugeSkeleton({ size = 80 }: { size?: number }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="rounded-full animate-red-pulse" style={{ width: size, height: size, border: "4px solid hsla(0,72%,51%,0.15)" }} />
      <div className="h-2 w-12 bg-primary/10 rounded-sm animate-red-pulse" />
    </div>
  );
}
