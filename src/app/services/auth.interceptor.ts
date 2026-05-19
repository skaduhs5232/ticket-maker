import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { AuthService } from './auth.service';


export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  const token = auth.token();
  if (token) {
    req = req.clone({ setHeaders: { 'X-Auth-Token': token } });
  }

  return next(req).pipe(
    catchError((err) => {
      if (err?.status === 401 && !req.url.includes('/api/auth/login')) {
        auth.clearLocal();
        router.navigate(['/login'], {
          queryParams: { returnUrl: router.url },
        });
      }
      return throwError(() => err);
    })
  );
};
