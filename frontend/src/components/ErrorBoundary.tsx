import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  reset = () => {
    this.setState({ hasError: false, error: null });
  };

  override render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div role="alert" className="flex flex-col items-center justify-center min-h-[320px] p-8 gap-4">
          <div className="w-12 h-12 rounded-full bg-danger-dim flex items-center justify-center">
            <AlertTriangle size={22} className="text-danger" />
          </div>
          <div className="text-center max-w-sm">
            <p className="text-sm font-semibold text-tx-primary mb-1">Something went wrong</p>
            <p className="text-xs text-tx-muted font-mono break-all">
              {this.state.error?.message ?? "An unexpected error occurred"}
            </p>
          </div>
          <button
            onClick={this.reset}
            className="btn-outline h-8 text-xs px-4 flex items-center gap-2"
          >
            <RefreshCw size={13} />
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
