import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Identity, Profile } from "@/components/screens/profile";
import type { Me } from "@/lib/api-client";

const token = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api-client", () => ({ createApi: () => ({ me: async () => ({ name: "alex", email: "alex@example.com", subject: "identity-123", memberships: [{ org_id: "org-1", org_name: "My shop", role: "admin" }] }) }) }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
vi.mock("@/lib/auth/session", () => ({ useSession: () => ({ who: null, getToken: token }) }));
vi.mock("@/components/screens/sign-in", () => ({ SignIn: () => <button>Continue to sign in</button> }));

describe("organization onboarding", () => {
  it("links an organization directly to setup", async () => {
    render(<Profile />);
    expect(await screen.findByRole("button", { name: "Set up" })).toHaveAttribute("href", "/orgs/org-1/settings");
    expect(screen.getByText("My shop")).toBeInTheDocument();
    expect(screen.queryByText("alex@example.com")).not.toBeInTheDocument();
  });

  it("shows a username without synthetic email or subject in compact onboarding identity", () => {
    render(<Identity compact me={{ name: null, email: "alex@example.com", subject: "identity-123" } as Me} />);
    expect(screen.getByText("alex")).toBeInTheDocument();
    expect(screen.queryByText("alex@example.com")).not.toBeInTheDocument();
    expect(screen.queryByText("identity-123")).not.toBeInTheDocument();
  });
});
