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
import { Router } from '@angular/router';
import { LucideChevronRight, LucideArrowLeftRight, LucideUser, LucideBot, LucideSend, LucideTicket } from '@lucide/angular';

import { ProjectService, Project } from '../../services/project.service';
import {
  ChatService,
  ChatMessage,
  StreamEvent,
} from '../../services/chat.service';
import { AuthService } from '../../services/auth.service';
import { ThemeService } from '../../services/theme.service';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    HttpClientModule,
    LucideChevronRight, LucideArrowLeftRight, LucideUser, LucideBot, LucideSend, LucideTicket
  ],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.css',
})
export class ChatComponent implements OnInit, AfterViewChecked {
  @ViewChild('messagesEnd') messagesEnd!: ElementRef;
  @ViewChild('inputRef') inputRef!: ElementRef<HTMLTextAreaElement>;

  private projectService = inject(ProjectService);
  private chatService = inject(ChatService);
  private authService = inject(AuthService);
  themeService = inject(ThemeService);
  private router = inject(Router);

  // State
  projects = signal<Project[]>([]);
  selectedProject = signal<Project | null>(null);
  messages = signal<ChatMessage[]>([]);
  inputText = signal('');
  isLoading = signal(false);
  isStreaming = signal(false);
  projectsLoading = signal(true); // inicia como carregando
  projectsError = signal('');
  conversationId = signal<string | null>(null);
  showProjectSelector = signal(true); // inicia mostrando seletor (com loader)

  // Identificação derivada do usuário autenticado
  userName = computed(() => this.authService.user()?.nome ?? '');
  userEmail = computed(() => this.authService.user()?.email ?? '');

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

  // Esconde o "Trocar projeto" se o usuário só tem acesso a um.
  canChangeProject = computed(() => this.projects().length > 1);

  ngOnInit() {
    // Quando este componente carrega, o AuthGuard já garantiu que o usuário está logado.
    this.loadProjects();
  }

  private loadProjects() {
    this.projectsLoading.set(true);
    this.projectsError.set('');
    this.projectService.getProjects().subscribe({
      next: (projects) => {
        this.projects.set(projects);
        this.projectsLoading.set(false);

        // Se o usuário só tem acesso a 1 projeto, seleciona automaticamente.
        if (projects.length === 1) {
          this.selectProject(projects[0]);
        } else {
          this.showProjectSelector.set(true);
        }
      },
      error: (err) => {
        this.projectsLoading.set(false);
        // 401 é tratado pelo interceptor (redireciona para /login).
        if (err?.status !== 401) {
          this.projectsError.set(
            'Falha ao carregar projetos. Verifique a conexão com o servidor.'
          );
          this.showProjectSelector.set(true);
        }
      },
    });
  }

  logout() {
    this.authService.logout();
    this.router.navigate(['/login']);
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
      content: `Olá! Sou o **Ticket Maker**, seu assistente de suporte para o projeto **${project.name}**. \n\nDescreva o problema ou dúvida que você está enfrentando e farei o possível para ajudá-lo. Se não conseguir resolver, posso abrir um chamado no OpenProject para você.`,
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
      .streamMessage(text, project.id, this.conversationId(), {
        projectName: project.name,
      })
      .subscribe({
        next: (event: StreamEvent) => {
          this.handleStreamEvent(event, aiMsgId);
        },
        error: (err) => {
          this.updateMessage(aiMsgId, {
            content: `Erro de conexão: ${err.message ?? 'Tente novamente.'}`,
          });
          this.finalizeAssistantMessage(aiMsgId);
        },
        complete: () => {
          this.finalizeAssistantMessage(aiMsgId);
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
                    {
                      tool: event.tool!,
                      args: event.args ?? {},
                      id: event.id,
                      done: false,
                    },
                  ],
                }
              : m
          )
        );
        break;

      case 'tool_result':
        // Marca a tool como concluída para que o loader pare de girar.
        this.messages.update((msgs) =>
          msgs.map((m) => {
            if (m.id !== aiMsgId || !m.toolCalls) return m;
            return {
              ...m,
              toolCalls: m.toolCalls.map((tc) =>
                tc.id === event.id || (!tc.id && tc.tool === event.tool && !tc.done)
                  ? { ...tc, done: true }
                  : tc
              ),
            };
          })
        );
        break;

      case 'done':
        if (event.conversation_id) {
          this.conversationId.set(event.conversation_id);
        }
        this.finalizeAssistantMessage(aiMsgId);
        break;

      case 'error':
        this.updateMessage(aiMsgId, {
          content: `${event.message ?? 'Ocorreu um erro inesperado.'}`,
        });
        this.finalizeAssistantMessage(aiMsgId);
        break;
    }
  }

  private updateMessage(id: string, patch: Partial<ChatMessage>) {
    this.messages.update((msgs) =>
      msgs.map((m) => (m.id === id ? { ...m, ...patch } : m))
    );
  }

  private finalizeAssistantMessage(id: string) {
    // Marca a mensagem como não-streaming e fecha todos os loaders de tool_call
    // que por algum motivo não tenham recebido o evento tool_result.
    this.messages.update((msgs) =>
      msgs.map((m) =>
        m.id === id
          ? {
              ...m,
              isStreaming: false,
              toolCalls: m.toolCalls?.map((tc) => ({ ...tc, done: true })),
            }
          : m
      )
    );
    this.isStreaming.set(false);
  }

  private scrollToBottom() {
    this.messagesEnd?.nativeElement?.scrollIntoView({ behavior: 'smooth' });
  }

  getToolLabel(toolName: string): string {
    const labels: Record<string, string> = {
      search_knowledge_base: 'Consultando base de conhecimento',
      search_existing_tickets: 'Buscando tickets similares',
      create_ticket: 'Criando ticket no OpenProject',
    };
    return labels[toolName] ?? `${toolName}`;
  }

  trackById(_: number, msg: ChatMessage) {
    return msg.id;
  }

  formatContent(content: string): string {
    return this.sanitizeAssistantContent(content)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.+?)`/g, '<code>$1</code>')
      .replace(/\[(.+?)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/\n/g, '<br>');
  }

  /**
   * Remove vazamentos típicos do Gemini quando ele simula chamadas de função
   * em texto: blocos ```tool_code, ```python com `default_api.xxx(...)`, etc.
   * Também esconde URLs internas do OpenProject que não devem ser mostradas.
   */
  private sanitizeAssistantContent(content: string): string {
    let out = content;
    // Remove blocos de código que contenham chamadas a `default_api.` ou `tool_code`.
    out = out.replace(/```[\s\S]*?(?:tool_code|default_api\.|print\(default_api)[\s\S]*?```/gi, '');
    // Remove menções soltas a default_api.foo(...)
    out = out.replace(/print\(\s*default_api\.[^)]*\)\s*/gi, '');
    out = out.replace(/default_api\.[A-Za-z_]+\([^)]*\)/g, '');
    // Remove referências a URLs internas do OpenProject (segurança em profundidade)
    out = out.replace(/https?:\/\/[^\s)]*openproject[^\s)]*/gi, '');
    return out.trim();
  }
}
