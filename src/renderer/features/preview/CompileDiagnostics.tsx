interface CompileDiagnosticsProps {
  errors: string[];
}

export function CompileDiagnostics({ errors }: CompileDiagnosticsProps) {
  return <pre className="compile-diagnostics">{errors.join("\n")}</pre>;
}
