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
    resumo.className = "item pde-resumo-selecao";

    var limpar = document.createElement("a");
    limpar.href = "javascript:void(0)";
    limpar.className = "remove";
    limpar.title = "Remover todos";
    limpar.textContent = "\u00d7";
    limpar.addEventListener("click", function (evento) {
      evento.preventDefault();
      evento.stopPropagation();
      limparSelecao(caixaSelectize);
    });
    resumo.appendChild(limpar);

    var texto = document.createElement("span");
    texto.className = "pde-resumo-texto";
    resumo.appendChild(texto);
    caixaSelectize.insertBefore(resumo, caixaSelectize.querySelector("input"));
    return resumo;
  }

  function atualizarResumo(caixaSelectize) {
    var itens = caixaSelectize.querySelectorAll(":scope > .item:not(.pde-resumo-selecao)");
    var resumo = caixaSelectize.querySelector(".pde-resumo-selecao");

    itens.forEach(function (item) {
      if (item.querySelector(".pde-item-texto")) return;
      Array.from(item.childNodes).forEach(function (no) {
        if (no.nodeType !== Node.TEXT_NODE || !no.textContent.trim()) return;
        var texto = document.createElement("span");
        texto.className = "pde-item-texto";
        texto.textContent = no.textContent;
        item.replaceChild(texto, no);
      });
    });

    if (itens.length > 1) {
      var textoResumo = itens.length + " itens";
      itens.forEach(function (item) {
        item.classList.add("pde-item-oculto");
      });
      if (!resumo) resumo = criarResumo(caixaSelectize);
      var texto = resumo.querySelector(".pde-resumo-texto");
      if (texto.textContent !== textoResumo) texto.textContent = textoResumo;
      resumo.classList.remove("filtro-resumo-oculto");
    } else if (resumo) {

      resumo.classList.add("filtro-resumo-oculto");
      itens.forEach(function (item) {
        item.classList.remove("pde-item-oculto");
      });
    }
  }

  function varrerFiltrosPde() {
    document.querySelectorAll(".filtros-pde .selectize-input").forEach(atualizarResumo);
  }

  document.addEventListener("DOMContentLoaded", function () {
    varrerFiltrosPde();
    new MutationObserver(varrerFiltrosPde).observe(document.body, { childList: true, subtree: true });
  });
})();
