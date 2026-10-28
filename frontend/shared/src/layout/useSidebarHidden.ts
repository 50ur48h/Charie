import { useState } from "react";

export function useSidebarHidden(): [boolean, (hidden: boolean) => void] {
  const [hidden, setHiddenState] = useState<boolean>(() => {
    try {
      return localStorage.getItem("charie-sidebar-hidden") === "1";
    } catch {
      return false;
    }
  });
  const setHidden = (value: boolean): void => {
    setHiddenState(value);
    try {
      localStorage.setItem("charie-sidebar-hidden", value ? "1" : "0");
    } catch {
      // Private browsing: the sidebar just doesn't stay hidden.
    }
  };
  return [hidden, setHidden];
}
