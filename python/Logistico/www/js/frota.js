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
    resumo.className = "item frota-resumo-selecao";

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
    texto.className = "frota-resumo-texto";
    resumo.appendChild(texto);
    caixaSelectize.insertBefore(resumo, caixaSelectize.querySelector("input"));
    return resumo;
  }

  function atualizarResumo(caixaSelectize) {
    var itens = caixaSelectize.querySelectorAll(":scope > .item:not(.frota-resumo-selecao)");
    var resumo = caixaSelectize.querySelector(".frota-resumo-selecao");

    itens.forEach(function (item) {
      if (item.querySelector(".frota-item-texto")) return;
      Array.from(item.childNodes).forEach(function (no) {
        if (no.nodeType !== Node.TEXT_NODE || !no.textContent.trim()) return;
        var texto = document.createElement("span");
        texto.className = "frota-item-texto";
        texto.textContent = no.textContent;
        item.replaceChild(texto, no);
      });
    });

    if (itens.length > 1) {
      var textoResumo = itens.length + " itens";
      itens.forEach(function (item) {
        item.classList.add("frota-item-oculto");
      });
      if (!resumo) resumo = criarResumo(caixaSelectize);
      var texto = resumo.querySelector(".frota-resumo-texto");
      if (texto.textContent !== textoResumo) texto.textContent = textoResumo;
      resumo.classList.remove("filtro-resumo-oculto");
    } else if (resumo) {

      resumo.classList.add("filtro-resumo-oculto");
      itens.forEach(function (item) {
        item.classList.remove("frota-item-oculto");
      });
    }
  }

  function varrerFiltrosFrota() {
    document.querySelectorAll(".filtros-frota .selectize-input").forEach(atualizarResumo);
  }

  document.addEventListener("DOMContentLoaded", function () {
    varrerFiltrosFrota();
    new MutationObserver(varrerFiltrosFrota).observe(document.body, { childList: true, subtree: true });
  });
})();

(function () {
  function removerClasseEscura() {
    if (document.documentElement.classList.contains("dark")) {
      document.documentElement.classList.remove("dark");
    }
  }

  removerClasseEscura();
  new MutationObserver(removerClasseEscura).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  });
})();

(function () {
  var SUFIXO_TABELA = "-tabela";
  var MAPA_CLASSE_INPUT = {
    "frota-btn-transferencia": "clique_transferencia",
    "frota-btn-motivo": "clique_motivo",
  };

  document.addEventListener("click", function (evento) {
    var botao = evento.target.closest(".frota-btn-cel");
    if (!botao) return;

    var saidaTabela = botao.closest('[id$="' + SUFIXO_TABELA + '"]');
    if (!saidaTabela) return;
    var ns = saidaTabela.id.slice(0, -SUFIXO_TABELA.length);

    var nomeInput = null;
    for (var classe in MAPA_CLASSE_INPUT) {
      if (botao.classList.contains(classe)) {
        nomeInput = MAPA_CLASSE_INPUT[classe];
        break;
      }
    }
    if (!nomeInput) return;

    Shiny.setInputValue(ns + "-" + nomeInput, botao.dataset.placa, { priority: "event" });
  });
})();

(function () {

  var TITULOS = {
    "frota-placa-atrasada": "Último romaneio há mais de 2 meses",
    "frota-linha-transferencia": "Oportunidade de transferência",
  };

  function explicar(celula) {
    for (var classe in TITULOS) {
      if (celula.classList.contains(classe)) return TITULOS[classe];

      if (celula.parentElement && celula.parentElement.classList.contains(classe)) {
        return TITULOS[classe];
      }
    }
    return null;
  }

  var TITULOS_CABECALHO = {
    "Débito":
      "Débito do DETRAN mais a Multa Senatran. Quando a placa tem multa nos dois, " +
      "entra só o que a Multa Senatran passa da Multa Detran (a mesma multa não conta duas vezes).",
  };

  function varrer() {
    document.querySelectorAll(".frota-modulo shiny-data-frame table tbody td").forEach(function (celula) {
      if (celula.dataset.tituloFrota === "1") return;
      celula.dataset.tituloFrota = "1";
      var explicacao = explicar(celula);
      if (explicacao) celula.title = explicacao;
    });
    document.querySelectorAll(".frota-modulo shiny-data-frame table thead th").forEach(function (cabecalho) {
      var explicacao = TITULOS_CABECALHO[cabecalho.textContent.trim()];
      if (explicacao && cabecalho.title !== explicacao) cabecalho.title = explicacao;
    });
  }

  function agendar() {
    window.requestAnimationFrame(varrer);
  }

  document.addEventListener("DOMContentLoaded", function () {
    agendar();

    new MutationObserver(agendar).observe(document.body, { childList: true, subtree: true });
  });
})();
