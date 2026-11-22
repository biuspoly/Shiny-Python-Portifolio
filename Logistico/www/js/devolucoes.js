(function () {
  function limparSelecao(caixaSelectize) {
    var controle = caixaSelectize.closest(".selectize-control");
    var select = controle && controle.previousElementSibling;
    if (!select || !select.selectize) {
      select = controle && controle.parentElement.querySelector("select.selectized");
    }
    if (select && select.selectize) select.selectize.clear();
  }

  function criarResumo(caixaSelectize) {
    var resumo = document.createElement("div");
    resumo.className = "item dev-resumo-selecao";

    var limpar = document.createElement("a");
    limpar.href = "javascript:void(0)";
    limpar.className = "remove";
    limpar.title = "Remover todos";
    limpar.textContent = "×";
    limpar.addEventListener("click", function (evento) {
      evento.preventDefault();
      evento.stopPropagation();
      limparSelecao(caixaSelectize);
    });
    resumo.appendChild(limpar);

    var texto = document.createElement("span");
    texto.className = "dev-resumo-texto";
    resumo.appendChild(texto);
    caixaSelectize.insertBefore(resumo, caixaSelectize.querySelector("input"));
    return resumo;
  }

  function atualizarResumo(caixaSelectize) {
    var itens = caixaSelectize.querySelectorAll(":scope > .item:not(.dev-resumo-selecao)");
    var resumo = caixaSelectize.querySelector(".dev-resumo-selecao");

    itens.forEach(function (item) {
      if (item.querySelector(".dev-item-texto")) return;
      Array.from(item.childNodes).forEach(function (no) {
        if (no.nodeType !== Node.TEXT_NODE || !no.textContent.trim()) return;
        var texto = document.createElement("span");
        texto.className = "dev-item-texto";
        texto.textContent = no.textContent;
        item.replaceChild(texto, no);
      });
    });

    if (itens.length > 1) {
      var textoResumo = itens.length + " itens";
      itens.forEach(function (item) {
        item.classList.add("dev-item-oculto");
      });
      if (!resumo) resumo = criarResumo(caixaSelectize);
      var texto = resumo.querySelector(".dev-resumo-texto");
      if (texto.textContent !== textoResumo) texto.textContent = textoResumo;
      resumo.classList.remove("filtro-resumo-oculto");
    } else if (resumo) {

      resumo.classList.add("filtro-resumo-oculto");
      itens.forEach(function (item) {
        item.classList.remove("dev-item-oculto");
      });
    }
  }

  function varrerFiltrosDev() {
    document.querySelectorAll(".filtros-dev .selectize-input").forEach(atualizarResumo);
  }

  document.addEventListener("DOMContentLoaded", function () {
    varrerFiltrosDev();
    new MutationObserver(varrerFiltrosDev).observe(document.body, { childList: true, subtree: true });
  });
})();

(function () {
  var SUFIXO_TABELA = "-tabela";

  document.addEventListener("click", function (evento) {
    var elemento = evento.target.closest(".dev-grupo-data");
    if (!elemento) return;

    var saidaTabela = elemento.closest('[id$="' + SUFIXO_TABELA + '"]');
    if (!saidaTabela) return;
    var ns = saidaTabela.id.slice(0, -SUFIXO_TABELA.length);

    Shiny.setInputValue(ns + "-clique_grupo_data", elemento.dataset.grupoData, { priority: "event" });
  });
})();
