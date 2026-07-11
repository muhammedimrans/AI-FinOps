import { cn, typeToConfirmMatches } from "../utils";

interface TypeToConfirmFieldProps {
  /** The exact string the user must type (e.g. the project or workspace name). */
  expected: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  id?: string;
}

/**
 * A "type the exact name to confirm" input — the guard this app's
 * destructive-deletion dialogs use so a delete can never happen from a
 * single misclick. Whitespace around the typed value is trimmed before
 * comparing (a trailing space shouldn't block an otherwise-correct
 * confirmation); native `<input>` already supports paste and Enter
 * (the latter handled by `ConfirmDialog` itself once `confirmDisabled`
 * turns false).
 */
export default function TypeToConfirmField({
  expected,
  value,
  onChange,
  disabled,
  id,
}: TypeToConfirmFieldProps) {
  const matches = typeToConfirmMatches(expected, value);
  return (
    <div className="mt-3">
      <label htmlFor={id} className="mb-1.5 block text-xs text-tx-muted">
        Type <span className="font-semibold text-tx-primary">{expected}</span> to confirm
      </label>
      <input
        id={id}
        autoFocus
        autoComplete="off"
        spellCheck={false}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        placeholder={expected}
        aria-invalid={!matches}
        className={cn(
          "w-full rounded-lg border bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none transition-colors disabled:opacity-60",
          matches ? "border-success focus:border-success" : "border-border-subtle focus:border-brand",
        )}
      />
    </div>
  );
}
