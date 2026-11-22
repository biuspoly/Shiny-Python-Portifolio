(function () {
  function celula(e) {
    return e.target.closest ? e.target.closest("table.tabela-mare-consolidada td[data-flx-l]") : null;
  }

  document.addEventListener("mousedown", function (e) {
    if (e.shiftKey && celula(e)) e.preventDefault();
  }, true);

  document.addEventListener("click", function (e) {
    var td = celula(e);
    if (!td || !window.Shiny) return;
    var cor = (e.ctrlKey || e.metaKey) ? "amarela" : (e.shiftKey ? "laranja" : null);
    if (cor && td.getAttribute("data-flx-marcavel") === "1") {
      Shiny.setInputValue("fluxo-marcar_celula",
        { l: Number(td.getAttribute("data-flx-l")), c: Number(td.getAttribute("data-flx-c")), cor: cor, n: Date.now() },
        { priority: "event" });
    }

    var balao = td.getAttribute("data-flx-balao");
    if (!balao) return;
    e.stopPropagation();
    if (!cor) {
      Shiny.setInputValue("fluxo-detalhe_celula", { id: balao, n: Date.now() }, { priority: "event" });
    }
  }, true);

  document.addEventListener("click", function (e) {
    if (!window.Shiny || !e.target.closest) return;
    if (e.target.closest(".popover") || e.target.closest("td[data-flx-balao]")) return;
    var abertos = [];
    document.querySelectorAll("table.tabela-mare-consolidada bslib-popover").forEach(function (p) {
      var td = p.closest("td[data-flx-balao]");
      if (p.visible && td) abertos.push(td.getAttribute("data-flx-balao"));
    });
    if (abertos.length) {
      Shiny.setInputValue("fluxo-fechar_baloes", { ids: abertos, n: Date.now() }, { priority: "event" });
    }
  });

  document.addEventListener("click", function (e) {
    var linha = e.target.closest ? e.target.closest(".flx-balao-tabela tr.flx-mov-mes") : null;
    if (linha && linha.parentNode) linha.parentNode.classList.toggle("aberto");
  });

  document.addEventListener("click", function (e) {
    if (!window.Shiny || !e.target.closest) return;
    if (e.target.closest(".popover") || e.target.closest("table.bhk-tabela bslib-popover")) return;
    var abertos = [];
    document.querySelectorAll("table.bhk-tabela bslib-popover").forEach(function (p) {
      if (p.visible && p.id) abertos.push(p.id.replace(/^banco_mar-/, ""));
    });
    if (abertos.length) {
      Shiny.setInputValue("banco_mar-fechar_baloes", { ids: abertos, n: Date.now() }, { priority: "event" });
    }
  });

  if (window.Shiny && Shiny.addCustomMessageHandler) {
    Shiny.addCustomMessageHandler("fluxoMarcar", function (recado) {
      var td = document.querySelector('table.tabela-mare-consolidada td[data-flx-l="' + recado.l +
                                      '"][data-flx-c="' + recado.c + '"]');
      if (!td) return;
      td.classList.toggle("celula-marcada", !!recado.amarela);
      td.classList.toggle("celula-marcada-laranja", !!recado.laranja);
    });
  }
})();
