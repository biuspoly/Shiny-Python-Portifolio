(function () {
  var CLASSE_LINHA = "cab-grupo-linha";
  var aplicando = false;

  function montarLinha(nivel) {
    var tr = document.createElement("tr");
    tr.className = CLASSE_LINHA;
    tr.setAttribute("aria-hidden", "true");
    nivel.forEach(function (celula) {
      var th = document.createElement("th");
      th.colSpan = celula.span || 1;
      th.textContent = celula.nome || "";
      th.className = celula.nome ? "cab-grupo-celula" : "cab-grupo-vazio";

      if (celula.nome) th.title = celula.nome;
      if (celula.fundo) th.style.backgroundColor = celula.fundo;
      if (celula.texto) th.style.color = celula.texto;
      if (celula.alinha) th.style.textAlign = celula.alinha;
      tr.appendChild(th);
    });
    return tr;
  }

  function trocarRotulos(linhaColunas, rotulos) {
    Array.prototype.forEach.call(linhaColunas.children, function (th, i) {
      if (i >= rotulos.length) return;
      var alvo = th.querySelector("div") || th;
      if (alvo.textContent === rotulos[i]) return;
      if (!th.title) th.title = alvo.textContent.replace(/\n/g, " ");
      alvo.textContent = rotulos[i];
    });
  }

  function aplicar(caixa) {
    var thead = caixa.querySelector("table thead");
    if (!thead) return;
    var linhaColunas = thead.querySelector("tr:not(." + CLASSE_LINHA + ")");
    if (!linhaColunas) return;

    var niveis, rotulos;
    try {
      niveis = JSON.parse(caixa.getAttribute("data-cabecalho-grupos"));
      rotulos = JSON.parse(caixa.getAttribute("data-cabecalho-rotulos") || "[]");
    } catch (erro) {
      return;
    }
    if (!niveis || !niveis.length) return;

    if (rotulos.length) trocarRotulos(linhaColunas, rotulos);

    var chave = caixa.getAttribute("data-cabecalho-grupos") + "|" + linhaColunas.children.length;
    if (thead.dataset.cabGrupo === chave &&
        thead.querySelectorAll("." + CLASSE_LINHA).length === niveis.length) return;

    Array.prototype.forEach.call(thead.querySelectorAll("." + CLASSE_LINHA), function (tr) {
      tr.parentNode.removeChild(tr);
    });
    niveis.forEach(function (nivel) {
      thead.insertBefore(montarLinha(nivel), linhaColunas);
    });
    thead.dataset.cabGrupo = chave;
  }

  function aplicarEmTodas() {
    if (aplicando) return;
    aplicando = true;
    try {
      Array.prototype.forEach.call(
        document.querySelectorAll("[data-cabecalho-grupos]"),
        aplicar
      );
    } finally {
      aplicando = false;
    }
  }

  new MutationObserver(aplicarEmTodas).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });

  if (window.jQuery) {
    jQuery(document).on("shiny:value", function () {
      window.setTimeout(aplicarEmTodas, 0);
    });
  }
  document.addEventListener("DOMContentLoaded", aplicarEmTodas);
  aplicarEmTodas();
})();
