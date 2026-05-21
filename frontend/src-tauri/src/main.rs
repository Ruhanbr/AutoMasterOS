// Evita janela de console no Windows em release. NÃO REMOVA esta linha.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    automaster_lib::run()
}
