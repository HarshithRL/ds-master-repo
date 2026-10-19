import Image from "next/image";

/**
 * Renders a country flag as an image from flagcdn.com.
 * Works consistently across all platforms (including Windows).
 */
export function CountryFlag({
  code,
  className,
  size = 20,
}: {
  code: string | null | undefined;
  className?: string;
  size?: number;
}) {
  if (!code || code.length !== 2) return null;

  const lowerCode = code.toLowerCase();

  return (
    <Image
      src={`https://flagcdn.com/w40/${lowerCode}.png`}
      alt={`Flag: ${code.toUpperCase()}`}
      width={size}
      height={Math.round(size * 0.75)}
      className={className}
      unoptimized
    />
  );
}
