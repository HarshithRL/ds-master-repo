"use client";

import { Component, type ReactNode } from "react";
import { AlertCircle } from "lucide-react";

interface Props {
  children: ReactNode;
  section?: string;
}

interface State {
  hasError: boolean;
}

export class SectionErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    if (process.env.NODE_ENV !== "production") {
      console.error(`[SectionErrorBoundary${this.props.section ? ` - ${this.props.section}` : ""}]`, error);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center gap-2 py-6 justify-center text-sm text-muted-foreground">
          <AlertCircle className="w-4 h-4 text-red-400" />
          <span>Something went wrong{this.props.section ? ` in ${this.props.section}` : ""}.</span>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="text-xs font-medium text-etex-orange hover:underline"
          >
            Try again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
