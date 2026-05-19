import { Injectable, signal, effect } from '@angular/core';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'tm.theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  /** Tema atual (signal reativo). */
  theme = signal<Theme>(this.resolveInitialTheme());

  constructor() {
    // Aplica a classe no <html> sempre que o tema muda.
    effect(() => {
      const t = this.theme();
      if (typeof document !== 'undefined') {
        const root = document.documentElement;
        root.classList.remove('theme-light', 'theme-dark');
        root.classList.add(`theme-${t}`);
        root.setAttribute('data-theme', t);
      }
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(STORAGE_KEY, t);
      }
    });
  }

  toggle(): void {
    this.theme.update((t) => (t === 'dark' ? 'light' : 'dark'));
  }

  set(theme: Theme): void {
    this.theme.set(theme);
  }

  private resolveInitialTheme(): Theme {
    // 1) preferência salva
    if (typeof localStorage !== 'undefined') {
      const saved = localStorage.getItem(STORAGE_KEY) as Theme | null;
      if (saved === 'light' || saved === 'dark') return saved;
    }
    // 2) preferência do sistema
    if (typeof window !== 'undefined' && window.matchMedia) {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      return prefersDark ? 'dark' : 'light';
    }
    // 3) default
    return 'dark';
  }
}
