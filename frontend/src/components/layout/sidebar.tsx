'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Tractor, LayoutDashboard, ClipboardList, Users, FileText, Package, DollarSign, Wrench, HardHat } from 'lucide-react';
import { cn } from '@/lib/utils';

const navItems = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/service-orders', label: 'Ordens de Serviço', icon: ClipboardList },
  { href: '/clients', label: 'Clientes', icon: Users },
  { href: '/machines', label: 'Máquinas', icon: Wrench },
  { href: '/stock', label: 'Estoque', icon: Package },
  { href: '/financial', label: 'Financeiro', icon: DollarSign },
  { href: '/invoices', label: 'NF-e', icon: FileText },
  { href: '/tecnicos', label: 'Técnicos', icon: HardHat },
];

export function Sidebar() {
  const pathname = usePathname();
  // Defer active-state to client-only to prevent hydration mismatch.
  // The App Router can serve a cached layout whose SSR HTML was rendered for
  // a different route; `usePathname()` on the client then disagrees with
  // the server-rendered class names.  By gating on `mounted`, SSR always
  // emits the neutral (inactive) style and React never sees a mismatch.
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  return (
    <aside className="w-64 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col">
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-gray-200">
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-green-600">
          <Tractor className="w-5 h-5 text-white" />
        </div>
        <div>
          <p className="text-base font-bold text-gray-900 leading-none">AutoMaster</p>
          <p className="text-xs text-gray-500 mt-0.5">Oficinas Agrícolas</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive =
            mounted &&
            (item.href === '/dashboard'
              ? pathname === '/dashboard'
              : pathname.startsWith(item.href));

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-green-50 text-green-700'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900',
              )}
            >
              <Icon
                className={cn(
                  'w-5 h-5 flex-shrink-0',
                  isActive ? 'text-green-600' : 'text-gray-400',
                )}
              />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Version */}
      <div className="px-6 py-4 border-t border-gray-200">
        <p className="text-xs text-gray-400">v1.0.0</p>
      </div>
    </aside>
  );
}
