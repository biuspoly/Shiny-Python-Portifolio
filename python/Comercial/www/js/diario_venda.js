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
    resumo.className = "item dv-resumo-selecao";

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
    texto.className = "dv-resumo-texto";
    resumo.appendChild(texto);
    caixaSelectize.insertBefore(resumo, caixaSelectize.querySelector("input"));
    return resumo;
  }

  function atualizarResumo(caixaSelectize) {
    var itens = caixaSelectize.querySelectorAll(":scope > .item:not(.dv-resumo-selecao)");
    var resumo = caixaSelectize.querySelector(".dv-resumo-selecao");

    itens.forEach(function (item) {
      if (item.querySelector(".dv-item-texto")) return;
      Array.from(item.childNodes).forEach(function (no) {
        if (no.nodeType !== Node.TEXT_NODE || !no.textContent.trim()) return;
        var texto = document.createElement("span");
        texto.className = "dv-item-texto";
        texto.textContent = no.textContent;
        item.replaceChild(texto, no);
      });
    });

    if (itens.length > 1) {
      var textoResumo = itens.length + " itens";
      itens.forEach(function (item) {
        item.classList.add("dv-item-oculto");
      });
      if (!resumo) resumo = criarResumo(caixaSelectize);
      var texto = resumo.querySelector(".dv-resumo-texto");
      if (texto.textContent !== textoResumo) texto.textContent = textoResumo;
      resumo.classList.remove("filtro-resumo-oculto");
    } else if (resumo) {

      resumo.classList.add("filtro-resumo-oculto");
      itens.forEach(function (item) {
        item.classList.remove("dv-item-oculto");
      });
    }
  }

  function varrerFiltrosDv() {
    document.querySelectorAll(".filtros-dv .selectize-input").forEach(atualizarResumo);
  }

  document.addEventListener("DOMContentLoaded", function () {
    varrerFiltrosDv();
    new MutationObserver(varrerFiltrosDv).observe(document.body, { childList: true, subtree: true });
  });
})();

(function () {
  var timerOcultar = null;
  var chaveAtual = null;
  window.dvHistoricoAtivo = false;

  Shiny.addCustomMessageHandler("dvHistoricoAtivo", function (mensagem) {
    window.dvHistoricoAtivo = mensagem.ativo;
    if (!mensagem.ativo) window.dvTooltipOcultar();
  });

  function mostrarPainel(evento) {
    var painel = document.getElementById("dv_tooltip_panel");
    if (!painel) return;
    painel.classList.add("dv-tooltip-panel-visivel");
    var posX = evento.clientX + 15;
    var posY = evento.clientY - 20;

    var largura = painel.offsetWidth;
    var altura = painel.offsetHeight;
    if (posX + largura + 10 > window.innerWidth) posX = window.innerWidth - largura - 15;
    if (posY + altura + 20 > window.innerHeight) posY = window.innerHeight - altura - 25;
    painel.style.left = posX + "px";
    painel.style.top = posY + "px";
  }

  window.dvTooltipOcultar = function () {
    timerOcultar = window.setTimeout(function () {
      var painel = document.getElementById("dv_tooltip_panel");
      if (painel) painel.classList.remove("dv-tooltip-panel-visivel");
      chaveAtual = null;
    }, 250);
  };
  window.dvTooltipCancelarOcultar = function () {
    window.clearTimeout(timerOcultar);
  };

  var SELETOR_CATEGORIAS =
    "[data-tooltip-categoria], [data-tooltip-cob-categoria], [data-tooltip-indicador], [data-tooltip-fat]";
  var SELETOR_FAMILIA = "[data-tooltip-familia-prod], [data-tooltip-cob-familia]";

  document.addEventListener("mouseover", function (evento) {
    if (!window.dvHistoricoAtivo) return;

    var celula = evento.target.closest(SELETOR_CATEGORIAS);
    var inputName, valor;
    if (celula) {
      if (celula.hasAttribute("data-tooltip-categoria")) {
        inputName = "dv_categoria_hover";
        valor = celula.getAttribute("data-tooltip-categoria");
      } else if (celula.hasAttribute("data-tooltip-cob-categoria")) {
        inputName = "dv_cob_categoria_hover";
        valor = celula.getAttribute("data-tooltip-cob-categoria");
      } else if (celula.hasAttribute("data-tooltip-indicador")) {
        inputName = "dv_indicador_hover";
        valor = celula.getAttribute("data-tooltip-indicador");
      } else {
        inputName = "dv_fat_hover";
        valor = celula.getAttribute("data-tooltip-fat");
      }
    } else {
      celula = evento.target.closest(SELETOR_FAMILIA);
      if (!celula) return;
      if (celula.hasAttribute("data-tooltip-familia-prod")) {
        inputName = "familia_prod_hover";
        valor = celula.getAttribute("data-tooltip-familia-prod");
      } else {
        inputName = "familia_cob_hover";
        valor = celula.getAttribute("data-tooltip-cob-familia");
      }
    }

    inputName = "diario_venda-" + inputName;

    var chave = inputName + ":" + valor;
    if (chave === chaveAtual) return;
    chaveAtual = chave;
    window.clearTimeout(timerOcultar);
    Shiny.setInputValue(inputName, valor, { priority: "event" });
    mostrarPainel(evento);
  });

  document.addEventListener("mouseout", function (evento) {
    var celula = evento.target.closest(SELETOR_CATEGORIAS + ", " + SELETOR_FAMILIA);
    if (!celula) return;
    if (!celula.contains(evento.relatedTarget)) window.dvTooltipOcultar();
  });
})();
