// Menu lateral: no computador o "<" alterna para o modo mini (só ícones) em
// vez de esconder o menu; o botão clicado fica destacado; só um grupo aberto.
document.addEventListener("DOMContentLoaded", function () {
  const layout = document.querySelector(".bslib-sidebar-layout");
  if (!layout) return;
  const toggle = layout.querySelector(".collapse-toggle");
  const telaDesktop = window.matchMedia("(min-width: 576px)");
  if (telaDesktop.matches) layout.classList.add("mini-sidebar");

  // "true": roda antes do bslib, que esconderia o menu inteiro.
  toggle.addEventListener("click", function (e) {
    if (!telaDesktop.matches) return;
    e.stopImmediatePropagation();
    layout.classList.toggle("mini-sidebar");
  }, true);

  function cabecalhoDoGrupo(botao) {
    const item = botao.closest(".accordion-item");
    return item ? item.querySelector(".accordion-button") : null;
  }

  document.querySelectorAll(".sidebar .action-button.selecionado").forEach(function (botao) {
    const cab = cabecalhoDoGrupo(botao);
    if (cab) cab.classList.add("selecionado");
  });

  document.addEventListener("click", function (e) {
    const botao = e.target.closest(".sidebar .action-button");
    if (!botao) return;
    document.querySelectorAll(".sidebar .selecionado").forEach(function (el) {
      el.classList.remove("selecionado");
    });
    botao.classList.add("selecionado");
    const cab = cabecalhoDoGrupo(botao);
    if (cab) cab.classList.add("selecionado");
  });

  document.addEventListener("show.bs.collapse", function (e) {
    if (!e.target.closest(".sidebar")) return;
    document.querySelectorAll(".sidebar .accordion-collapse.show").forEach(function (outro) {
      if (outro !== e.target) bootstrap.Collapse.getOrCreateInstance(outro).hide();
    });
  });
});
