// frontend/package.json
{
  "name": "atito-qs-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "14.0.4",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "typescript": "^5.3.3",
    "@types/node": "^20.10.5",
    "@types/react": "^18.2.45",
    "@types/react-dom": "^18.2.18",
    "axios": "^1.6.2",
    "zustand": "^4.4.7",
    "react-hook-form": "^7.49.2",
    "zod": "^3.22.4",
    "@hookform/resolvers": "^3.3.3",
    "tailwindcss": "^3.3.6",
    "autoprefixer": "^10.4.16",
    "postcss": "^8.4.32",
    "lucide-react": "^0.298.0",
    "recharts": "^2.10.3",
    "dexie": "^3.2.4",
    "dexie-react-hooks": "^1.1.7",
    "react-dropzone": "^14.2.3",
    "date-fns": "^3.0.6",
    "clsx": "^2.0.0",
    "tailwind-merge": "^2.2.0"
  },
  "devDependencies": {
    "eslint": "^8.56.0",
    "eslint-config-next": "14.0.4"
  }
}

// frontend/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}

// frontend/tailwind.config.js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#366092',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
      },
    },
  },
  plugins: [],
}

// frontend/next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
}

module.exports = nextConfig

// frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000

// frontend/src/lib/api.ts
/**
 * API Client for ATITO QS App
 * Axios-based HTTP client with interceptors
 */

import axios, { AxiosInstance, AxiosError } from 'axios';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Request interceptor - add auth token
    this.client.interceptors.request.use(
      (config) => {
        const token = this.getToken();
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor - handle errors
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        if (error.response?.status === 401) {
          // Token expired, try to refresh
          const refreshed = await this.refreshToken();
          if (refreshed && error.config) {
            return this.client.request(error.config);
          }
          // Redirect to login
          this.clearAuth();
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );
  }

  private getToken(): string | null {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('access_token');
    }
    return null;
  }

  private getRefreshToken(): string | null {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('refresh_token');
    }
    return null;
  }

  private setTokens(accessToken: string, refreshToken: string) {
    if (typeof window !== 'undefined') {
      localStorage.setItem('access_token', accessToken);
      localStorage.setItem('refresh_token', refreshToken);
    }
  }

  private clearAuth() {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
    }
  }

  private async refreshToken(): Promise<boolean> {
    try {
      const refreshToken = this.getRefreshToken();
      if (!refreshToken) return false;

      const response = await axios.post(`${API_BASE_URL}/api/auth/refresh`, {
        refresh_token: refreshToken,
      });

      const { access_token } = response.data;
      this.setTokens(access_token, refreshToken);
      return true;
    } catch {
      return false;
    }
  }

  // Auth endpoints
  async login(email: string, password: string) {
    const response = await this.client.post('/api/auth/login', { email, password });
    const { access_token, refresh_token, user } = response.data;
    this.setTokens(access_token, refresh_token);
    if (typeof window !== 'undefined') {
      localStorage.setItem('user', JSON.stringify(user));
    }
    return response.data;
  }

  async register(data: {
    email: string;
    password: string;
    full_name: string;
    phone_number?: string;
  }) {
    const response = await this.client.post('/api/auth/register', data);
    return response.data;
  }

  async logout() {
    try {
      await this.client.post('/api/auth/logout');
    } finally {
      this.clearAuth();
    }
  }

  async getCurrentUser() {
    const response = await this.client.get('/api/auth/me');
    return response.data;
  }

  // Projects endpoints
  async getProjects(status?: string) {
    const response = await this.client.get('/api/projects/', {
      params: { status },
    });
    return response.data;
  }

  async getProject(projectId: string) {
    const response = await this.client.get(`/api/projects/${projectId}`);
    return response.data;
  }

  async createProject(data: any) {
    const response = await this.client.post('/api/projects/', data);
    return response.data;
  }

  async updateProject(projectId: string, data: any) {
    const response = await this.client.put(`/api/projects/${projectId}`, data);
    return response.data;
  }

  async deleteProject(projectId: string) {
    await this.client.delete(`/api/projects/${projectId}`);
  }

  async finalizeProject(projectId: string) {
    const response = await this.client.post(`/api/projects/${projectId}/finalize`);
    return response.data;
  }

  // File upload endpoints
  async uploadFiles(projectId: string, files: File[]) {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    const response = await this.client.post(
      `/api/uploads/${projectId}/files`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  }

  async processProject(projectId: string) {
    const response = await this.client.post(`/api/uploads/${projectId}/process`);
    return response.data;
  }

  // Reports endpoints
  async downloadBoQExcel(projectId: string) {
    const response = await this.client.get(`/api/reports/${projectId}/boq/excel`, {
      responseType: 'blob',
    });
    return response.data;
  }

  async downloadBBSExcel(projectId: string) {
    const response = await this.client.get(`/api/reports/${projectId}/bbs/excel`, {
      responseType: 'blob',
    });
    return response.data;
  }

  async downloadBoQPDF(projectId: string) {
    const response = await this.client.get(`/api/reports/${projectId}/boq/pdf`, {
      responseType: 'blob',
    });
    return response.data;
  }

  // Payment endpoints
  async initiateSubscription(phoneNumber: string, plan: string) {
    const response = await this.client.post('/api/payments/subscribe', {
      phone_number: phoneNumber,
      plan: plan,
    });
    return response.data;
  }

  async getSubscriptionInfo() {
    const response = await this.client.get('/api/payments/subscription');
    return response.data;
  }

  async checkPaymentStatus(transactionId: string) {
    const response = await this.client.get(`/api/payments/status/${transactionId}`);
    return response.data;
  }

  // Comments endpoints
  async getBoQComments(boqItemId: string) {
    const response = await this.client.get(`/api/comments/boq/${boqItemId}`);
    return response.data;
  }

  async createComment(data: any) {
    const response = await this.client.post('/api/comments/', data);
    return response.data;
  }

  // Site logs endpoints
  async getSiteLogs(projectId: string) {
    const response = await this.client.get(`/api/sitelogs/${projectId}`);
    return response.data;
  }

  async createSiteLog(projectId: string, data: any) {
    const response = await this.client.post(`/api/sitelogs/${projectId}`, data);
    return response.data;
  }

  // Expenses endpoints
  async getExpenses(projectId: string) {
    const response = await this.client.get(`/api/expenses/${projectId}`);
    return response.data;
  }

  async createExpense(projectId: string, data: any) {
    const response = await this.client.post(`/api/expenses/${projectId}`, data);
    return response.data;
  }

  async getBudgetVariance(projectId: string) {
    const response = await this.client.get(`/api/expenses/${projectId}/variance`);
    return response.data;
  }
}

