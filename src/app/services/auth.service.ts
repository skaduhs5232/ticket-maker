import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import { environment } from '../../environments/environment';

export interface AuthUser {
  codigo: string;
  nome: string;
  email: string;
}

export interface LoginResponse {
  token: string;
  user: AuthUser;
  project_ids: number[];
}

const TOKEN_KEY = 'tm.auth_token';
const USER_KEY = 'tm.auth_user';
const PROJECTS_KEY = 'tm.auth_projects';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private apiUrl = environment.api_back;

  token = signal<string | null>(this.readStorage(TOKEN_KEY));
  user = signal<AuthUser | null>(this.readJson<AuthUser>(USER_KEY));
  allowedProjectIds = signal<number[]>(this.readJson<number[]>(PROJECTS_KEY) ?? []);
  isAuthenticated = computed(() => !!this.token());

  constructor(private http: HttpClient) {}

  login(email: string, senha: string): Observable<LoginResponse> {
    return this.http
      .post<LoginResponse>(`https://vonmvr-ip-170-0-202-57.tunnelmole.net/api/auth/login`, {
        email,
        senha,
      })
      .pipe(
        tap((resp) => {
          this.token.set(resp.token);
          this.user.set(resp.user);
          this.allowedProjectIds.set(resp.project_ids ?? []);
          this.writeStorage(TOKEN_KEY, resp.token);
          this.writeJson(USER_KEY, resp.user);
          this.writeJson(PROJECTS_KEY, resp.project_ids ?? []);
        }),
      );
  }

  logout(): void {
    const t = this.token();
    if (t) {
      this.http
        .post(`https://vonmvr-ip-170-0-202-57.tunnelmole.net/api/auth/logout`, {})
        .subscribe({ error: () => {} });
    }
    this.clearLocal();
  }

  clearLocal(): void {
    this.token.set(null);
    this.user.set(null);
    this.allowedProjectIds.set([]);
    this.removeStorage(TOKEN_KEY);
    this.removeStorage(USER_KEY);
    this.removeStorage(PROJECTS_KEY);
  }

  private readStorage(key: string): string | null {
    if (typeof localStorage === 'undefined') return null;
    return localStorage.getItem(key);
  }

  private readJson<T>(key: string): T | null {
    const raw = this.readStorage(key);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as T;
    } catch {
      return null;
    }
  }

  private writeStorage(key: string, value: string) {
    if (typeof localStorage !== 'undefined') localStorage.setItem(key, value);
  }

  private writeJson(key: string, value: unknown) {
    if (typeof localStorage !== 'undefined') localStorage.setItem(key, JSON.stringify(value));
  }

  private removeStorage(key: string) {
    if (typeof localStorage !== 'undefined') localStorage.removeItem(key);
  }
}
