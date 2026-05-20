import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface Project {
  id: number;
  name: string;
  identifier: string;
  description: string;
  active: boolean;
}

@Injectable({ providedIn: 'root' })
export class ProjectService {
  private apiUrl = environment.api_back;

  constructor(private http: HttpClient) {}

  getProjects(): Observable<Project[]> {
    return this.http
      .get<{ projects: Project[] }>(`https://vonmvr-ip-170-0-202-57.tunnelmole.net/api/projects`)
      .pipe(map((res) => res.projects));
  }
}
