import React from "react";

/** A render crash must not leave OPPO/vivo on a white screen. */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="min-h-screen grid place-items-center p-6 text-center" data-testid="app-error">
        <div>
          <p className="font-heading text-lg font-bold text-ink">Something went wrong</p>
          <p className="text-sm text-ink-soft mt-2 max-w-sm">
            The page hit an error. Tap reload — on some Android phones a pull-down
            refresh blanks the app.
          </p>
          <button
            type="button"
            className="mt-4 rounded-lg bg-cobalt px-4 py-2 text-sm font-semibold text-white"
            onClick={() => window.location.reload()}
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
