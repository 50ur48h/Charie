// Client-side twin of the upload check in the fake API (mock learner
// handlers): Word, PDF, PowerPoint, Excel, Markdown and text, 50 MB each.
// The messages match the server's word for word. Returns the message to
// show, or null when the file can be added.
const LEARNABLE_EXTENSIONS = new Set(["docx", "pdf", "pptx", "xlsx", "md", "txt"]);

export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

export function checkFile(file: { name: string; size: number }): string | null {
  const ext = file.name.slice(file.name.lastIndexOf(".") + 1).toLowerCase();
  if (!LEARNABLE_EXTENSIONS.has(ext)) {
    return `${file.name} can't be added. Charie reads Word, PDF, PowerPoint, Excel, Markdown and text files.`;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `${file.name} is too big. Each file can be up to 50 MB.`;
  }
  return null;
}
