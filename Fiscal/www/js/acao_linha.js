(function () {
  document.addEventListener("mousedown", function (evento) {
    if (evento.target.closest && evento.target.closest(".fis-acao-linha")) evento.stopPropagation();
  }, true);

  document.addEventListener("click", function (evento) {
    var botao = evento.target.closest && evento.target.closest(".fis-acao-linha [data-acao]");
    if (!botao || botao.disabled || !(window.Shiny && Shiny.setInputValue)) return;
    Shiny.setInputValue(botao.getAttribute("data-input"), {
      acao: botao.getAttribute("data-acao"),
      operacao: botao.getAttribute("data-operacao") || "",
      chave: botao.getAttribute("data-chave"),
      empresa: botao.getAttribute("data-empresa") || "",
      origem: botao.getAttribute("data-origem") || "",
      n: Date.now(),
    }, { priority: "event" });
  });
})();
