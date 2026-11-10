export interface SSEFrame {
  event?: string;
  id?: string;
  retry?: number;
  data: string;
}

const FRAME_BOUNDARY = /\r?\n\r?\n/;

export class SSEFramer {
  private buffer = "";

  push(chunk: string): SSEFrame[] {
    this.buffer += chunk;
    const frames: SSEFrame[] = [];

    while (true) {
      const match = FRAME_BOUNDARY.exec(this.buffer);
      if (!match) break;

      const raw = this.buffer.slice(0, match.index);
      this.buffer = this.buffer.slice(match.index + match[0].length);

      const frame = parseFrame(raw);
      if (frame) frames.push(frame);
    }

    return frames;
  }

  reset(): void {
    this.buffer = "";
  }
}

export async function* readSSE(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SSEFrame> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const framer = new SSEFramer();

  try {
    while (true) {
      if (signal?.aborted) {
        throw new DOMException("Aborted", "AbortError");
      }

      const { done, value } = await reader.read();
      if (done) break;

      for (const frame of framer.push(decoder.decode(value, { stream: true }))) {
        yield frame;
      }
    }

    for (const frame of framer.push(decoder.decode())) {
      yield frame;
    }
  } finally {
    framer.reset();
    try {
      await reader.cancel();
    } catch {
      // The reader is already closed or cancelled.
    }
    reader.releaseLock();
  }
}

function parseFrame(raw: string): SSEFrame | null {
  let eventName: string | undefined;
  let id: string | undefined;
  let retry: number | undefined;
  const dataLines: string[] = [];

  for (const line of raw.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue;

    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);

    if (value.startsWith(" ")) value = value.slice(1);

    switch (field) {
      case "event":
        eventName = value;
        break;
      case "data":
        dataLines.push(value);
        break;
      case "id":
        id = value;
        break;
      case "retry": {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) retry = parsed;
        break;
      }
      default:
        break;
    }
  }

  if (dataLines.length === 0) return null;

  return { event: eventName, id, retry, data: dataLines.join("\n") };
}
