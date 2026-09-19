import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { of } from 'rxjs';
import { catchError } from 'rxjs/operators';

export type UserRole = 'admin' | 'user';

export interface AuthUser {
  username: string;
  role: UserRole;
  locked: boolean;
}

export interface AuthStatus {
  auth: boolean;
  user: AuthUser | null;
}

export interface UsersResponse {
  status?: string;
  users: AuthUser[];
}

export interface ErrorResponse {
  status: 'error';
  msg: string;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private http = inject(HttpClient);

  me() {
    return this.http.get<AuthStatus>('me').pipe(catchError(this.handleHTTPError));
  }

  login(username: string, password: string) {
    return this.http.post<AuthStatus>('login', { username, password }).pipe(catchError(this.handleHTTPError));
  }

  logout() {
    return this.http.post<AuthStatus>('logout', {}).pipe(catchError(this.handleHTTPError));
  }

  listUsers() {
    return this.http.get<UsersResponse>('users').pipe(catchError(this.handleHTTPError));
  }

  addUser(username: string, password: string, role: UserRole) {
    return this.http.post<UsersResponse>('users', { username, password, role }).pipe(catchError(this.handleHTTPError));
  }

  updateUser(username: string, changes: { password?: string; role?: UserRole }) {
    return this.http.post<UsersResponse>('users/update', { username, ...changes }).pipe(catchError(this.handleHTTPError));
  }

  deleteUser(username: string) {
    return this.http.post<UsersResponse>('users/delete', { username }).pipe(catchError(this.handleHTTPError));
  }

  private handleHTTPError(error: HttpErrorResponse) {
    const msg =
      typeof error.error === 'string' && error.error.trim()
        ? error.error
        : error.error?.msg || error.message || 'Request failed';
    return of({ status: 'error', msg } as ErrorResponse);
  }
}
