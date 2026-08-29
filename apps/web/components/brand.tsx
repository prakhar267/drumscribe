import Link from "next/link";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="brand" aria-label="DrumScribe home">
      <svg className="brand-mark" viewBox="0 0 34 34" aria-hidden="true">
        <circle cx="17" cy="17" r="15" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M8 13.5h18M8 20.5h18M12 9v16M22 9v16" stroke="currentColor" strokeWidth="1.5" opacity=".36" />
        <circle cx="12" cy="13.5" r="3" fill="currentColor" />
        <circle cx="22" cy="20.5" r="3" fill="currentColor" />
      </svg>
      {!compact && <span>DrumScribe</span>}
    </Link>
  );
}
