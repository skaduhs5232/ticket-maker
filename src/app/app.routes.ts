import { Routes } from '@angular/router';
import { ChatComponent } from './components/chat/chat.component';
import { LoginComponent } from './components/login/login.component';
import { authGuard, noAuthGuard } from './services/auth.guard';

export const routes: Routes = [
  { path: 'login', component: LoginComponent, canActivate: [noAuthGuard] },
  { path: '', component: ChatComponent, canActivate: [authGuard] },
  { path: '**', redirectTo: '' },
];
