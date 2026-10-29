import { useEffect } from "react";
import { Navigate, useLocation } from "react-router";
import { Button } from "../components/Button";
import { Spinner } from "../components/Spinner";
import { useMe } from "../api/hooks";
import { applyServerTheme } from "../theme/serverTheme";

export function RequireLogin({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const { pathname, search } = useLocation();

  useEffect(() => {
    if (me.data?.logged_in) applyServerTheme(me.data.theme);
  }, [me.data]);

  if (me.isPending) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <p className="flex items-center gap-2.5 text-muted">
          <Spinner label="Loading" />
          Loading…
        </p>
      </div>
    );
  }
  if (me.isError) {
    return (
      <div className="grid min-h-dvh place-items-center px-5">
        <div className="grid justify-items-center gap-3 text-center">
          <p className="text-muted">Can&apos;t reach Charie right now.</p>
          <Button variant="outline" onClick={() => void me.refetch()}>
            Try again
          </Button>
        </div>
      </div>
    );
  }
  if (!me.data.logged_in) {
    return <Navigate to="/login" replace state={{ from: `${pathname}${search}` }} />;
  }
  return <>{children}</>;
}
