import { Navigate } from "react-router";
import { useMe } from "@charie/shared";

// The learner index route honors "never show again" (P04.3): sign-in lands
// on Sources once setup is done, on the guide before that.
export function LearnerIndex() {
  const me = useMe();
  if (me.isPending) return null;
  return <Navigate to={me.data?.setup_done ? "sources" : "setup"} replace />;
}
