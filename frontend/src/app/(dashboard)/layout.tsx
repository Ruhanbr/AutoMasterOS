import { Sidebar } from '@/components/layout/sidebar';
import { OfflineBar } from '@/components/OfflineBar';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* pb-10 garante que o conteúdo não fique atrás da OfflineBar quando visível */}
        <main className="flex-1 overflow-y-auto pb-10">{children}</main>
      </div>
      {/* Barra de status offline (só aparece no app desktop Tauri) */}
      <OfflineBar />
    </div>
  );
}
