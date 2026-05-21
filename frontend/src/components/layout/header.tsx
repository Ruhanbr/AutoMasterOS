'use client';

import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { LogOut, User, ChevronDown } from 'lucide-react';
import { useState } from 'react';
import { authApi } from '@/lib/api';
import { clearTokens } from '@/lib/auth';
import type { User as UserType } from '@/types';

interface HeaderProps {
  title: string;
}

export function Header({ title }: HeaderProps) {
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);

  const { data: user } = useQuery<UserType>({
    queryKey: ['me'],
    queryFn: async () => {
      const res = await authApi.me();
      return res.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  const handleLogout = () => {
    clearTokens();
    router.push('/login');
    router.refresh();
  };

  return (
    <header className="bg-white border-b border-gray-200 px-6 h-14 flex items-center justify-between flex-shrink-0">
      <h1 className="text-lg font-semibold text-gray-900">{title}</h1>

      {/* User menu */}
      <div className="relative">
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-gray-50 transition"
        >
          <div className="w-7 h-7 rounded-full bg-green-100 flex items-center justify-center">
            <User className="w-4 h-4 text-green-700" />
          </div>
          <div className="text-left hidden sm:block">
            <p className="text-sm font-medium text-gray-900 leading-none">
              {user?.full_name || 'Usuário'}
            </p>
            <p className="text-xs text-gray-500 mt-0.5">{user?.role || ''}</p>
          </div>
          <ChevronDown className="w-4 h-4 text-gray-400" />
        </button>

        {menuOpen && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
            <div className="absolute right-0 top-full mt-1 w-48 bg-white rounded-lg shadow-lg border border-gray-200 z-20 py-1">
              <div className="px-3 py-2 border-b border-gray-100">
                <p className="text-xs font-medium text-gray-900">{user?.full_name}</p>
                <p className="text-xs text-gray-500">{user?.email}</p>
              </div>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50 transition"
              >
                <LogOut className="w-4 h-4" />
                Sair
              </button>
            </div>
          </>
        )}
      </div>
    </header>
  );
}
