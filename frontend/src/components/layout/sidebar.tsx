'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Tractor, LayoutDashboard, ClipboardList, Users, FileText, Package, DollarSign, Wrench, HardHat, Menu, X } from 'lucide-react';
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
  const [mounted, setMounted] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  // Fecha o menu ao trocar de página no mobile
  useEffect(() => { setMobileOpen(false); }, [pathname]);

  const SidebarContent = () => (
    <aside className="w-64 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col h-full">
      {/* Logo */}
      <div className="flex items-center justify-between gap-3 px-6 py-5 border-b border-gray-200">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-green-600">
            <Tractor className="w-5 h-5 text-white" />
          </div>
          <div>
            <p className="text-base font-bold text-gray-900 leading-none">AutoMaster</p>
            <p className="text-xs text-gray-500 mt-0.5">Oficinas Agrícolas</p>
          </div>
        </div>
        {/* Botão fechar no mobile */}
        <button
          className="md:hidden text-gray-400 hover:text-gray-600"
          onClick={() => setMobileOpen(false)}
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
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

  return (
    <>
      {/* Botão hambúrguer — só aparece no mobile */}
      <button
        className="md:hidden fixed top-4 left-4 z-50 p-2 bg-white rounded-lg shadow-md border border-gray-200"
        onClick={() => setMobileOpen(true)}
      >
        <Menu className="w-5 h-5 text-gray-600" />
      </button>

      {/* Sidebar desktop — sempre visível em telas >= md */}
      <div className="hidden md:flex">
        <SidebarContent />
      </div>

      {/* Sidebar mobile — overlay */}
      {mobileOpen && (
        <>
          {/* Fundo escurecido */}
          <div
            className="md:hidden fixed inset-0 z-40 bg-black/40"
            onClick={() => setMobileOpen(false)}
          />
          {/* Sidebar deslizando da esquerda */}
          <div className="md:hidden fixed inset-y-0 left-0 z-50 flex">
            <SidebarContent />
          </div>
        </>
      )}
    </>
  );
}
