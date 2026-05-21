import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Rotas públicas — não exigem autenticação
const PUBLIC_PATHS = ['/login', '/master/login'];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Rotas públicas — libera sem verificação
  if (PUBLIC_PATHS.some((path) => pathname.startsWith(path))) {
    return NextResponse.next();
  }

  // Internals do Next.js — libera sempre
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/api') ||
    pathname.includes('.')
  ) {
    return NextResponse.next();
  }

  const token = request.cookies.get('access_token')?.value;

  if (!token) {
    // Rotas do painel master → redireciona para o login master
    if (pathname.startsWith('/master')) {
      return NextResponse.redirect(new URL('/master/login', request.url));
    }
    // Demais rotas → login normal
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('from', pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