export const api = new ApiClient();


// frontend/src/lib/store.ts
/**
 * Zustand Global State Management
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  subscription_plan: string;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  setUser: (user: User | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      logout: () => set({ user: null, isAuthenticated: false }),
    }),
    {
      name: 'auth-storage',
    }
  )
);

interface Project {
  id: string;
  name: string;
  status: string;
  estimated_cost: number;
}

interface ProjectState {
  projects: Project[];
  currentProject: Project | null;
  setProjects: (projects: Project[]) => void;
  setCurrentProject: (project: Project | null) => void;
}

export const useProjectStore = create<ProjectState>((set) => ({
  projects: [],
  currentProject: null,
  setProjects: (projects) => set({ projects }),
  setCurrentProject: (project) => set({ currentProject: project }),
}));


// frontend/src/lib/db.ts
/**
 * IndexedDB for Offline Support using Dexie
 */

import Dexie, { Table } from 'dexie';

export interface SiteLogQueue {
  id?: number;
  projectId: string;
  logText: string;
  timestamp: Date;
  synced: boolean;
}

export class OfflineDB extends Dexie {
  siteLogQueue!: Table<SiteLogQueue>;

  constructor() {
    super('AtitoQSDB');
    this.version(1).stores({
      siteLogQueue: '++id, projectId, synced, timestamp',
    });
  }
}

export const db = new OfflineDB();


// frontend/src/lib/utils.ts
/**
 * Utility Functions
 */

import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: 'KES',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatDate(date: string | Date): string {
  return new Intl.DateTimeFormat('en-KE', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(new Date(date));
}

export function downloadFile(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}
