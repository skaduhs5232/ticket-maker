import { Injectable, NgZone } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export type MessageRole = 'user' | 'ai';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  isStreaming?: boolean;
  toolCalls?: ToolCallEvent[];
  timestamp: Date;
}

export interface ToolCallEvent {
  tool: string;
  args: Record<string, unknown>;
}

export interface StreamEvent {
  type: 'token' | 'tool_call' | 'done' | 'error';
  content?: string;
  tool?: string;
  args?: Record<string, unknown>;
  conversation_id?: number;
  message?: string;
}

@Injectable({ providedIn: 'root' })
export class ChatService {
  private apiUrl = environment.api_back;

  constructor(private ngZone: NgZone) {}

  streamMessage(
    message: string,
    projectId: number,
    conversationId: number | null
  ): Observable<StreamEvent> {
    return new Observable<StreamEvent>((observer) => {
      // Use fetch() with a POST + SSE read via ReadableStream
      const body = JSON.stringify({
        message,
        project_id: projectId,
        conversation_id: conversationId,
      });

      const controller = new AbortController();

      fetch(`${this.apiUrl}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: controller.signal,
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`HTTP error: ${response.status}`);
          }
          const reader = response.body!.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          const pump = (): Promise<void> =>
            reader.read().then(({ done, value }) => {
              if (done) {
                observer.complete();
                return;
              }

              buffer += decoder.decode(value, { stream: true });
              const lines = buffer.split('\n');
              buffer = lines.pop() ?? '';

              for (const line of lines) {
                if (line.startsWith('data: ')) {
                  const raw = line.slice(6).trim();
                  if (!raw) continue;
                  try {
                    const event: StreamEvent = JSON.parse(raw);
                    this.ngZone.run(() => observer.next(event));
                  } catch {
                    // ignore malformed chunks
                  }
                }
              }

              return pump();
            });

          return pump();
        })
        .catch((err) => {
          if (err.name !== 'AbortError') {
            this.ngZone.run(() => observer.error(err));
          }
        });

      // Teardown: abort fetch if unsubscribed
      return () => controller.abort();
    });
  }
}
