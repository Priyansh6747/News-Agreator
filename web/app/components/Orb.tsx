type OrbSize = "lg" | "md" | "sm";

export function Orb({
  size = "lg",
  className = "",
}: {
  size?: OrbSize;
  className?: string;
}) {
  return (
    <span aria-hidden="true" className={`orb-shell orb-${size} ${className}`}>
      <span className="orb" />
    </span>
  );
}
