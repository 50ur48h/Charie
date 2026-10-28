import { Link, useInRouterContext } from "react-router";

// A link that uses the router inside the apps and a plain anchor in
// router-less contexts (frame demos, unit tests without a router).
export function RouterLink({
  to,
  children,
  ...rest
}: {
  to: string;
  children: React.ReactNode;
} & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href">) {
  const inRouter = useInRouterContext();
  if (inRouter) {
    return (
      <Link to={to} {...rest}>
        {children}
      </Link>
    );
  }
  return (
    <a href={to} {...rest}>
      {children}
    </a>
  );
}
