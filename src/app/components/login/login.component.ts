import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { LucideTicket } from '@lucide/angular';

import { AuthService } from '../../services/auth.service';
import { ThemeService } from '../../services/theme.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, LucideTicket],
  templateUrl: './login.component.html',
  styleUrl: './login.component.css',
})
export class LoginComponent {
  private auth = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  themeService = inject(ThemeService);

  email = signal('');
  senha = signal('');
  loading = signal(false);
  error = signal('');

  submit(event?: Event) {
    // Garante que o form nunca submeta nativamente (evita reload da página).
    event?.preventDefault();
    event?.stopPropagation();

    const email = this.email().trim();
    const senha = this.senha();
    if (!email || !senha) return;

    this.error.set('');
    this.loading.set(true);
    this.auth.login(email, senha).subscribe({
      next: () => {
        this.loading.set(false);
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') ?? '/';
        this.router.navigateByUrl(returnUrl);
      },
      error: (err) => {
        this.loading.set(false);
        const msg =
          err?.error?.detail ??
          (err?.status === 401
            ? 'E-mail ou senha inválidos.'
            : 'Não foi possível entrar. Tente novamente.');
        this.error.set(msg);
      },
    });
  }
}
