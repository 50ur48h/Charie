import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource-variable/source-serif-4/opsz.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";

let ready: Promise<void> | null = null;

export function fontsReady(): Promise<void> {
  if (!ready) {
    const fonts = (document as Document).fonts?.ready?.then(() => undefined);
    const timeout = new Promise<void>((resolve) => {
      setTimeout(resolve, 1500);
    });
    ready = fonts ? Promise.race([fonts, timeout]).then(() => undefined) : timeout;
  }
  return ready;
}
