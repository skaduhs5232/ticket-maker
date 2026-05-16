import {
  Component,
  OnInit,
  signal,
  computed,
  inject,
  ViewChild,
  ElementRef,
  AfterViewChecked,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';
import { LucideAngularModule, ChevronRight, ArrowLeftRight, User, Bot, Send, Ticket } from 'lucide-angular';

import { ProjectService, Project } from '../../services/project.service';
import {
  ChatService,
  ChatMessage,
  StreamEvent,
} from '../../services/chat.service';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    HttpClientModule,
    LucideAngularModule
  ],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.css',
})
export class ChatComponent implements OnInit, AfterViewChecked {
  @ViewChild('messagesEnd') messagesEnd!: ElementRef;
  @ViewChild('inputRef') inputRef!: ElementRef<HTMLTextAreaElement>;

  private projectService = inject(ProjectService);
  private chatService = inject(ChatService);

  // State
  projects = signal<Project[]>([]);
  selectedProject = signal<Project | null>(null);
  messages = signal<ChatMessage[]>([]);
  inputText = signal('');
  isLoading = signal(false);
  isStreaming = signal(false);
  projectsLoading = signal(true);
  projectsError = signal('');
  conversationId = signal<number | null>(null);
  showProjectSelector = signal(true);
  private shouldScroll = false;

  // Computed
  canSend = computed(
    () =>
      this.inputText().trim().length > 0 &&
      !this.isStreaming() &&
      !!this.selectedProject()
  );

  selectedProjectName = computed(
    () => this.selectedProject()?.name ?? 'Selecione um projeto'
  );

  ngOnInit() {
    this.projectService.getProjects().subscribe({
      next: (projects) => {
        this.projects.set(projects);
        this.projectsLoading.set(false);
      },
      error: () => {
        this.projectsError.set('Falha ao carregar projetos. Verifique a conexão com o servidor.');
        this.projectsLoading.set(false);
      },
    });
  }

  ngAfterViewChecked() {
    if (this.shouldScroll) {
      this.scrollToBottom();
      this.shouldScroll = false;
    }
  }

  selectProject(project: Project) {
    this.selectedProject.set(project);
    this.showProjectSelector.set(false);
    this.messages.set([]);
    this.conversationId.set(null);

    // Add welcome message
    const welcome: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'ai',
      content: `Olá! Sou o **Ticket Maker**, seu assistente de suporte para o projeto **${project.name}**. 😊\n\nDescreva o problema ou dúvida que você está enfrentando e farei o possível para ajudá-lo. Se não conseguir resolver, posso abrir um chamado no OpenProject para você.`,
      timestamp: new Date(),
    };
    this.messages.update((msgs) => [...msgs, welcome]);
    this.shouldScroll = true;
  }

  changeProject() {
    this.showProjectSelector.set(true);
    this.selectedProject.set(null);
  }

  onInputKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  onInputChange(event: Event) {
    const target = event.target as HTMLTextAreaElement;
    this.inputText.set(target.value);
    // Auto-resize textarea
    target.style.height = 'auto';
    target.style.height = Math.min(target.scrollHeight, 160) + 'px';
  }

  sendMessage() {
    const text = this.inputText().trim();
    const project = this.selectedProject();
    if (!text || !project || this.isStreaming()) return;

    // Add user message
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    };
    this.messages.update((msgs) => [...msgs, userMsg]);
    this.inputText.set('');
    this.shouldScroll = true;

    // Reset textarea height
    if (this.inputRef?.nativeElement) {
      this.inputRef.nativeElement.value = '';
      this.inputRef.nativeElement.style.height = 'auto';
    }

    // Add streaming AI placeholder
    const aiMsgId = crypto.randomUUID();
    const aiMsg: ChatMessage = {
      id: aiMsgId,
      role: 'ai',
      content: '',
      isStreaming: true,
      toolCalls: [],
      timestamp: new Date(),
    };
    this.messages.update((msgs) => [...msgs, aiMsg]);
    this.isStreaming.set(true);

    this.chatService
      .streamMessage(text, project.id, this.conversationId())
      .subscribe({
        next: (event: StreamEvent) => {
          this.handleStreamEvent(event, aiMsgId);
        },
        error: (err) => {
          this.updateMessage(aiMsgId, {
            content: `❌ Erro de conexão: ${err.message ?? 'Tente novamente.'}`,
            isStreaming: false,
          });
          this.isStreaming.set(false);
        },
        complete: () => {
          this.updateMessage(aiMsgId, { isStreaming: false });
          this.isStreaming.set(false);
          this.shouldScroll = true;
        },
      });
  }

  private handleStreamEvent(event: StreamEvent, aiMsgId: string) {
    switch (event.type) {
      case 'token':
        this.messages.update((msgs) =>
          msgs.map((m) =>
            m.id === aiMsgId
              ? { ...m, content: m.content + (event.content ?? '') }
              : m
          )
        );
        this.shouldScroll = true;
        break;

      case 'tool_call':
        this.messages.update((msgs) =>
          msgs.map((m) =>
            m.id === aiMsgId
              ? {
                  ...m,
                  toolCalls: [
                    ...(m.toolCalls ?? []),
                    { tool: event.tool!, args: event.args ?? {} },
                  ],
                }
              : m
          )
        );
        break;

      case 'done':
        if (event.conversation_id) {
          this.conversationId.set(event.conversation_id);
        }
        this.updateMessage(aiMsgId, { isStreaming: false });
        this.isStreaming.set(false);
        break;

      case 'error':
        this.updateMessage(aiMsgId, {
          content: `❌ ${event.message ?? 'Ocorreu um erro inesperado.'}`,
          isStreaming: false,
        });
        this.isStreaming.set(false);
        break;
    }
  }

  private updateMessage(id: string, patch: Partial<ChatMessage>) {
    this.messages.update((msgs) =>
      msgs.map((m) => (m.id === id ? { ...m, ...patch } : m))
    );
  }

  private scrollToBottom() {
    this.messagesEnd?.nativeElement?.scrollIntoView({ behavior: 'smooth' });
  }

  getToolLabel(toolName: string): string {
    const labels: Record<string, string> = {
      search_knowledge_base: '📚 Consultando base de conhecimento',
      search_existing_tickets: '🔍 Buscando tickets similares',
      create_ticket: '🎫 Criando ticket no OpenProject',
    };
    return labels[toolName] ?? `⚙️ ${toolName}`;
  }

  trackById(_: number, msg: ChatMessage) {
    return msg.id;
  }

  formatContent(content: string): string {
    // Simple Markdown-like rendering for bold, code, links
    return content
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.+?)`/g, '<code>$1</code>')
      .replace(/\[(.+?)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/\n/g, '<br>');
  }
}
